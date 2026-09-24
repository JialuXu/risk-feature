# -*- coding: utf-8 -*-
"""
征信/机构侧宽表上的比值与占比类衍生特征。

与 SKILL 对齐的入口：create_credit_features、get_feature_sets。
不包含数据合并、IV、分群统计或建模（见各专项 Skill）。
"""

import numpy as np

from .config import CREDIT_CONFIG
from .io_utils import safe_divide


def create_credit_features(df):
    """
    构建征信衍生特征（比值/占比型，消除规模影响）

    设计原则：
    1. 消除企业规模影响，使大小企业可比
    2. 提取行为逻辑，反映融资行为模式
    3. 避免除零错误，使用安全除法
    """
    df = df.copy()

    # 结构占比类
    df['非银机构占比'] = safe_divide(df['非银授信机构数'], df['总机构数'])
    df['银行机构占比'] = safe_divide(df['银行授信机构数'], df['总机构数'])
    df['小贷公司占比'] = safe_divide(df['小额贷款公司数'], df['总机构数'])
    df['消金公司占比'] = safe_divide(df['消费金融公司数'], df['总机构数'])
    df['未结清机构占比'] = safe_divide(df['信贷交易未结清总机构数'], df['总机构数'])

    # 渠道风险特征
    df['高风险渠道数'] = df['小额贷款公司数'] + df['消费金融公司数']
    df['高风险渠道占比'] = safe_divide(df['高风险渠道数'], df['总机构数'])
    df['是否有高风险渠道'] = (df['高风险渠道数'] > 0).astype(int)
    df['非银银行比例'] = safe_divide(df['非银授信机构数'], df['银行授信机构数'])

    # 行为指标类
    df['授信分散度'] = np.log1p(df['总机构数'])

    # 效率比值类
    df['担保查询未结清比'] = safe_divide(
        df['担保人征信查询次数'], df['信贷交易未结清总机构数']
    )
    df['担保查询机构比'] = safe_divide(df['担保人征信查询次数'], df['总机构数'])

    # 交叉特征
    df['高风险未结清交叉'] = df['高风险渠道数'] * df['信贷交易未结清总机构数']

    # ========== 第二轮：补充衍生特征（针对征信数据特性） ==========

    total = df['总机构数']

    # --- 比率类（消除规模影响）---
    # 结清机构占比（正常履约表现）
    df['结清机构占比'] = safe_divide(
        total - df['信贷交易未结清总机构数'], total)

    # 当前逾期率（最直接的违约信号）
    df['当前逾期率'] = safe_divide(df['当前逾期机构数'], total)

    # 单机构均担保查询（控制规模后反映融资活跃度）
    df['人均担保查询'] = safe_divide(df['担保人征信查询次数'], total)

    # 单机构均贷款笔数（信用集中度信号）
    df['人均未结清笔数'] = safe_divide(df['信贷交易未结清总机构数'], total)

    # 逾期金额深度（每非银+银行机构对应多少逾期余额）
    nonbank_bank = df['非银授信机构数'] + df['银行授信机构数']
    df['逾期每机构余额'] = safe_divide(df['当前逾期余额'], nonbank_bank)

    # --- 交互/复合特征 ---
    # 纯非银依赖度（无银行贷款倾向 = 高风险偏好）
    total_nonbank = df['非银授信机构数'] + df['银行授信机构数']
    df['纯非银比例'] = safe_divide(df['非银授信机构数'], total_nonbank)

    # 审核压力比（查询多且未结清少 = 高审批压力 = 可能资金链紧张）
    df['审核压力比'] = safe_divide(df['担保人征信查询次数'],
                                    df['信贷交易未结清总机构数'])

    # 高风险渠道占总比（小贷+消金合计占比）
    high_risk_count = df['小额贷款公司数'] + df['消费金融公司数']
    df['高风险渠道总数'] = high_risk_count
    df['高风险渠道占总比'] = safe_divide(high_risk_count, total)

    # --- 结构化计数 ---
    # 授信渠道多样性（有值的机构类别数 = 0~5 离散变量）
    df['渠道多样性'] = (
        (df['银行授信机构数'] > 0).astype(int) +
        (df['非银授信机构数'] > 0).astype(int) +
        (df['小额贷款公司数'] > 0).astype(int) +
        (df['消费金融公司数'] > 0).astype(int)
    )

    # 对数变换（缓解长尾，使数值更接近正态）
    df['log_总机构数'] = np.log1p(df['总机构数'].fillna(0))
    df['log_未结清机构数'] = np.log1p(df['信贷交易未结清总机构数'].fillna(0))

    return df


def get_feature_sets(df):
    """
    获取三套特征集（过滤无效特征）

    返回:
        dict: raw / derived / all / default（默认使用衍生列）
    """

    def _filter(feat_list):
        return [c for c in feat_list if c in df.columns and df[c].std() > 0]

    raw = _filter(CREDIT_CONFIG['raw_features'])
    derived = _filter(CREDIT_CONFIG['derived_features'])
    all_feats = _filter(
            CREDIT_CONFIG['raw_features'] + CREDIT_CONFIG['derived_features'])

    return {
        'raw': raw,
        'derived': derived,
        'all': all_feats,
        'default': derived,
    }
