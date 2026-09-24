# -*- coding: utf-8 -*-
"""
轻量级"宽表 + 坏客户清单 → 可喂给链路的 df"合成器。

典型用法（agent 推荐写法）：

    from risk_data_prep.scripts.prepare_df import prepare_df
    df, feature_cols = prepare_df(
        wide_path='data/processed/舆情特征宽表_全量补零.csv',
        bad_customer_path='data/raw/坏客户标记.csv',
        id_col='客户编号', target_col='is_bad',
        filter={'企业规模': {'exclude': ['0']}},
        exclude_features={'授信总金额', '表内授信余额', '表外授信余额', '类信贷余额'},
    )

之后直接：

    run_generic_pipeline(df=df, feature_cols=feature_cols, target_col='is_bad', ...)

设计目标：
- 统一"打坏客户标签 + 过滤口径 + 选特征列"的标准做法，避免每个 agent 手抄一遍
- 只做数据整形（不写盘）
"""
from __future__ import annotations

import sys
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from .feature_sanity import find_degenerate_qual_names, find_redundant_binary_features


def _read_csv_robust(path: str, dtype=None) -> pd.DataFrame:
    """兼容 utf-8-sig / utf-8 / gbk 的读取。

    dtype 用于把主键列锁成 str（§5.1）：若不锁，'00123' 会被推断成 int 123，
    之后 astype(str) 只能得到 '123'——前导零在源头就没了。pandas 对 dtype
    里不存在的列名静默忽略，故主键列名尚未校验时传入也安全。
    """
    for enc in ('utf-8-sig', 'utf-8', 'gbk', 'gb18030'):
        try:
            return pd.read_csv(path, encoding=enc, dtype=dtype)
        except UnicodeDecodeError:
            continue
    # 最后兜底
    return pd.read_csv(path, encoding='latin1', dtype=dtype)


def prepare_df(
    wide_path: str,
    bad_customer_path: Optional[str] = None,
    *,
    id_col: str = '客户编号',
    target_col: str = 'is_bad',
    bad_id_col: Optional[str] = None,
    merge_table_path: Optional[str] = None,
    merge_id_col: Optional[str] = None,
    merge_cols: Optional[Iterable[str]] = None,
    filter: Optional[Dict[str, Dict[str, Iterable]]] = None,
    exclude_features: Optional[Iterable[str]] = None,
    extra_exclude_cols: Optional[Iterable[str]] = None,
    min_std: float = 0.0,
) -> Tuple[pd.DataFrame, List[str]]:
    """把宽表 + 坏客户清单合成为可直接送入 `run_generic_pipeline` 的 (df, feature_cols)。

    Args:
        wide_path: 宽表 CSV 路径，需含 id_col 列。
        bad_customer_path: 坏客户清单 CSV。若为 None，假定宽表已含 target_col。
        id_col: 宽表与坏客户清单共用的主键（默认 `客户编号`）。
        target_col: 生成/校验的目标列名（默认 `is_bad`）。
        bad_id_col: 坏客户清单中的主键列；默认与 id_col 相同。
        merge_table_path: 可选的补充表 CSV（如分群维度在另一张表）。按主键 left-join
                          到宽表上，免去手抄 pandas merge（AGENTS.md 禁止手抄合并）。
        merge_id_col: 补充表主键列名；默认与 id_col 相同。
        merge_cols: 仅从补充表带入这些列（默认带入全部非主键列）。
        filter: 运行前过滤，每列接受以下规则键（可联用，按顺序应用）：
                  - exclude: list  排除的取值（按字符串比较）
                  - include: list  仅保留的取值（按字符串比较）
                  - min: number    保留 col >= min 的行（数值列）
                  - max: number    保留 col <= max 的行（数值列）
                  - range: [lo,hi] 等价同时设 min=lo, max=hi
                  - drop_na: bool  丢弃该列为空的行
                示例：
                  {'企业规模': {'exclude': ['0']},
                   '行业': {'include': ['制造业']},
                   '非银机构占比': {'range': [0, 1]},
                   '资产负债率': {'max': 1.0, 'drop_na': True}}
        exclude_features: 不参与分析的业务列（如金融敞口类）。
        extra_exclude_cols: 额外排除的非特征列；id_col 与 target_col 自动加入。
        min_std: 特征最小标准差（默认 0，即仅剔除完全常数列）。

    Returns:
        (df, feature_cols)：
          - df 已打好 target_col 标签并按 filter 过滤
          - feature_cols 为自动识别的数值型特征列（剔除 id/target/指定排除/零方差）
    """
    df = _read_csv_robust(wide_path, dtype={id_col: str})

    # 可选：左连接一张维度/补充表（如分群维度在另一张 CSV）。
    # 在主键上 left-join，免去每个 agent 手抄 pandas merge（AGENTS.md 禁止手抄合并）。
    if merge_table_path is not None:
        mkey = merge_id_col or id_col
        merge_df = _read_csv_robust(merge_table_path, dtype={mkey: str})
        if id_col not in df.columns:
            raise ValueError(f"宽表缺少主键列 {id_col!r}；实际列：{list(df.columns)[:20]}...")
        if mkey not in merge_df.columns:
            raise ValueError(
                f"补充表 {merge_table_path!r} 缺少主键列 {mkey!r}；实际列：{list(merge_df.columns)}"
            )
        if merge_cols:
            want = list(merge_cols)
            missing = [c for c in want if c not in merge_df.columns]
            if missing:
                raise ValueError(
                    f"补充表 {merge_table_path!r} 缺少指定列 {missing}；实际列：{list(merge_df.columns)}"
                )
            merge_df = merge_df[[mkey] + [c for c in want if c != mkey]]
        # 主键统一转字符串，规避前导零/类型不一致导致的 0 命中
        df[id_col] = df[id_col].astype(str)
        merge_df = merge_df.copy()
        merge_df[mkey] = merge_df[mkey].astype(str)
        # 去重补充表主键，避免一对多放大行数
        merge_df = merge_df.drop_duplicates(subset=[mkey], keep='first')
        merge_payload = [c for c in merge_df.columns if c != mkey]
        # 撞列（除主键外）以补充表为准：先从左表删同名列再 join
        collide = [c for c in merge_payload if c in df.columns]
        if collide:
            print(
                f"[提示] 补充表与宽表存在同名列 {collide}，将以补充表覆盖宽表。",
                file=sys.stderr,
            )
            df = df.drop(columns=collide)
        n_before = len(df)
        df = df.merge(merge_df, left_on=id_col, right_on=mkey, how='left')
        if mkey != id_col and mkey in df.columns:
            df = df.drop(columns=[mkey])
        if merge_payload:
            matched = int(df[merge_payload[0]].notna().sum())
            if matched == 0:
                raise ValueError(
                    f"补充表 {merge_table_path!r} 与宽表主键 0 匹配，left-join 后新增列全为空。\n"
                    f"  宽表主键 {id_col!r} 样例: {df[id_col].head(5).tolist()}\n"
                    f"  补充表主键 {mkey!r} 样例: {merge_df[mkey].head(5).tolist()}\n"
                    f"  → 请检查 --merge-id-col 是否正确、两边主键是否存在前导零/空格差异。"
                )
        if len(df) != n_before:
            raise ValueError(
                f"补充表 left-join 后行数从 {n_before} 变为 {len(df)}（补充表主键未唯一？）"
            )

    if bad_customer_path is not None:
        key = bad_id_col or id_col
        bad_df = _read_csv_robust(bad_customer_path, dtype={key: str})
        if key not in bad_df.columns:
            raise ValueError(f"坏客户清单缺少主键列 {key!r}；实际列：{list(bad_df.columns)}")
        if id_col not in df.columns:
            raise ValueError(f"宽表缺少主键列 {id_col!r}；实际列：{list(df.columns)[:20]}...")
        bad_set = set(bad_df[key].astype(str))
        n_list = len(bad_set)
        if n_list == 0:
            raise ValueError(
                f"坏客户清单为空（{bad_customer_path!r} 去重后 0 条，可能只有表头）；"
                f"请检查清单文件内容。"
            )
        df = df.copy()  # 去碎片化，避免插列时的 pandas PerformanceWarning（P3-2）
        df[target_col] = df[id_col].astype(str).isin(bad_set).astype(int)
        n_bad = int(df[target_col].sum())
        if n_bad == 0:
            wide_sample = df[id_col].astype(str).head(5).tolist()
            list_sample = sorted(bad_set)[:5]
            raise ValueError(
                f"坏客户清单与宽表主键 0 匹配，全部客户将被标为好客户（{target_col}=0），"
                f"下游分析将全部空跑。\n"
                f"  宽表主键 {id_col!r} 样例: {wide_sample}\n"
                f"  清单主键 {key!r} 样例: {list_sample}\n"
                f"  → 请检查 --bad-id-col 是否正确、两边主键是否存在前导零/空格/格式差异。"
            )
        if n_bad == len(df):
            raise ValueError(
                f"全部 {len(df)} 个客户都被标为坏客户（{target_col}=1）；"
                f"坏客户清单或主键可能用错，请检查清单文件与 --bad-id-col。"
            )
        # P3-1：低匹配率有两种成因，按「宽表内是否真的标到了坏客户」区分，
        # 避免把「正常子集」（清单覆盖人群大于本次分析总体）误报成「主键格式不一致」。
        n_out = n_list - n_bad                      # 清单中未落在宽表里的条数
        list_hit_rate = n_bad / n_list              # 清单中落在宽表内的占比
        wide_bad_rate = n_bad / len(df) if len(df) else 0.0  # 宽表内被标坏的占比（口径校验信号）
        if list_hit_rate < 0.5:
            if wide_bad_rate >= 0.005:
                # 宽表内坏客户占比正常 → join 已生效，只是清单覆盖人群更大，属正常子集
                print(
                    f"[提示] 坏客户清单覆盖的人群大于本次分析的宽表（疑似正常子集关系）："
                    f"清单共 {n_list} 条，落在宽表内 {n_bad} 条（{list_hit_rate*100:.1f}%）、"
                    f"落在宽表外 {n_out} 条；宽表内坏客户占比 {wide_bad_rate*100:.2f}%。"
                    f"若宽表本就是清单人群的一个子集，可忽略本提示。",
                    file=sys.stderr,
                )
            else:
                # 宽表内几乎没人被标坏 → 更像主键对不上
                print(
                    f"[警告] 坏客户清单与宽表主键几乎对不上："
                    f"清单共 {n_list} 条，仅 {n_bad} 条落在宽表内、{n_out} 条落在宽表外，"
                    f"宽表内坏客户占比仅 {wide_bad_rate*100:.2f}%；"
                    f"请确认两边主键格式是否一致（前导零/空格/编码差异等）。",
                    file=sys.stderr,
                )
    else:
        if target_col not in df.columns:
            raise ValueError(
                f"未提供 bad_customer_path，且宽表不含 {target_col!r} 列；"
                f"请补充坏客户清单，或确认宽表已含目标列。"
            )
        n_na = int(df[target_col].isna().sum())
        if n_na > 0:
            raise ValueError(
                f"宽表目标列 {target_col!r} 含 {n_na} 条缺失值；"
                f"请先处理缺失，或改用坏客户清单（bad_customer_path）打标。"
            )
        numeric = pd.to_numeric(df[target_col], errors='coerce')
        if numeric.isna().any() or not numeric.isin([0, 1]).all():
            uniques = df[target_col].unique()[:10].tolist()
            raise ValueError(
                f"宽表目标列 {target_col!r} 取值必须为 0/1 且 1=坏客户；"
                f"实际取值（最多前 10 个）：{uniques}。"
                f"请先转换编码（如 '是/否'、1/2），或改用坏客户清单打标。"
            )
        df[target_col] = numeric.astype(int)
        if df[target_col].nunique() < 2:
            uniq = df[target_col].unique().tolist()
            raise ValueError(
                f"宽表目标列 {target_col!r} 只有单一取值 {uniq}（全 0 或全 1），"
                f"无法做有监督分析；请检查目标列定义或坏客户口径。"
            )

    if filter:
        for col, rule in filter.items():
            if col not in df.columns:
                continue
            if 'exclude' in rule:
                df = df[~df[col].astype(str).isin([str(v) for v in rule['exclude']])]
            if 'include' in rule:
                df = df[df[col].astype(str).isin([str(v) for v in rule['include']])]
            # 数值范围过滤（强制 to_numeric，非数值会变 NaN 而被自动过滤掉）
            if any(k in rule for k in ('min', 'max', 'range')):
                numeric = pd.to_numeric(df[col], errors='coerce')
                lo = rule.get('min')
                hi = rule.get('max')
                if 'range' in rule:
                    rng = rule['range']
                    if not (isinstance(rng, (list, tuple)) and len(rng) == 2):
                        raise ValueError(
                            f"filter[{col!r}].range 必须是 [min, max] 形式的二元数组，实际：{rng!r}"
                        )
                    lo = rng[0] if lo is None else lo
                    hi = rng[1] if hi is None else hi
                if lo is not None:
                    df = df[numeric >= lo]
                    numeric = numeric.loc[df.index]
                if hi is not None:
                    df = df[numeric <= hi]
            if rule.get('drop_na'):
                df = df[df[col].notna()]

    excluded = {id_col, target_col}
    if extra_exclude_cols:
        excluded.update(extra_exclude_cols)
    if exclude_features:
        excluded.update(exclude_features)

    feature_cols = [
        c for c in df.select_dtypes(include='number').columns
        if c not in excluded and df[c].std(skipna=True) > min_std
    ]

    # 特征卫生闸（见 feature_sanity.py）：先剔语义残缺的资质哑变量名（如上游
    # one-hot 用取值拼出的「是_非」类列名），再对二值特征做完全相同/互补去重。
    # 名字闸在前，保证互补对里存活的是「正名」那一列，而不是碰运气按列序。
    # 只清理入池清单，不动 df；每条剔除显式记原因。
    dropped = find_degenerate_qual_names(feature_cols)
    dropped.update(find_redundant_binary_features(
        df, [c for c in feature_cols if c not in dropped]))
    if dropped:
        lines = '\n'.join(f"  - {c}: {why}" for c, why in dropped.items())
        print(
            f"[提示] 特征卫生闸剔除 {len(dropped)} 列（列仍保留在 df 中，仅不入特征清单）：\n{lines}",
            file=sys.stderr,
        )
        feature_cols = [c for c in feature_cols if c not in dropped]

    return df.reset_index(drop=True), feature_cols
