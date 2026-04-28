# -*- coding: utf-8 -*-
"""
risk_export_report 配置

公共配置统一从 risk_pipeline.config 导入，本文件仅保留模块专属配置。
"""
import sys
from pathlib import Path

# 将 risk-feature-pipeline/ 加入 sys.path，使 risk_pipeline 包可被 import
_MY_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _MY_SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _MY_SKILLS_ROOT)

# 导入全部公共配置（DATA_CONFIG, SEGMENT_DIMS, CREDIT_BINS, SAMPLE_THRESHOLDS 等）
from risk_pipeline.config import *  # noqa: F401,F403

# =============================================================================
# 模块专属配置：导出报告
# =============================================================================
from risk_pipeline.config import (  # noqa: F401 (补充路径常量)
    RESULTS_DIR_CREDIT, OUTPUT_DIR_CREDIT,
    RESULTS_DIR_GSFC,   OUTPUT_DIR_GSFC,
    RESULTS_DIR,        OUTPUT_DIR_GENERIC,
)

# 管线 A（征信）
CREDIT_PIPELINE_PATHS = {
    'results_rel': RESULTS_DIR_CREDIT,
    'output_rel':  OUTPUT_DIR_CREDIT,
}

# 通用宽表管线（generic）
GENERIC_PIPELINE_PATHS = {
    'results_rel': RESULTS_DIR,
    'output_rel':  OUTPUT_DIR_GENERIC,
}

# 管线 A LLM JSON「报告目标」模板，{pname} 替换为 project_name
CREDIT_LLM_REPORT_GOAL_TEMPLATE = (
    '基于{pname}，识别与客户信用风险显著相关的特征信号，'
    '为授信审批和贷后监控提供数据依据'
)

# 管线 B（工商财务）结果导出：时间戳类文件前缀、综合表文件名、LLM 产物项目名
GSFC_RESULTS_EXPORT_PREFIX = '风险分析'
GSFC_COMPREHENSIVE_CSV_BASENAME = '风险特征分析综合结果'
GSFC_IV_COMPARE_CSV_BASENAME = '风险特征分析_分群IV对比'
GSFC_LLM_PROJECT_NAME = '工商财务风险特征分析'
