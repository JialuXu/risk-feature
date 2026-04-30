# -*- coding: utf-8 -*-
"""
轻量级"宽表 + 坏客户清单 → 可喂给管线的 df"合成器。

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
- 只做纯函数式的数据整形，不写盘、不跑分析
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd


def _read_csv_robust(path: str) -> pd.DataFrame:
    """兼容 utf-8-sig / utf-8 / gbk 的读取。"""
    for enc in ('utf-8-sig', 'utf-8', 'gbk', 'gb18030'):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    # 最后兜底
    return pd.read_csv(path, encoding='latin1')


def prepare_df(
    wide_path: str,
    bad_customer_path: Optional[str] = None,
    *,
    id_col: str = '客户编号',
    target_col: str = 'is_bad',
    bad_id_col: Optional[str] = None,
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
    df = _read_csv_robust(wide_path)

    if bad_customer_path is not None:
        bad_df = _read_csv_robust(bad_customer_path)
        key = bad_id_col or id_col
        if key not in bad_df.columns:
            raise ValueError(f"坏客户清单缺少主键列 {key!r}；实际列：{list(bad_df.columns)}")
        if id_col not in df.columns:
            raise ValueError(f"宽表缺少主键列 {id_col!r}；实际列：{list(df.columns)[:20]}...")
        bad_set = set(bad_df[key].astype(str))
        df[target_col] = df[id_col].astype(str).isin(bad_set).astype(int)
    else:
        if target_col not in df.columns:
            raise ValueError(
                f"未提供 bad_customer_path，且宽表不含 {target_col!r} 列；"
                f"请补充坏客户清单，或确认宽表已含目标列。"
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

    return df.reset_index(drop=True), feature_cols
