# -*- coding: utf-8 -*-
"""
风险特征分析流水线 - 共享配置（唯一数值来源）

所有模块通过 from risk_core.config import ... 引用此文件。
配置值从 risk_core/config/default.yaml 和 risk_core/config/column_mapping.yaml 加载，
Python 接口与改造前完全一致，保证向后兼容。
"""
import os

import numpy as np

from . import paths as _paths
from .config_loader import load_config, load_column_mapping

# =============================================================================
# 从 YAML 加载配置（随包分发的 default.yaml / column_mapping.yaml；单行场景不支持
# 运行时覆盖——适配某份数据走 CLI flag，长期接入新银行属开发仓库维护动作）
# =============================================================================
_cfg = load_config()
_mapping = load_column_mapping()

# =============================================================================
# 数据路径配置 - 相对路径，基于项目根目录
# =============================================================================
DATA_CONFIG = {
    '客户信息': _cfg['data']['raw']['customer_info'],
    '工商变更': _cfg['data']['raw']['business_change'],
    '财务数据': _cfg['data']['processed']['financial'],
    '产业数据': _cfg['data']['processed']['industry'],
    '坏客户标记': _cfg['data']['raw']['bad_label'],
}

# =============================================================================
# 输出路径配置（YAML 提供相对路径）
#
# 不在 import 时冻结：下列常量经模块级 __getattr__（PEP 562）**每次访问时**按当时的
# RISK_OUTPUT_ROOT 解析——
#   - 未设 RISK_OUTPUT_ROOT：返回相对路径，调用方 os.path.join(project_root, X) 照旧；
#   - 设了 RISK_OUTPUT_ROOT：返回 <output_root>/X 绝对路径，os.path.join 短路返回自身。
# 因此进程内先 import 后设 env 也生效。注意 ``from risk_core.config import RESULTS_DIR``
# 会把**那一刻**的值绑定到调用方名字上——需要随 env 变化的代码请在调用时读
# ``risk_core.config.RESULTS_DIR``（或直接用 risk_core.paths.results_dir()）。
# =============================================================================
def _resolve_output_path(rel: str) -> str:
    rel = rel.rstrip('/')
    if os.environ.get(_paths.ENV_OUTPUT_ROOT):
        return os.path.join(_paths.get_output_root(), rel)
    return rel


_OUTPUT_PATH_RELS = {
    # 征信链路
    'RESULTS_DIR_CREDIT': _cfg['output']['results_credit'],
    'OUTPUT_DIR_CREDIT': _cfg['output']['final_credit'],
    # 工商财务链路（OUTPUT_DIR / FINAL_OUTPUT_DIR 为向后兼容别名）
    'RESULTS_DIR_GSFC': _cfg['output']['results_gsfc'],
    'OUTPUT_DIR_GSFC': _cfg['output']['final_gsfc'],
    'OUTPUT_DIR': _cfg['output']['results_gsfc'],
    'FINAL_OUTPUT_DIR': _cfg['output']['final_gsfc'],
    # 通用链路
    'RESULTS_DIR': _cfg['output'].get('results', 'data/results'),
    'OUTPUT_DIR_GENERIC': _cfg['output'].get('final', 'output'),
}
OUTPUT_PATH_NAMES = frozenset(_OUTPUT_PATH_RELS)


def __getattr__(name):
    if name in _OUTPUT_PATH_RELS:
        return _resolve_output_path(_OUTPUT_PATH_RELS[name])
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


# =============================================================================
# 分群维度配置
# =============================================================================
_seg = _cfg['segment_dims']
SEGMENT_DIMS = {
    '行业': _seg['industry'],
    '企业性质': _seg['nature'],
    '控股类型': _seg['holding_type'],
    '所属分行': _seg['branch'],
}

# =============================================================================
# 授信总金额分层配置（单位：元）
# =============================================================================
_bin_thresholds = _cfg['credit_bins']['thresholds']
CREDIT_BINS = _bin_thresholds + [np.inf]
CREDIT_LABELS = _cfg['credit_bins']['labels']

# 腰部企业定义
WAIST_MIN = _cfg['waist']['min']
WAIST_MAX = _cfg['waist']['max']
WAIST_HIGH_RATINGS = _cfg['waist']['high_ratings']

# =============================================================================
# 宽表合并：财务侧表与客户信息重复列（避免 merge 产生 _x/_y）
# =============================================================================
FINANCE_MERGE_DUP_COLS = _mapping.get('finance_merge_dup_cols', [])

# =============================================================================
# 分维度分析配置
# =============================================================================
_dim_cfg = _cfg.get('dimension_config', {})
DIMENSION_CONFIG = {}
_DIM_KEY_MAP = {
    'business_change': '工商变更',
    'financial': '财务指标',
}
for _yaml_key, _display_name in _DIM_KEY_MAP.items():
    if _yaml_key in _dim_cfg:
        _d = _dim_cfg[_yaml_key]
        entry = {
            'data_key': _d.get('data_key', ''),
            'description': _d.get('description', ''),
        }
        if 'exclude_cols' in _d:
            entry['exclude_cols'] = _d['exclude_cols']
        if 'exclude_patterns' in _d:
            entry['exclude_patterns'] = _d['exclude_patterns']
        DIMENSION_CONFIG[_display_name] = entry

# =============================================================================
# IV 值筛选阈值配置
# =============================================================================
_iv_levels = _cfg['iv']['prediction_levels']
IV_THRESHOLD = {
    'weak': _iv_levels['weak'],
    'medium': _iv_levels['medium'],
    'strong': _iv_levels['strong'],
}

IV_SELECT_THRESHOLD = _cfg['iv']['select_threshold']

# =============================================================================
# 样本量阈值统一参考表（对齐 rules.mdc；为唯一数值来源）
# =============================================================================
_thr = _cfg['thresholds']
SAMPLE_THRESHOLDS = {
    'MIN_SAMPLES': _thr['min_samples'],
    'MIN_BAD_SAMPLES': _thr['min_bad_samples'],
    'MIN_BAD_CORR': _thr['min_bad_corr'],
    'MIN_GOOD_CORR': _thr['min_good_corr'],
    'MIN_BAD_LR': _thr['min_bad_lr'],
    'MIN_GOOD_LR': _thr['min_good_lr'],
    'MIN_SAMPLES_CV': _thr['min_samples_cv'],
    'MIN_BAD_CV': _thr['min_bad_cv'],
}

# 快捷变量（从 SAMPLE_THRESHOLDS 派生，供直接 import 使用）
MIN_SAMPLES = SAMPLE_THRESHOLDS['MIN_SAMPLES']
MIN_BAD_SAMPLES = SAMPLE_THRESHOLDS['MIN_BAD_SAMPLES']

# =============================================================================
# IV 计算可信度配置
# =============================================================================
IV_SUSPECT_THRESHOLD = _cfg['iv']['suspect_threshold']

_adaptive = _cfg['iv']['adaptive_bins']
ADAPTIVE_BINS_SAMPLE_THRESHOLD = _adaptive['sample_threshold']
ADAPTIVE_BINS_BAD_THRESHOLD = _adaptive['bad_threshold']
ADAPTIVE_BINS_MIN = _adaptive['min_bins']

WOE_CAP = _cfg['iv']['woe_cap']

# IV 可信度分级阈值（单一源）
_credibility = _cfg['iv'].get('credibility', {})
IV_CREDIBILITY_MIN_BAD_STRICT = _credibility.get('min_bad_strict', 20)
IV_CREDIBILITY_UNRELIABLE_IV_IF_LOW_BAD = _credibility.get('unreliable_iv_if_low_bad', 0.5)
IV_CREDIBILITY_LOW_SAMPLE_N = _credibility.get('low_sample_n', 200)
IV_CREDIBILITY_REFERENCE_IV = _credibility.get('reference_iv', 1.0)

# 全量 IV「预测能力」分档：过强起点（单一源）
IV_PREDICTION_OVERSTRONG_MIN = _cfg['iv'].get('prediction_overstrong_min', 0.5)

# =============================================================================
# 规则挖掘配置（risk_rule_mining 专用）
# =============================================================================
_rm = _cfg.get('rule_mining', {})
RULE_MINING_CONFIG = {
    'max_depth': _rm.get('max_depth', 3),
    'min_samples_leaf_ratio': _rm.get('min_samples_leaf_ratio', 0.05),
    'min_bad_in_leaf': _rm.get('min_bad_in_leaf', 5),
    'min_coverage': _rm.get('min_coverage', 0.01),
    'min_lift': _rm.get('min_lift', 1.5),
    'top_k_per_segment': _rm.get('top_k_per_segment', 10),
    'holdout_ratio': _rm.get('holdout_ratio', 0.3),
    'holdout_min_bad': _rm.get('holdout_min_bad', 10),
    'bootstrap_n': _rm.get('bootstrap_n', 200),
    'stability_min_valid_ratio': _rm.get('stability_min_valid_ratio', 0.6),
    'tree_criterion': _rm.get('tree_criterion', 'gini'),
    'class_weight': _rm.get('class_weight', 'balanced'),
}

# =============================================================================
# 征信特征分析专用配置
# =============================================================================
CREDIT_CONFIG = {
    # 数据路径
    'data': {
        '征信数据': _cfg['data']['raw']['credit_report'],
        '客户信息': _cfg['data']['raw']['customer_info'],
        '产业数据': _cfg['data']['processed']['industry'],
        '坏客户标记': _cfg['data']['raw']['bad_label'],
    },
    # prepare_credit_wide_table：金额列清洗与千分位转数值时保留为 object 的列
    'credit_prep_amount_cols': _mapping.get('amount_cols', []),
    'credit_prep_object_keep_cols': _mapping.get('numeric_skip_cols', []),
    # 输出文件前缀
    'project_name': '征信特征分析',
    # 类别型分群维度（合并客户信息与产业数据）
    'category_dims': _mapping.get('credit_category_dims', []),
    # 原始特征（数量型，来自征信报告原始字段）
    'raw_features': _mapping.get('credit_raw_features', []),
    # 衍生特征（比值/占比型，消除规模影响）
    'derived_features': _mapping.get('credit_derived_features', []),
}

# =============================================================================
# 列名常量（通过 ColumnMapper 从 YAML 配置生成）
# 所有模块通过 from risk_core.config import * 获得这些常量，
# 替代脚本中硬编码的字段名字符串，使多银行适配生效。
# =============================================================================
from .column_mapper import ColumnMapper

_mapper = ColumnMapper()

COL_CUSTOMER_ID = _mapper.customer_id
COL_CUSTOMER_ID_STR = _mapper.customer_id_str
COL_TARGET = _mapper.target
COL_REPORT_DATE = _mapper.report_date
COL_CHANGE_DATE = _mapper.change_date
COL_QUAL_PREFIX = _mapper.qual_prefix
COL_INDUSTRY_DATA_COLS = _mapper.industry_data_cols
COL_SEGMENT_DIMS_DICT = _mapper.segment_dims_dict
COL_SEGMENT_DIMS = _mapper.segment_dims
COL_CREDIT_CATEGORY_DIMS = _mapper.credit_category_dims
COL_SEGMENT_IV_LIMITS = _mapper.segment_iv_limits
COL_AMOUNT_COLS = _mapper.amount_cols
COL_NUMERIC_SKIP_COLS = _mapper.numeric_skip_cols
COL_FINANCE_MERGE_DUP_COLS = _mapper.finance_merge_dup_cols
