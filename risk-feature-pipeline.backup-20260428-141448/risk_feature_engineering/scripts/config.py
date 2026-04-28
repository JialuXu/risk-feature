# -*- coding: utf-8 -*-
"""
risk_feature_engineering 配置

公共配置统一从 shared.config 导入，本文件仅保留模块专属配置。
"""
import sys
from pathlib import Path

# 将 risk-feature-pipeline/ 加入 sys.path，使 shared 包可被 import
_MY_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _MY_SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _MY_SKILLS_ROOT)

# 导入全部公共配置（DATA_CONFIG, SEGMENT_DIMS, CREDIT_BINS, SAMPLE_THRESHOLDS 等）
from shared.config import *  # noqa: F401,F403

# =============================================================================
# 模块专属配置：特征工程
# =============================================================================

# get_feature_cols：按列名子串排除的 ID、目标、分群与元数据列
# 由配置常量动态构建，多银行适配时自动跟随 YAML 变化
_FEATURE_EXCLUDE_PATTERNS = [
    '客户名称', '是否坏客户', '分层', '分群',
    '是否腰部', '是否中等授信', '_来源', '赛道',
    '是否科技企业', '是否盈利', '数据质量等级',
    '主报表类型', '资产规模分层', '2024年以来新户',
]

FEATURE_COL_EXCLUDE_SUBSTRINGS = (
    _FEATURE_EXCLUDE_PATTERNS
    + [COL_CUSTOMER_ID, COL_TARGET, COL_REPORT_DATE]
    + COL_SEGMENT_DIMS
    + COL_INDUSTRY_DATA_COLS
    + [COL_QUAL_PREFIX]  # 匹配所有资质标签列
)

# 征信宽表：对象列尝试去千分位转数值时跳过的分类/主键列
CREDIT_OBJECT_TO_NUMERIC_SKIP_COLS = COL_NUMERIC_SKIP_COLS

# 工商变更：高风险变更累计列名（与变更侧表字段一致）
CHANGE_HIGH_RISK_CUMULATIVE_COLS = [
    '累计_法定代表人/负责人变更', '累计_股东/投资人变更', '累计_注册资本变更',
]

# 工商变更：近期窗口（天），用于占比与高风险计数
CHANGE_RECENT_DAY_WINDOWS = ('30', '90', '180', '365')
CHANGE_HIGH_RISK_SHORT_WINDOWS = ('30', '90')

# 财务衍生特征列清单（与 feature_engineering 构造顺序一致，供 Winsorize 与统计）
FINANCE_DERIVED_COL_NAMES = (
    '营运资金', '营运资金比率', '短期借款压力', '短期借款占负债比',
    '长期负债比率', '借款依赖度', '权益乘数', '负债权益比',
    '利息保障倍数', '利息支出占收入比',
    '应收账款占收入比', '存货占收入比', '应收存货占流动资产比',
    '存货占流动资产比', '应收账款占流动资产比', '货币资金占流动资产比',
    '无形资产占比', '长期股权投资占比', '非流动资产占比',
    '应付账款周转率', '应付账款占成本比', '固定资产周转率',
    '营运资本周转率', '资产收益质量',
    '成本费用利润率', '营业成本率', '研发投入强度',
    '管理费用率', '销售费用率', '财务费用率',
    '净利润现金流比', '经营现金净利润比',
    '未分配利润占权益比', '盈余公积占权益比',
    '经营现金流借款覆盖比', '现金流利息保障倍数', '自由现金流',
    '现金储备月数', '货币资金短期借款覆盖', '筹资依赖度', '投资现金流占比',
    '本行授信使用率', '本行授信资产比', '本行授信收入比', '本行授信净资产比', '本行授信现金流比',
    '本行融资占比', '他行融资估算', '整体债务收入比',
    '实收资本占资产比', '资本公积占权益比', '实收资本借款比',
)
