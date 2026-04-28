# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd

from .config import (
    FINANCE_DERIVED_COL_NAMES,
    FEATURE_COL_EXCLUDE_SUBSTRINGS,
)
from .io_utils import safe_divide


def feature_engineering(df):
    """
    特征工程 - 构造财务衍生特征

    偿债能力、资产质量、经营效率、盈利质量、现金流安全、授信匹配度等
    """
    print("\n" + "="*60)
    print("Step 2: 特征工程")
    print("="*60)

    # -----------------------------
    # 财务指标衍生特征（从银行贷后管理角度全面构建）
    # -----------------------------
    print("[INFO] 构造财务衍生特征（贷后风险预警视角）...")

    # ===== 2.2.1 偿债能力预警指标 =====
    print("[INFO]   - 偿债能力预警指标...")

    # 营运资金 = 流动资产 - 流动负债（短期偿债缓冲）
    if '流动资产合计' in df.columns and '流动负债合计' in df.columns:
        if '营运资金' not in df.columns:
            df['营运资金'] = df['流动资产合计'].fillna(0) - df['流动负债合计'].fillna(0)

    # 营运资金比率 = 营运资金 / 总资产（营运资金充足度）
    if '营运资金' in df.columns and '资产总计' in df.columns:
        df['营运资金比率'] = safe_divide(df['营运资金'], df['资产总计'])

    # 短期借款压力 = 短期借款 / 流动资产（短期偿债压力）
    if '短期借款' in df.columns and '流动资产合计' in df.columns:
        df['短期借款压力'] = safe_divide(df['短期借款'], df['流动资产合计'])

    # 短期借款占负债比 = 短期借款 / 负债合计（负债结构）
    if '短期借款' in df.columns and '负债合计' in df.columns:
        df['短期借款占负债比'] = safe_divide(df['短期借款'], df['负债合计'])

    # 长期负债比率 = 非流动负债 / 总资产（长期偿债结构）
    if '非流动负债合计' in df.columns and '资产总计' in df.columns:
        df['长期负债比率'] = safe_divide(df['非流动负债合计'], df['资产总计'])

    # 借款依赖度 = (短期借款 + 长期借款) / 总资产
    if '短期借款' in df.columns and '长期借款' in df.columns and '资产总计' in df.columns:
        total_loans = df['短期借款'].fillna(0) + df['长期借款'].fillna(0)
        df['借款依赖度'] = safe_divide(total_loans, df['资产总计'])

    # 权益乘数 = 总资产 / 股东权益（财务杠杆）
    if '资产总计' in df.columns and '股东权益总计' in df.columns:
        df['权益乘数'] = safe_divide(df['资产总计'], df['股东权益总计'])

    # 负债权益比 = 负债合计 / 股东权益（杠杆率）
    if '负债合计' in df.columns and '股东权益总计' in df.columns:
        df['负债权益比'] = safe_divide(df['负债合计'], df['股东权益总计'])

    # 利息保障倍数 = 利润总额 / 财务费用（偿息能力）
    if '利润总额' in df.columns and '财务费用' in df.columns:
        if '利息保障倍数' not in df.columns:
            df['利息保障倍数'] = safe_divide(df['利润总额'], df['财务费用'])

    # 利息支出占比 = 利息支出 / 营业收入（融资成本负担）
    if '利息支出' in df.columns and '营业收入' in df.columns:
        df['利息支出占收入比'] = safe_divide(df['利息支出'], df['营业收入'])

    # ===== 2.2.2 资产质量指标 =====
    print("[INFO]   - 资产质量指标...")

    # 应收账款占收入比 = 应收账款 / 营业收入（收入质量/回款风险）
    if '应收账款' in df.columns and '营业收入' in df.columns:
        df['应收账款占收入比'] = safe_divide(df['应收账款'], df['营业收入'])

    # 存货占收入比 = 存货 / 营业收入（存货积压风险）
    if '存货' in df.columns and '营业收入' in df.columns:
        df['存货占收入比'] = safe_divide(df['存货'], df['营业收入'])

    # 应收存货合计占流动资产比（流动资产质量）
    if '应收账款' in df.columns and '存货' in df.columns and '流动资产合计' in df.columns:
        df['应收存货占流动资产比'] = safe_divide(
            df['应收账款'].fillna(0) + df['存货'].fillna(0),
            df['流动资产合计']
        )

    # 存货占流动资产比
    if '存货' in df.columns and '流动资产合计' in df.columns:
        if '存货占流动资产比' not in df.columns:
            df['存货占流动资产比'] = safe_divide(df['存货'], df['流动资产合计'])

    # 应收账款占流动资产比
    if '应收账款' in df.columns and '流动资产合计' in df.columns:
        if '应收账款占流动资产比' not in df.columns:
            df['应收账款占流动资产比'] = safe_divide(df['应收账款'], df['流动资产合计'])

    # 货币资金占流动资产比
    if '货币资金' in df.columns and '流动资产合计' in df.columns:
        if '货币资金占流动资产比' not in df.columns:
            df['货币资金占流动资产比'] = safe_divide(df['货币资金'], df['流动资产合计'])

    # 无形资产占比 = 无形资产 / 总资产（资产虚实）
    if '无形资产' in df.columns and '资产总计' in df.columns:
        df['无形资产占比'] = safe_divide(df['无形资产'], df['资产总计'])

    # 长期股权投资占比 = 长期股权投资 / 总资产（对外投资风险）
    if '长期股权投资' in df.columns and '资产总计' in df.columns:
        df['长期股权投资占比'] = safe_divide(df['长期股权投资'], df['资产总计'])

    # 非流动资产占比 = 非流动资产 / 总资产（资产流动性）
    if '非流动资产合计' in df.columns and '资产总计' in df.columns:
        df['非流动资产占比'] = safe_divide(df['非流动资产合计'], df['资产总计'])

    # ===== 2.2.3 经营效率指标 =====
    print("[INFO]   - 经营效率指标...")

    # 应付账款周转率 = 营业成本 / 应付账款（付款效率）
    if '营业成本' in df.columns and '应付账款' in df.columns:
        df['应付账款周转率'] = safe_divide(df['营业成本'], df['应付账款'])

    # 应付账款占成本比 = 应付账款 / 营业成本（供应链议价能力）
    if '应付账款' in df.columns and '营业成本' in df.columns:
        df['应付账款占成本比'] = safe_divide(df['应付账款'], df['营业成本'])

    # 固定资产周转率 = 营业收入 / 固定资产净值（固定资产利用效率）
    if '营业收入' in df.columns and '固定资产净值' in df.columns:
        df['固定资产周转率'] = safe_divide(df['营业收入'], df['固定资产净值'])

    # 营运资本周转率 = 营业收入 / 营运资金（营运效率）
    if '营业收入' in df.columns and '营运资金' in df.columns:
        df['营运资本周转率'] = safe_divide(df['营业收入'], df['营运资金'])

    # 资产收益质量 = 经营现金流入 / 资产总计（资产产生现金能力）
    if '经营活动现金流入' in df.columns and '资产总计' in df.columns:
        df['资产收益质量'] = safe_divide(df['经营活动现金流入'], df['资产总计'])

    # ===== 2.2.4 盈利质量指标 =====
    print("[INFO]   - 盈利质量指标...")

    # 成本费用利润率 = 利润总额 / (营业成本 + 三项费用)
    if '利润总额' in df.columns and '营业成本' in df.columns and '三项费用合计' in df.columns:
        total_cost = df['营业成本'].fillna(0) + df['三项费用合计'].fillna(0)
        df['成本费用利润率'] = safe_divide(df['利润总额'], total_cost)

    # 营业成本率 = 营业成本 / 营业收入
    if '营业成本' in df.columns and '营业收入' in df.columns:
        df['营业成本率'] = safe_divide(df['营业成本'], df['营业收入'])

    # 研发投入强度 = 研发费用 / 营业收入（创新能力）
    if '研发费用' in df.columns and '营业收入' in df.columns:
        df['研发投入强度'] = safe_divide(df['研发费用'], df['营业收入'])

    # 管理费用率 = 管理费用 / 营业收入
    if '管理费用' in df.columns and '营业收入' in df.columns:
        df['管理费用率'] = safe_divide(df['管理费用'], df['营业收入'])

    # 销售费用率 = 销售费用 / 营业收入
    if '销售费用' in df.columns and '营业收入' in df.columns:
        df['销售费用率'] = safe_divide(df['销售费用'], df['营业收入'])

    # 财务费用率 = 财务费用 / 营业收入
    if '财务费用' in df.columns and '营业收入' in df.columns:
        df['财务费用率'] = safe_divide(df['财务费用'], df['营业收入'])

    # 净利润与经营现金流比 = 净利润 / 经营现金流入（盈利现金含量）
    if '净利润' in df.columns and '经营活动现金流入' in df.columns:
        df['净利润现金流比'] = safe_divide(df['净利润'], df['经营活动现金流入'])

    # 经营现金流与净利润比 = 经营现金流入 / 净利润（现金利润质量）
    if '经营活动现金流入' in df.columns and '净利润' in df.columns:
        df['经营现金净利润比'] = safe_divide(df['经营活动现金流入'], df['净利润'])

    # 未分配利润占净资产比 = 未分配利润 / 股东权益（盈利积累）
    if '未分配利润' in df.columns and '股东权益总计' in df.columns:
        df['未分配利润占权益比'] = safe_divide(df['未分配利润'], df['股东权益总计'])

    # 盈余公积占权益比 = 盈余公积 / 股东权益（利润留存）
    if '盈余公积' in df.columns and '股东权益总计' in df.columns:
        df['盈余公积占权益比'] = safe_divide(df['盈余公积'], df['股东权益总计'])

    # ===== 2.2.5 现金流安全指标 =====
    print("[INFO]   - 现金流安全指标...")

    # 经营现金流对借款覆盖比 = 经营现金流入 / (短期借款 + 长期借款)
    if '经营活动现金流入' in df.columns and '短期借款' in df.columns and '长期借款' in df.columns:
        total_loans = df['短期借款'].fillna(0) + df['长期借款'].fillna(0)
        df['经营现金流借款覆盖比'] = safe_divide(df['经营活动现金流入'], total_loans)

    # 现金流利息保障倍数 = 经营现金流入 / 利息支出
    if '经营活动现金流入' in df.columns and '利息支出' in df.columns:
        df['现金流利息保障倍数'] = safe_divide(df['经营活动现金流入'], df['利息支出'])

    # 自由现金流 = 经营现金流入 - 投资活动净额（可自由支配现金）
    if '经营活动现金流入' in df.columns and '投资活动净额' in df.columns:
        df['自由现金流'] = df['经营活动现金流入'].fillna(0) - df['投资活动净额'].fillna(0).abs()

    # 现金储备月数 = 货币资金 / (营业成本 / 12)（现金支撑运营时间）
    if '货币资金' in df.columns and '营业成本' in df.columns:
        monthly_cost = df['营业成本'] / 12
        df['现金储备月数'] = safe_divide(df['货币资金'], monthly_cost)

    # 货币资金对短期借款覆盖 = 货币资金 / 短期借款
    if '货币资金' in df.columns and '短期借款' in df.columns:
        df['货币资金短期借款覆盖'] = safe_divide(df['货币资金'], df['短期借款'])

    # 筹资活动依赖度 = 筹资活动现金流入 / 经营活动现金流入
    if '筹资活动现金流入' in df.columns and '经营活动现金流入' in df.columns:
        df['筹资依赖度'] = safe_divide(df['筹资活动现金流入'], df['经营活动现金流入'])

    # 投资现金流占比 = 投资活动现金流入 / 经营活动现金流入
    if '投资活动现金流入' in df.columns and '经营活动现金流入' in df.columns:
        df['投资现金流占比'] = safe_divide(df['投资活动现金流入'], df['经营活动现金流入'])

    # ===== 2.2.6 授信匹配度指标（贷后核心 - 修正版） =====
    print("[INFO]   - 授信匹配度指标（本行视角 & 份额视角）...")

    # 1. 本行授信激进程度（原“授信匹配度”）
    # 明确这些指标反映的是“本行”对客户的风险暴露，而非客户整体负债水平

    # 本行授信使用率
    if '表内授信余额' in df.columns and '授信总金额' in df.columns:
        df['本行授信使用率'] = safe_divide(df['表内授信余额'], df['授信总金额'])

    # 本行授信与资产比（衡量本行敞口相对于客户规模）
    if '授信总金额' in df.columns and '资产总计' in df.columns:
        df['本行授信资产比'] = safe_divide(df['授信总金额'], df['资产总计'])

    # 本行授信与收入比（衡量本行额度是否超出了客户营收承载力）
    if '授信总金额' in df.columns and '营业收入' in df.columns:
        df['本行授信收入比'] = safe_divide(df['授信总金额'], df['营业收入'])

    # 本行授信与净资产比
    if '授信总金额' in df.columns and '股东权益总计' in df.columns:
        df['本行授信净资产比'] = safe_divide(df['授信总金额'], df['股东权益总计'])

    # 本行授信与现金流比
    if '授信总金额' in df.columns and '经营活动现金流入' in df.columns:
        df['本行授信现金流比'] = safe_divide(df['授信总金额'], df['经营活动现金流入'])

    # 2. 本行融资份额（新增：核心风控指标）
    # 逻辑：用本行余额 / 财报显示的刚性总债务
    if '表内授信余额' in df.columns and '短期借款' in df.columns and '长期借款' in df.columns:
        # 财报中的有息负债总额
        total_interest_debt = df['短期借款'].fillna(0) + df['长期借款'].fillna(0)
        
        # 本行融资占比 (限制最大值为1，防止因财报滞后导致 本行余额 > 财报总债 的异常情况)
        share_ratio = safe_divide(df['表内授信余额'], total_interest_debt)
        df['本行融资占比'] = share_ratio.clip(upper=1.0) # 修正异常值
        
        # 他行融资估算 (财报总债 - 本行余额)
        other_bank_debt = total_interest_debt - df['表内授信余额'].fillna(0)
        df['他行融资估算'] = other_bank_debt.clip(lower=0)

    # 3. 整体杠杆匹配度（使用财报数据，而非本行授信）
    # 真正的“授信匹配度”应该看客户的总债务是否匹配其资产/收入
    if '短期借款' in df.columns and '长期借款' in df.columns and '营业收入' in df.columns:
        total_interest_debt = df['短期借款'].fillna(0) + df['长期借款'].fillna(0)
        df['整体债务收入比'] = safe_divide(total_interest_debt, df['营业收入'])

    # ===== 2.2.7 资本结构稳定性指标 =====
    print("[INFO]   - 资本结构稳定性指标...")

    # 实收资本占比 = 实收资本 / 总资产
    if '实收资本' in df.columns and '资产总计' in df.columns:
        df['实收资本占资产比'] = safe_divide(df['实收资本'], df['资产总计'])

    # 资本公积占权益比 = 资本公积 / 股东权益
    if '资本公积' in df.columns and '股东权益总计' in df.columns:
        df['资本公积占权益比'] = safe_divide(df['资本公积'], df['股东权益总计'])

    # 实收资本与借款比 = 实收资本 / (短期借款 + 长期借款)
    if '实收资本' in df.columns and '短期借款' in df.columns and '长期借款' in df.columns:
        total_loans = df['短期借款'].fillna(0) + df['长期借款'].fillna(0)
        df['实收资本借款比'] = safe_divide(df['实收资本'], total_loans)

    print("[INFO] 财务衍生特征构造完成")

    # 统计衍生特征数量
    derived_features = [c for c in FINANCE_DERIVED_COL_NAMES if c in df.columns]
    print(f"[INFO] 衍生特征数量: {len(derived_features)}")

    # Winsorize 缩尾处理：将比率类特征的极端值截断到 1%/99% 分位数
    # 目的：消除分母极小时产生的极端比率值（如应收账款/营业收入=500），
    # 这些极端值在分箱时形成"异常值箱"，导致 WOE 极端、IV 虚高
    ratio_cols = [c for c in derived_features if c in df.columns and c != '营运资金'
                  and c != '自由现金流' and c != '他行融资估算']
    n_winsorized = 0
    for col in ratio_cols:
        s = df[col].dropna()
        if len(s) < 20:
            continue
        q_low = s.quantile(0.01)
        q_high = s.quantile(0.99)
        if q_low == q_high:
            continue
        before_clip = df[col].copy()
        df[col] = df[col].clip(lower=q_low, upper=q_high)
        changed = (before_clip.notna() & (before_clip != df[col])).sum()
        if changed > 0:
            n_winsorized += 1
    print(f"[INFO] Winsorize 缩尾处理: 对 {n_winsorized} 个比率特征执行了 1%/99% 分位数截断")

    return df


_ABS_VALUE_KEYWORDS = [
    '总资产', '总负债', '营业收入', '净利润', '营业利润', '利润总额', '营业成本',
    '短期借款', '长期借款', '有息负债', 'EBIT', 'EBITDA', '归母净利润',
    '营运资本', '净资产', '经营现金流净额', '投资现金流净额', '筹资现金流净额',
    '自由现金流', '净现金流', '期末现金余额', '资本性支出',
    '信用减值损失', '资产减值损失', '减值损失合计',
    '应收票据和应收账款', '合同资产', '非经常性损益',
    '授信总金额', '表内授信余额',
    '营运资金', '他行融资估算',
]

_PROTECT_KEYWORDS = [
    '率', '比', '占', '倍', '增长', '变动', '预警',
    '周转', '覆盖', '含量', '错配', '压力', '依赖',
    '储备', '强度', '质量',
]


def _is_abs_value_feature(col_name):
    """判断是否为绝对值原始指标（排除衍生比率/效率类）"""
    has_abs = any(kw in col_name for kw in _ABS_VALUE_KEYWORDS)
    if not has_abs:
        return False
    has_protect = any(kw in col_name for kw in _PROTECT_KEYWORDS)
    return not has_protect


def get_feature_cols(df):
    """
    获取用于分析的特征列（仅衍生/比率类指标）

    排除ID列、目标变量、分群维度，以及绝对值原始财务指标
    """
    feature_cols = []
    excluded_abs = []
    for col in df.columns:
        if any(p in col for p in FEATURE_COL_EXCLUDE_SUBSTRINGS):
            continue
        if df[col].dtype not in ['float64', 'int64', 'float32', 'int32']:
            continue
        if _is_abs_value_feature(col):
            excluded_abs.append(col)
            continue
        feature_cols.append(col)

    if excluded_abs:
        print(f"[INFO] 排除 {len(excluded_abs)} 个绝对值原始指标，"
              f"保留 {len(feature_cols)} 个衍生/比率类特征")

    return feature_cols
