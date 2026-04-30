# -*- coding: utf-8 -*-
"""
风险触碰提取模块 - 本地配置

⚠️  默认特征 RISK_FEATURES_GSFC 仅适配 GSFC（工商财务）主题宽表；
    其他主题（征信、舆情、generic）请通过 extract_triggers(features=...) 或
    CLI `--features-file` 参数注入项目专属特征列表。
    若使用默认特征但宽表匹配率 < MIN_DEFAULT_FEATURE_MATCH_RATE，
    extract_triggers 会抛 RuntimeError 阻断（避免输出全 0 名单）。

每条记录字段说明：
  report_name        : 报告展示名称
  source_col         : 宽表中的列名
  risk_direction     : 'positive'（值越大风险越高）或 'negative'（值越小风险越高）
  iv                 : 全量IV值
  category           : 业务类别（用于汇总统计）
  explicit_threshold : 可选，报告中明确给出的阈值，格式 (operator, value)，优先于数据计算
  scope              : 触发范围，支持 4 种形态：
                         'full'                                # 全量（默认）
                         'waist'                               # 仅腰部企业（兼容旧写法，等价于
                                                               #   {"dim": "是否腰部企业", "value": 1}）
                         {"dim": "X", "value": "Y"}            # 单值维度筛选
                         {"dim": "X", "values": ["Y1","Y2"]}   # 多值维度筛选
  iv_waist           : 腰部企业IV（scope='waist' 时用于加权得分；通用 scope 无此字段，统一用 iv）
"""
import sys
from pathlib import Path

# 向上两级找到 risk-feature-pipeline 根
_pipeline_root = str(Path(__file__).resolve().parent.parent.parent)
if _pipeline_root not in sys.path:
    sys.path.insert(0, _pipeline_root)

from risk_pipeline.config import (  # noqa: F401
    COL_CUSTOMER_ID,
    COL_TARGET,
    MIN_SAMPLES,
    MIN_BAD_SAMPLES,
)

# 默认特征匹配率阈值：使用 RISK_FEATURES 默认值时，若宽表匹配率低于此值，
# extract_triggers 会抛 RuntimeError 而非静默跑出全 0 名单。
MIN_DEFAULT_FEATURE_MATCH_RATE = 0.5

# ---------------------------------------------------------------------------
# 默认风险特征配置（GSFC 主题：工商变更 + 财务 + 授信匹配度 + 数据完整度）
# 调用 extract_triggers() 时可通过 features= 参数整体替换为项目专属配置。
# ---------------------------------------------------------------------------
RISK_FEATURES_GSFC = [
    # =========================================================
    # 一、工商变更特征
    # =========================================================
    {
        'report_name': '经营范围变更_年度差值',
        'source_col': '经营范围变更_年度差值(最近一年-上一年)',
        'risk_direction': 'positive',
        'iv': 0.484,
        'category': '工商变更-年度差值',
        'scope': 'full',
    },
    {
        'report_name': '距离最近变更天数',
        'source_col': '距离最近变更天数',
        'risk_direction': 'positive',
        'iv': 0.356,
        'category': '工商变更-基础',
        'scope': 'full',
    },
    {
        'report_name': '变更类型数_年度差值',
        'source_col': '变更类型数_差值(最近一年-上一年)',
        'risk_direction': 'positive',
        'iv': 0.327,
        'category': '工商变更-年度差值',
        'scope': 'full',
    },
    {
        'report_name': '变更次数_年度差值',
        'source_col': '变更次数_差值(最近一年-上一年)',
        'risk_direction': 'positive',
        'iv': 0.326,
        'category': '工商变更-年度差值',
        'scope': 'full',
    },
    {
        'report_name': '注册资本变更_年度差值',
        'source_col': '注册资本变更_年度差值(最近一年-上一年)',
        'risk_direction': 'positive',
        'iv': 0.246,
        'category': '工商变更-年度差值',
        'scope': 'full',
    },
    {
        'report_name': '股东/投资人变更_年度差值',
        'source_col': '股东/投资人变更_年度差值(最近一年-上一年)',
        'risk_direction': 'positive',
        'iv': 0.229,
        'category': '工商变更-年度差值',
        'scope': 'full',
    },
    {
        'report_name': '董监高变更_年度差值',
        'source_col': '董监高变更_年度差值(最近一年-上一年)',
        'risk_direction': 'positive',
        'iv': 0.200,
        'category': '工商变更-年度差值',
        'scope': 'full',
    },
    {
        'report_name': '资本相关最大百分比变化',
        'source_col': '资本相关最大百分比变化',
        'risk_direction': 'negative',
        'iv': 0.492,
        'category': '工商变更-资本',
        'scope': 'full',
    },
    {
        'report_name': '资本相关金额变化合计(万)',
        'source_col': '资本相关金额变化合计(万)',
        'risk_direction': 'negative',
        'iv': 0.291,
        'category': '工商变更-资本',
        'scope': 'full',
    },
    # =========================================================
    # 二、财务特征 - 偿债能力
    # =========================================================
    {
        'report_name': '现金比率',
        'source_col': '现金比率',
        'risk_direction': 'negative',
        'iv': 0.390,
        'category': '财务-偿债能力',
        'scope': 'full',
    },
    {
        'report_name': '借款依赖度',
        'source_col': '借款依赖度',
        'risk_direction': 'positive',
        'iv': 0.385,
        'category': '财务-偿债能力',
        'scope': 'full',
    },
    {
        'report_name': '营运资金比率',
        'source_col': '营运资金比率',
        'risk_direction': 'positive',
        'iv': 0.295,
        'category': '财务-偿债能力',
        'scope': 'full',
    },
    {
        'report_name': '流动比率',
        'source_col': '流动比率',
        'risk_direction': 'negative',
        'iv': 0.280,
        'category': '财务-偿债能力',
        'scope': 'full',
    },
    {
        'report_name': '资产负债率',
        'source_col': '资产负债率',
        'risk_direction': 'negative',
        'iv': 0.132,
        'category': '财务-偿债能力',
        'scope': 'full',
    },
    # =========================================================
    # 三、财务特征 - 资产负债表关键信号
    # =========================================================
    {
        'report_name': '货币资金短期借款覆盖',
        'source_col': '货币资金短期借款覆盖',
        'risk_direction': 'negative',
        'iv': 0.643,
        'category': '财务-资产负债表',
        'explicit_threshold': ('<', 0.5),
        'scope': 'full',
    },
    {
        'report_name': '货币资金占流动资产比',
        'source_col': '货币资金占流动资产比',
        'risk_direction': 'negative',
        'iv': 0.556,
        'category': '财务-资产负债表',
        'scope': 'full',
    },
    {
        'report_name': '有息负债',
        'source_col': '有息负债',
        'risk_direction': 'negative',
        'iv': 0.430,
        'category': '财务-资产负债表',
        'scope': 'full',
    },
    {
        'report_name': '短期借款占负债比',
        'source_col': '短期借款占负债比',
        'risk_direction': 'positive',
        'iv': 0.270,
        'category': '财务-资产负债表',
        'scope': 'full',
    },
    {
        'report_name': '未分配利润占权益比',
        'source_col': '未分配利润占权益比',
        'risk_direction': 'positive',
        'iv': 0.284,
        'category': '财务-资产负债表',
        'scope': 'full',
    },
    {
        'report_name': '存货占收入比',
        'source_col': '存货占收入比',
        'risk_direction': 'negative',
        'iv': 0.294,
        'category': '财务-资产负债表',
        'scope': 'full',
    },
    # =========================================================
    # 四、财务特征 - 现金流
    # =========================================================
    {
        'report_name': '投资活动净额',
        'source_col': '投资活动净额',
        'risk_direction': 'positive',
        'iv': 0.607,
        'category': '财务-现金流',
        'scope': 'full',
    },
    {
        'report_name': '现金流量净额',
        'source_col': '现金流量净额',
        'risk_direction': 'negative',
        'iv': 0.540,
        'category': '财务-现金流',
        'scope': 'full',
    },
    {
        'report_name': '借款收到的现金',
        'source_col': '借款收到的现金',
        'risk_direction': 'negative',
        'iv': 0.437,
        'category': '财务-现金流',
        'scope': 'full',
    },
    # =========================================================
    # 五、盈利质量特征
    # =========================================================
    {
        'report_name': '财务费用率',
        'source_col': '财务费用率',
        'risk_direction': 'positive',
        'iv': 0.556,
        'category': '盈利质量',
        'scope': 'full',
    },
    {
        'report_name': '财务费用',
        'source_col': '财务费用',
        'risk_direction': 'negative',
        'iv': 0.568,
        'category': '盈利质量',
        'scope': 'full',
    },
    {
        'report_name': '营业收入',
        'source_col': '营业收入',
        'risk_direction': 'negative',
        'iv': 0.318,
        'category': '盈利质量',
        'scope': 'full',
    },
    # =========================================================
    # 六、授信匹配度特征
    # =========================================================
    {
        'report_name': '本行授信使用率',
        'source_col': '本行授信使用率',
        'risk_direction': 'positive',
        'iv': 0.860,
        'category': '授信匹配度',
        'explicit_threshold': ('>', 0.70),
        'scope': 'full',
    },
    {
        'report_name': '授信总金额',
        'source_col': '授信总金额',
        'risk_direction': 'positive',
        'iv': 0.448,
        'category': '授信匹配度',
        'scope': 'full',
    },
    {
        'report_name': '表内授信余额',
        'source_col': '表内授信余额',
        'risk_direction': 'positive',
        'iv': 0.367,
        'category': '授信匹配度',
        'scope': 'full',
    },
    {
        'report_name': '本行授信净资产比',
        'source_col': '本行授信净资产比',
        'risk_direction': 'negative',
        'iv': 0.311,
        'category': '授信匹配度',
        'scope': 'full',
    },
    {
        'report_name': '本行融资占比',
        'source_col': '本行融资占比',
        'risk_direction': 'positive',
        'iv': 0.360,
        'category': '授信匹配度',
        'explicit_threshold': ('>', 0.40),
        'scope': 'full',
    },
    # =========================================================
    # 七、数据完整度
    # =========================================================
    {
        'report_name': '数据完整度',
        'source_col': '数据完整度',
        'risk_direction': 'negative',
        'iv': 0.266,
        'category': '数据完整度',
        'explicit_threshold': ('<', 70),
        'scope': 'full',
    },
    # =========================================================
    # 八、腰部企业专项强信号
    # =========================================================
    {
        'report_name': '高风险变更总数',
        'source_col': '高风险变更总数',
        'risk_direction': 'positive',
        'iv': 0.081,
        'iv_waist': 1.019,
        'category': '工商变更-腰部专项',
        'scope': 'waist',
    },
    {
        'report_name': '变更总次数',
        'source_col': '变更总次数',
        'risk_direction': 'positive',
        'iv': 0.030,
        'iv_waist': 0.822,
        'category': '工商变更-腰部专项',
        'scope': 'waist',
    },
    {
        'report_name': '年度变更次数标准差',
        'source_col': '年度变更次数标准差',
        'risk_direction': 'positive',
        'iv': 0.032,
        'iv_waist': 0.749,
        'category': '工商变更-腰部专项',
        'scope': 'waist',
    },
    {
        'report_name': '最新股东数量',
        'source_col': '最新股东数量',
        'risk_direction': 'positive',
        'iv': 0.004,
        'iv_waist': 0.773,
        'category': '工商变更-腰部专项',
        'scope': 'waist',
    },
    {
        'report_name': '累计_法定代表人变更',
        'source_col': '累计_法定代表人/负责人变更',
        'risk_direction': 'positive',
        'iv': 0.023,
        'iv_waist': 1.944,
        'category': '工商变更-腰部专项',
        'scope': 'waist',
    },
]

# 向后兼容别名：旧代码 / 旧测试用例 import RISK_FEATURES 仍可用
RISK_FEATURES = RISK_FEATURES_GSFC
