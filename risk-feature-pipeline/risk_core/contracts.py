# -*- coding: utf-8 -*-
"""risk_core.contracts —— 磁盘契约的单一真源（DECOUPLING-DESIGN §5）。

拆分后「写点」与「读点」分属不同 skill，本模块把它们之间的隐式约定（列名 /
dtype / 元信息白名单 / 文件名模板 / wire schema / 指纹 / 状态目录派生）固化为
**唯一权威定义**：所有生产/消费方只从这里 import，杜绝各处自拼键名/列名/路径。

依赖方向：contracts 是叶子（只依赖 stdlib + pandas + 同包 paths），任何上层
（risk_mining / 各子 skill / 组合根）都可向下依赖它；它不反向依赖任何上层。

分节对应设计文档：
  §5.1 prepared.csv（含前导零 dtype 契约）      —— PREPARED_* + read/write_prepared
  §5.2 features.json（15 键 + 子 schema）        —— FEATURES_JSON_KEYS + read/write_features_json
  §5.3 _intermediate wire（analyze→export 通道） —— INTERMEDIATE_* + dump/load_intermediate
  §5.4 对外 results 列名 + 元信息白名单          —— GENERIC_COLS / *_META_COLS / COL_*
  §5.5 数据集指纹（schema_version=2）             —— FINGERPRINT_* + dataset_fingerprint
  §5.6 .pipeline_state.json 目录/键              —— STATE_* / LEVEL_ORDER / state_results_dir
  §5.7 YAML 覆盖语义 + 产物文件名模板            —— RESULT_FILE_TEMPLATE / RULE_TREE_PKL_TEMPLATE

⚠ 收敛进度（契约先行 P6：本模块在阶段 1 建立为单一真源，各消费方分阶段接入）：
  - cli_io（wire/指纹/features.json 函数）已在阶段 1 退化为本模块的再导出 shim。
  - export 装配的写端白名单（report_analysis.build_corr/lr_export）在阶段 3 接入。
  - data_prep 的 prepared.csv / features.json 读写在阶段 6 接入（顺手修 §5.1 前导零 bug）。
  - visualization / threshold_explore 的文件名拼读在阶段 7 接入。
  - pipeline_state 的 state 目录派生在阶段 9 接入。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd


# =============================================================================
# 通用工具
# =============================================================================
def now_iso() -> str:
    """当前时间的本地时区 ISO 8601 字符串（历史 utc_now_iso 误名，统一为 now_iso）。"""
    return datetime.now(timezone.utc).astimezone().isoformat()


def _safe_filename(s: str) -> str:
    """把分群维度名转成可作为文件名的 token（中文保留）。"""
    return re.sub(r'[\\/:\s]+', '_', str(s))


# =============================================================================
# §5.1 prepared.csv —— 主键 str dtype 契约（修前导零经 CSV 往返丢失的潜在 bug）
# =============================================================================
PREPARED_CSV_ENCODING = 'utf-8-sig'
PREPARED_CSV_INDEX = False
PREPARED_ID_DTYPE = str  # 读回时强制主键为 str，避免带前导零的客户编号被推断成数值


def write_prepared(df: pd.DataFrame, path) -> None:
    """落 prepared.csv（§5.1 唯一写点）：utf-8-sig、index=False。"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=PREPARED_CSV_INDEX, encoding=PREPARED_CSV_ENCODING)


def read_prepared(path, id_col: Optional[str] = None) -> pd.DataFrame:
    """读 prepared.csv（§5.1 唯一读点）：强制 ``dtype={id_col: str}`` 保住前导零。

    失败场景（此契约要修的 bug）：带前导零的客户编号经 CSV 往返被推断成 int →
    与客户宽表 merge 0 命中 → trigger 匹配率 < 阈值 → 全 0 预警名单。

    id_col=None（features.json 缺失/损坏拿不到主键名）时退化为普通读——
    此时前导零保护不生效，但不阻断只读路径；pandas 对 dtype 里不存在的列名
    静默忽略，故传入的 id_col 不在 CSV 中也安全。
    """
    dtype = {id_col: PREPARED_ID_DTYPE} if id_col else None
    return pd.read_csv(path, encoding=PREPARED_CSV_ENCODING, dtype=dtype)


# =============================================================================
# §5.2 features.json —— 15 键 + confirmation / column_mapping_audit 子 schema
# =============================================================================
FEATURES_JSON_KEYS = (
    'feature_cols',
    'id_col',
    'target_col',
    'wide_source_path',
    'wide_source_fingerprint',
    'bad_customer_path',
    'filter_applied',
    'exclude_features',
    'n_rows',
    'n_bad',
    'n_features',
    'created_at',
    'confirmation',
    'column_mapping_audit',
    'preflight_skipped',
)
# confirmation 子 schema（prepare 三种确认模式的存证）
FEATURES_CONFIRMATION_KEYS = ('mode', 'id_col', 'target_col', 'target_positive')
# column_mapping_audit 子 schema（_preflight_column_mapping 产出；analyze 读 segment_dims.actual/expected）：
#   三组列 × 每组四键。analyze 靠 segment_dims.hit_rate 判是否 preflight 阻断，读 actual/expected 生成诊断 hint。
FEATURES_AUDIT_GROUPS = ('segment_dims', 'credit_category_dims', 'amount_cols')
FEATURES_AUDIT_GROUP_KEYS = ('expected', 'actual', 'missing', 'hit_rate')


def write_features_json(path, info: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False, indent=2, default=str)


def read_features_json(path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# =============================================================================
# §5.3 _intermediate/ —— analyze→export 唯一数据通道的 wire schema
# =============================================================================
MANIFEST_SCHEMA_VERSION = 1
INTERMEDIATE_CSV_ENCODING = 'utf-8-sig'
# manifest.json 键集合（⚠ target_col 只在 manifest；results dict 不含它）
INTERMEDIATE_MANIFEST_KEYS = (
    'schema_version', 'project_name', 'target_col', 'category_dims', 'qual_dims',
    'feature_cols', 'raw_features', 'derived_features', 'wide_dim_keys', 'created_at',
)
# 简单 DataFrame（长格式或元信息）→ {key}.csv（index=False）
INTERMEDIATE_SIMPLE_KEYS = (
    'iv_full',
    'iv_group_all',
    'reliability_summary',
    'feature_set_comparison',
    'corr_long',
    'lr_coef_long',
    'lr_auc_long',
    'comprehensive',
)
# 宽矩阵 dict[dim → DataFrame] → {prefix}_{safe(dim)}.csv（index=True，回读 index_col=0）
INTERMEDIATE_WIDE_DICT_KEYS = (
    ('corr_wide', 'corr_results'),
    ('lr_coef_wide', 'lr_coef_results'),
    ('lr_auc', 'lr_auc_results'),
    ('meta', 'meta_results'),
)
# qual_dims 非空时 wide_dim_keys 追加此特判键
QUAL_WIDE_DIM_KEY = '资质标签'

# 兼容旧内部名（本模块内的函数体沿用；外部请用大写公有名）
_SIMPLE_KEYS = INTERMEDIATE_SIMPLE_KEYS
_WIDE_DICT_KEYS = INTERMEDIATE_WIDE_DICT_KEYS


def dump_intermediate(
    results: dict,
    intermediate_dir: str,
    *,
    project_name: str,
    target_col: str,
    category_dims,
    qual_dims,
    feature_cols,
    raw_features=None,
    derived_features=None,
) -> None:
    """把 run_generic_pipeline 返回的 results 拆成多 CSV + manifest.json。"""
    os.makedirs(intermediate_dir, exist_ok=True)

    # 简单 DataFrame
    for key in _SIMPLE_KEYS:
        df = results.get(key)
        if df is None or not hasattr(df, 'to_csv') or df.empty:
            continue
        df.to_csv(
            os.path.join(intermediate_dir, f'{key}.csv'),
            index=False, encoding=INTERMEDIATE_CSV_ENCODING,
        )

    # 宽矩阵 dict
    for prefix, key in _WIDE_DICT_KEYS:
        wide_dict = results.get(key) or {}
        for dim, wide in wide_dict.items():
            if wide is None or not hasattr(wide, 'to_csv') or wide.empty:
                continue
            wide.to_csv(
                os.path.join(intermediate_dir, f'{prefix}_{_safe_filename(dim)}.csv'),
                encoding=INTERMEDIATE_CSV_ENCODING, index=True,
            )

    manifest = {
        'schema_version': MANIFEST_SCHEMA_VERSION,
        'project_name': project_name,
        'target_col': target_col,
        'category_dims': list(category_dims or []),
        'qual_dims': list(qual_dims or []),
        'feature_cols': list(feature_cols or []),
        'raw_features': list(raw_features or []),
        'derived_features': list(derived_features or []),
        'wide_dim_keys': sorted(set([
            d
            for _, k in _WIDE_DICT_KEYS
            for d in (results.get(k) or {}).keys()
        ])),
        'created_at': now_iso(),
    }
    with open(os.path.join(intermediate_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def load_intermediate(intermediate_dir: str) -> Tuple[dict, dict]:
    """从 _intermediate/ 重建 minimal results dict + manifest。"""
    if not os.path.isdir(intermediate_dir):
        raise FileNotFoundError(f'_intermediate/ 目录不存在: {intermediate_dir}')

    manifest_path = os.path.join(intermediate_dir, 'manifest.json')
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(f'manifest.json 不存在: {manifest_path}')

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    results: dict = {
        'project_name': manifest['project_name'],
        'feature_cols': manifest.get('feature_cols', []),
        'raw_features': manifest.get('raw_features', []),
        'derived_features': manifest.get('derived_features', []),
        'category_dims': manifest.get('category_dims', []),
        'qual_dims': manifest.get('qual_dims', []),
    }

    for key in _SIMPLE_KEYS:
        path = os.path.join(intermediate_dir, f'{key}.csv')
        if os.path.exists(path):
            results[key] = pd.read_csv(path, encoding=INTERMEDIATE_CSV_ENCODING)

    wide_dim_keys = manifest.get('wide_dim_keys') or list(manifest.get('category_dims', []))
    if manifest.get('qual_dims') and QUAL_WIDE_DIM_KEY not in wide_dim_keys:
        wide_dim_keys = wide_dim_keys + [QUAL_WIDE_DIM_KEY]

    for prefix, key in _WIDE_DICT_KEYS:
        wide_dict = {}
        for dim in wide_dim_keys:
            path = os.path.join(intermediate_dir, f'{prefix}_{_safe_filename(dim)}.csv')
            if os.path.exists(path):
                wide_dict[dim] = pd.read_csv(path, encoding=INTERMEDIATE_CSV_ENCODING, index_col=0)
        if wide_dict:
            results[key] = wide_dict

    return results, manifest


# =============================================================================
# §5.4 对外 results 产物列名（= 跨 skill 读契约）+ 元信息列白名单
# =============================================================================
# 通用三列（A4 后统一对外）
COL_FEATURE = '特征'
COL_SEG_DIM = '分群维度'
COL_SEG_NAME = '分群名称'
GENERIC_COLS = (COL_FEATURE, COL_SEG_DIM, COL_SEG_NAME)

# 完整列名常量（query/visualization/export 硬依赖；改任一列名会击穿读取路径）
COL_IV = 'IV值'
COL_CORR = '相关系数'
COL_ABS_CORR = '|相关系数|'
COL_LR_COEF = '系数'
COL_ABS_LR_COEF = '|系数|'
COL_AUC = 'AUC'
COL_AUC_TYPE = 'AUC类型'
COL_N_SAMPLES = '样本数'
COL_N_BAD = '坏客户数'
COL_BAD_RATE = '坏客户率'
COL_IV_CREDIBILITY = 'IV可信度'
IV_CREDIBLE = '可信'  # report_analysis 判 == '可信'

# 写端元信息白名单（report_analysis.build_corr_export / build_lr_export；阶段 3 接入）
CORR_EXPORT_META_COLS = ['分群维度', '分群名称', '样本数', '坏客户数', '坏客户率']
LR_EXPORT_META_COLS = ['分群维度', '分群名称', 'AUC', 'AUC类型', '样本数', '坏客户数']
# 读端元信息白名单（results_loader._melt_wide_to_long；须 ⊇ 上面两个写端列表的并集）
KNOWN_META_COLS = {
    '分群维度', '分群名称', '分群类型', '分群',
    '样本数', '坏客户数', '坏客户率',
    'AUC', 'AUC类型',
}

# 历史旧列名 → A4 标准列名（读取时归一化，仅改返回 DataFrame，不改盘上文件）
LEGACY_COL_RENAMES = {
    '特征名称': '特征',
    '分群值': '分群名称',
}


# =============================================================================
# §5.5 数据集指纹（schema_version=2：head+tail 采样哈希 + size + mtime）
# =============================================================================
FINGERPRINT_SCHEMA_VERSION = 2
FINGERPRINT_HEAD_BYTES = 256 * 1024
FINGERPRINT_TAIL_BYTES = 256 * 1024
_FP_HEAD_BYTES = FINGERPRINT_HEAD_BYTES  # 兼容旧内部名
_FP_TAIL_BYTES = FINGERPRINT_TAIL_BYTES


def dataset_fingerprint(path: str) -> dict:
    """返回 头+尾 采样哈希 + size + mtime 的指纹（schema_version=2）。

    - sha256_head: 前 256KB，捕获表头/前段 schema 变更
    - sha256_tail: 尾 256KB，捕获「宽表追加新客户」（老实现只看前 1MB 会漏判）
    - size_bytes + mtime: 兜底
    - schema_version=2: 与老格式（sha256_first_1mb + size_bytes）区分，
      pipeline_state._fingerprint_matches 据此选比对策略
    """
    size = os.path.getsize(path)
    mtime = os.path.getmtime(path)
    with open(path, 'rb') as f:
        head_chunk = f.read(_FP_HEAD_BYTES)
        if size > _FP_HEAD_BYTES + _FP_TAIL_BYTES:
            f.seek(-_FP_TAIL_BYTES, os.SEEK_END)
            tail_chunk = f.read(_FP_TAIL_BYTES)
        else:
            # 文件 ≤ head+tail：尾部会与头重叠，置空避免重复计算
            tail_chunk = b''
    return {
        'schema_version': FINGERPRINT_SCHEMA_VERSION,
        'path': str(path),
        'sha256_head': hashlib.sha256(head_chunk).hexdigest(),
        'sha256_tail': hashlib.sha256(tail_chunk).hexdigest(),
        'size_bytes': size,
        'mtime': mtime,
    }


# =============================================================================
# §5.6 .pipeline_state.json —— 目录派生 + 键 + Level 序
# =============================================================================
STATE_FILENAME = '.pipeline_state.json'
STATE_SCHEMA_VERSION = 1
STATE_TOP_KEYS = ('project_name', 'current_level', 'known_datasets', 'history')
LEVEL_ORDER = ['前置', '过渡态', 'Level 1', 'Level 2', 'Level 3']


def state_results_dir(project: str, *, project_root: str) -> str:
    """.pipeline_state.json 所在的结果目录派生（§5.6 单一真源；阶段 9 由 pipeline_state 接入）。

    设 RISK_OUTPUT_ROOT 时落到写盘根，否则落项目根，**均无「征信」前缀**。
    ⚠ 已知偏差：credit/gsfc 结果目录带「征信」/「工商财务」前缀，而此处无前缀——
    对应 DECOUPLING-DESIGN §9 阶段 9 修复；本函数刻意保留现状以待统一。
    """
    from .paths import get_output_root, ENV_OUTPUT_ROOT
    if os.environ.get(ENV_OUTPUT_ROOT):
        return os.path.join(get_output_root(), 'data', 'results', project)
    return os.path.join(project_root, 'data', 'results', project)


# =============================================================================
# §5.7 产物文件名模板（visualization/threshold_explore 除走 loader 外还直接拼读）
# =============================================================================
RESULT_FILE_TEMPLATE = '{project}_{type}.csv'      # 全部对外 CSV
RULE_TREE_PKL_TEMPLATE = 'rule_tree_{safe_dim}.pkl'  # _intermediate/ 内规则树 pkl
# YAML 覆盖语义（config_loader._deep_merge / _expand）——写进契约以防多银行误解：
#   dict 递归深合并、list 整体替换（非并集）；所有字符串值加载时做 ${VAR}/~ 展开。
YAML_LIST_MERGE_IS_REPLACE = True
