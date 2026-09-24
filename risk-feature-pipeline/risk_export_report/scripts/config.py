# -*- coding: utf-8 -*-
"""
risk_export_report 配置

公共配置统一从 risk_core.config 导入，本文件仅保留模块专属配置。
"""

# 导入全部公共配置（DATA_CONFIG, SEGMENT_DIMS, CREDIT_BINS, SAMPLE_THRESHOLDS 等）
from risk_core.config import *  # noqa: F401,F403

# =============================================================================
# 模块专属配置：导出报告
# =============================================================================
# 输出路径在**调用时**解析（遵循当时的 RISK_OUTPUT_ROOT），不在 import 时冻结。
from risk_core import config as _core_cfg  # noqa: E402

_PIPELINE_PATH_NAMES = {
    'credit': ('RESULTS_DIR_CREDIT', 'OUTPUT_DIR_CREDIT'),   # 链路 A（征信）
    'gsfc': ('RESULTS_DIR_GSFC', 'OUTPUT_DIR_GSFC'),         # 链路 B（工商财务）
    'generic': ('RESULTS_DIR', 'OUTPUT_DIR_GENERIC'),        # 通用宽表链路
}


def pipeline_paths(kind: str = 'credit') -> dict:
    """返回某链路的 {'results_rel', 'output_rel'}（调用时解析）。"""
    res_name, out_name = _PIPELINE_PATH_NAMES[kind]
    return {'results_rel': getattr(_core_cfg, res_name),
            'output_rel': getattr(_core_cfg, out_name)}


def __getattr__(name):
    """PEP 562：RESULTS_DIR_* / OUTPUT_DIR_* 与旧的 *_PIPELINE_PATHS 按访问时的 env 解析。"""
    if name in _core_cfg.OUTPUT_PATH_NAMES:
        return getattr(_core_cfg, name)
    if name == 'CREDIT_PIPELINE_PATHS':
        return pipeline_paths('credit')
    if name == 'GENERIC_PIPELINE_PATHS':
        return pipeline_paths('generic')
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


# 链路 A LLM JSON「报告目标」模板，{pname} 替换为 project_name
CREDIT_LLM_REPORT_GOAL_TEMPLATE = (
    '基于{pname}，识别与客户信用风险显著相关的特征信号，'
    '为授信审批和贷后监控提供数据依据'
)

# 链路 B（工商财务）结果导出：时间戳类文件前缀、综合表文件名、LLM 产物项目名
GSFC_RESULTS_EXPORT_PREFIX = '风险分析'
GSFC_COMPREHENSIVE_CSV_BASENAME = '风险特征分析综合结果'
GSFC_IV_COMPARE_CSV_BASENAME = '风险特征分析_分群IV对比'
GSFC_LLM_PROJECT_NAME = '工商财务风险特征分析'
