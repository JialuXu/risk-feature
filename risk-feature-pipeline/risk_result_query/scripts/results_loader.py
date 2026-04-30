# -*- coding: utf-8 -*-
"""
risk-result-query: 读取已导出的风险特征分析结果。

核心 API:
    load_results(project_name, subdir=None) -> Results
    top_features(results, kind, group=None, dim=None, n=15, sign=None) -> DataFrame

不跑任何分析；若结果不存在，抛 FileNotFoundError 由上层决定是否重跑。
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

# 将 risk-feature-pipeline/ 根加入 sys.path（为 prepare_df 等相对导入兜底）
_SKILL_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)

# 搜索顺序：generic → 征信(credit) → 工商财务(gsfc)
# 优先匹配 generic 管线（run_generic_pipeline 导出到 data/results/<project>）
# 若不存在则自动尝试旧有的业务类型子目录（向后兼容）
_SEARCH_BASES = [
    ('data/results', 'output'),            # generic pipeline
    ('data/results/征信', 'output/征信'),   # credit pipeline
    ('data/results/工商财务', 'output/工商财务'),  # gsfc pipeline
]


def _find_project_root(start: Optional[str] = None) -> str:
    """委托到 risk_pipeline.paths.get_project_root（支持 RISK_PROJECT_ROOT）。"""
    from risk_pipeline.paths import get_project_root
    return get_project_root(start=start)


@dataclass
class Results:
    """已加载的分析结果容器。所有 DataFrame 属性缺失时为 None。"""
    project_name: str
    results_dir: str
    output_dir: Optional[str] = None

    iv_full: Optional[pd.DataFrame] = None
    iv_group_all: Optional[pd.DataFrame] = None
    corr_long: Optional[pd.DataFrame] = None
    diff_long: Optional[pd.DataFrame] = None
    lr_coef_long: Optional[pd.DataFrame] = None
    lr_auc_long: Optional[pd.DataFrame] = None
    comprehensive: Optional[pd.DataFrame] = None
    reliability_summary: Optional[pd.DataFrame] = None
    iv_pivot: Optional[pd.DataFrame] = None
    reliability_pivot: Optional[pd.DataFrame] = None
    segment_profiles: Optional[pd.DataFrame] = None
    llm_report: Optional[dict] = None

    loaded_files: list = field(default_factory=list)

    def __repr__(self) -> str:
        loaded = [k for k, v in self.__dict__.items()
                  if isinstance(v, pd.DataFrame) and not v.empty]
        return (f"Results(project={self.project_name!r}, "
                f"loaded={loaded}, files={len(self.loaded_files)})")


def _read_csv_if_exists(path: str) -> Optional[pd.DataFrame]:
    if not os.path.exists(path):
        return None
    for enc in ('utf-8-sig', 'utf-8', 'gbk'):
        try:
            df = pd.read_csv(path, encoding=enc)
            return _normalize_legacy_cols(df)
        except UnicodeDecodeError:
            continue
    return None


def _read_csv_with_fallback(*paths: str) -> Optional[pd.DataFrame]:
    """按顺序尝试多个候选路径，命中第一个存在的；用于 A5 文件改名后的兼容读取。"""
    for p in paths:
        df = _read_csv_if_exists(p)
        if df is not None:
            return df
    return None


# A4 后对外列名标准化为：特征 / 分群维度 / 分群名称
# 历史 CSV 可能存在以下旧列名，读取时统一改名（仅修改返回的 DataFrame，不改盘上文件）
_LEGACY_COL_RENAMES = {
    '特征名称': '特征',
    '分群值': '分群名称',
}


def _normalize_legacy_cols(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return df
    rename = {old: new for old, new in _LEGACY_COL_RENAMES.items() if old in df.columns}
    if rename:
        df = df.rename(columns=rename)
    return df


def _read_json_if_exists(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# 每种导出宽表中已知的非特征列（分群标识 + 样本元信息 + AUC 附加信息）
_KNOWN_META_COLS = {
    '分群维度', '分群名称', '分群类型', '分群',
    '样本数', '坏客户数', '坏客户率',
    'AUC', 'AUC类型',
}


def _melt_wide_to_long(wide: pd.DataFrame,
                       value_name: str,
                       abs_col: Optional[str]) -> pd.DataFrame:
    """把导出的 `特征风险相关性.csv` / `逻辑回归系数.csv` 等宽表重塑为长格式。

    导出 CSV 的列结构：`分群维度, 分群名称, [样本数, 坏客户数, ...metadata], <特征列...>`。
    本函数只把「非元信息列」拿来 melt，其余保持不变。
    """
    if wide is None or wide.empty:
        return pd.DataFrame()

    id_cols = [c for c in ('分群维度', '分群名称') if c in wide.columns]
    if not id_cols:
        # 无法识别的旧导出 → 退化：第一列当分群名称
        wide = wide.rename(columns={wide.columns[0]: '分群名称'})
        wide.insert(0, '分群维度', '未知')
        id_cols = ['分群维度', '分群名称']

    feat_cols = [c for c in wide.columns
                 if c not in id_cols and c not in _KNOWN_META_COLS]
    if not feat_cols:
        return pd.DataFrame()

    long = wide.melt(id_vars=id_cols, value_vars=feat_cols,
                     var_name='特征', value_name=value_name)
    # 数值转换（CSV 里空值会被读为 NaN，文本会导致 abs() 爆炸 → 强转）
    long[value_name] = pd.to_numeric(long[value_name], errors='coerce')
    long = long.dropna(subset=[value_name])

    if abs_col:
        long[abs_col] = long[value_name].abs()
    return long


def _extract_lr_auc_long(lr_wide: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """从 `逻辑回归系数.csv` 抽 AUC 长格式。"""
    if lr_wide is None or lr_wide.empty:
        return None
    needed = [c for c in ('分群维度', '分群名称', 'AUC', 'AUC类型', '样本数', '坏客户数')
              if c in lr_wide.columns]
    if not needed:
        return None
    out = lr_wide[needed].copy()
    if 'AUC' in out.columns:
        out['AUC'] = pd.to_numeric(out['AUC'], errors='coerce')
    return out


def load_results(project_name: str,
                 subdir: Optional[str] = None,
                 project_root: Optional[str] = None,
                 results_base: Optional[str] = None,
                 output_base: Optional[str] = None) -> Results:
    """读取已导出的分析结果。

    Args:
        project_name:  跑管线时传入的 project_name
        subdir:        结果子目录名；默认等于 project_name
        project_root:  手动指定项目根（默认从 CWD 向上找 data/）
        results_base:  data/results 级别的相对路径；None = 自动按优先级搜索
        output_base:   output 级别的相对路径；None = 跟随 results_base 自动选取

    自动搜索顺序（results_base=None 时）：
        1. data/results/<subdir>          ← generic pipeline
        2. data/results/征信/<subdir>     ← credit pipeline（向后兼容）
        3. data/results/工商财务/<subdir> ← gsfc pipeline（向后兼容）

    Returns:
        Results 对象。缺失的文件对应属性为 None，不抛错（除非整个目录不存在）。

    Raises:
        FileNotFoundError: 所有候选路径均不存在；消息列出已尝试的路径。
    """
    root = project_root or _find_project_root()
    subdir = subdir or project_name

    # 确定实际使用的路径
    if results_base is not None:
        _output_base = output_base or results_base.replace('data/results', 'output', 1)
        search_pairs = [(results_base, _output_base)]
    else:
        search_pairs = list(_SEARCH_BASES)

    res_dir = out_dir = None
    for rb, ob in search_pairs:
        candidate = os.path.join(root, rb, subdir)
        if os.path.isdir(candidate):
            res_dir = candidate
            out_dir = os.path.join(root, ob, subdir)
            break

    if res_dir is None:
        tried = [os.path.join(root, rb, subdir) for rb, _ in search_pairs]
        # 列出每个已尝试父目录下的可用子目录，方便 agent 诊断
        hints = []
        for rb, _ in search_pairs:
            parent = os.path.join(root, rb)
            if os.path.isdir(parent):
                hints.append(f"  {parent}: {sorted(os.listdir(parent))}")
        raise FileNotFoundError(
            f"未找到项目 {project_name!r} 的结果目录。\n"
            f"已尝试路径:\n" + "\n".join(f"  {p}" for p in tried) + "\n"
            + ("已有子目录:\n" + "\n".join(hints) if hints else "") + "\n"
            f"提示：若未跑过，请先执行 run_generic_pipeline(..., steps=[..., 'export'])"
        )

    r = Results(project_name=project_name, results_dir=res_dir, output_dir=out_dir)

    def _p(name: str) -> str:
        return os.path.join(res_dir, f'{project_name}_{name}')

    def _po(name: str) -> str:
        return os.path.join(out_dir, f'{project_name}_{name}')

    # A5 文件改名：优先读新名（_全量 / _分群），回退到旧名
    r.iv_full = _read_csv_with_fallback(
        _p('IV分析结果_全量.csv'),
        _p('IV分析结果.csv'),
    )
    r.iv_group_all = _read_csv_with_fallback(
        _p('IV分析结果_分群.csv'),
        _p('IV值分析.csv'),
    )
    r.comprehensive = _read_csv_if_exists(_p('综合特征分析结果.csv'))
    r.reliability_summary = _read_csv_if_exists(_p('IV可信度诊断.csv'))
    r.iv_pivot = _read_csv_if_exists(_p('IV值透视表.csv'))
    r.reliability_pivot = _read_csv_if_exists(_p('IV可信度透视表.csv'))

    corr_wide = _read_csv_if_exists(_p('特征风险相关性.csv'))
    r.corr_long = _melt_wide_to_long(corr_wide, '相关系数', '|相关系数|')

    lr_wide = _read_csv_if_exists(_p('逻辑回归系数.csv'))
    r.lr_coef_long = _melt_wide_to_long(lr_wide, '系数', '|系数|')
    r.lr_auc_long = _extract_lr_auc_long(lr_wide)

    # diff_long（坏-好均值差）未独立落盘；消费方若需要，请用宽表 groupby 自算
    r.diff_long = None

    r.segment_profiles = _read_csv_if_exists(_po('LLM_分群画像.csv'))
    r.llm_report = _read_json_if_exists(_po('LLM报告数据.json'))

    for attr in ('iv_full', 'iv_group_all', 'corr_long', 'lr_coef_long',
                 'lr_auc_long', 'comprehensive', 'reliability_summary',
                 'iv_pivot', 'reliability_pivot', 'segment_profiles', 'llm_report'):
        obj = getattr(r, attr)
        if obj is not None and (not hasattr(obj, 'empty') or not obj.empty):
            r.loaded_files.append(attr)

    return r


def top_features(results: Results,
                 kind: str,
                 group: Optional[str] = None,
                 dim: Optional[str] = None,
                 n: int = 15,
                 sign: Optional[str] = None) -> pd.DataFrame:
    """统一的 top-N 查询。

    Args:
        kind:   'iv' | 'iv_group' | 'corr' | 'lr'
        group:  分群名称（如 '小型企业'），不传则不过滤
        dim:    分群维度（如 '企业规模'），不传则不过滤
        n:      取前多少条
        sign:   仅对 kind='lr' 生效：'positive' / 'negative' / None（按 |系数| 取）

    Returns:
        已按相应指标降序、head(n) 后的 DataFrame。
    """
    if kind == 'iv':
        if dim or group:
            import warnings
            warnings.warn(
                f"kind='iv' 走全量 IV 表，不接受 dim/group 参数（dim={dim!r}, group={group!r} 已被忽略）。"
                f"如需分群 IV top-N，请改用 kind='iv_group'。",
                UserWarning,
                stacklevel=2,
            )
        df = results.iv_full
        if df is None or df.empty:
            return pd.DataFrame()
        return df.sort_values('IV值', ascending=False).head(n)

    if kind == 'iv_group':
        df = results.iv_group_all
        if df is None or df.empty:
            return pd.DataFrame()
        if dim:
            df = df[df['分群维度'] == dim]
        if group:
            df = df[df['分群名称'] == group]
        return df.sort_values('IV值', ascending=False).head(n)

    if kind == 'corr':
        df = results.corr_long
        if df is None or df.empty:
            return pd.DataFrame()
        if dim:
            df = df[df['分群维度'] == dim]
        if group:
            df = df[df['分群名称'] == group]
        return df.sort_values('|相关系数|', ascending=False).head(n)

    if kind == 'lr':
        df = results.lr_coef_long
        if df is None or df.empty:
            return pd.DataFrame()
        if dim:
            df = df[df['分群维度'] == dim]
        if group:
            df = df[df['分群名称'] == group]
        if sign == 'positive':
            return df.sort_values('系数', ascending=False).head(n)
        if sign == 'negative':
            return df.sort_values('系数', ascending=True).head(n)
        return df.sort_values('|系数|', ascending=False).head(n)

    raise ValueError(f"未知 kind: {kind!r}；支持 iv / iv_group / corr / lr")
