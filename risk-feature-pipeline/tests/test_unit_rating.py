# -*- coding: utf-8 -*-
"""特征评级 / IV 预测力标签单测：钉死本次收敛后的两处共享标签逻辑。

背景：
- `rate_feature`（report_insights）此前在 report_analysis / report_export 各有一份
  内联实现且都漏了"方向一致的中等信号提升为重要特征"，本次收敛为单一实现并补上该口径。
  本文件是该口径的回归网——它服务于贷前业务建议 / 贷后预警规则，而非评分卡，故
  「跨分群方向一致」在评级里是一等公民，不是只看单变量 IV 强度。
- `iv_power_label`（iv_core）由 report_analysis 两处逐字相同的内联 `_iv_power` 收敛而来。

任何改动若动了评级阈值 / 一致性闸门 / IV 预测力分档，这里会立刻红。
"""
import pytest

from risk_export_report.scripts.report_insights import rate_feature
from risk_pipeline.analysis.iv_core import iv_power_label


# ---------------------------------------------------------------------------
# rate_feature：核心特征 —— IV>=0.2 且跨分群方向一致（又强又稳）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('iv,corr,consistent', [
    (0.2, 0.10, True),    # 边界：IV 恰好 0.2
    (0.5, 0.30, True),
    (0.2, None, True),    # 核心档不依赖 corr，corr 缺失也成立
    (0.25, -0.40, True),  # 负相关同样算（方向由 sign_consistent 表达）
])
def test_core_feature(iv, corr, consistent):
    assert rate_feature(iv, corr, consistent) == '核心特征'


def test_strong_iv_but_inconsistent_is_only_important():
    """强 IV 但跨分群方向不一致 → 降为重要特征（不给核心），这是稳定性优先的体现。"""
    assert rate_feature(0.25, 0.10, False) == '重要特征'


# ---------------------------------------------------------------------------
# rate_feature：重要特征 —— IV>=0.1，或（方向一致 且 |corr均值|>=0.05）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('iv,corr,consistent,reason', [
    (0.10, 0.0, False, 'IV 恰好 0.1，单凭强度即可'),
    (0.15, None, False, 'IV>=0.1，corr 缺失也成立'),
    (0.19, 0.0, False, 'IV 在 [0.1,0.2) 且方向不一致'),
    # —— 关键回归点：方向一致的中等信号被提升为重要特征（本次新增口径）——
    (0.09, 0.06, True, '中等 IV + 方向一致 + corr 够 → 升重要'),
    (0.05, 0.05, True, 'corr 恰好 0.05（>=）边界，方向一致 → 升重要'),
    (0.05, -0.08, True, '负相关取绝对值，方向一致 → 升重要'),
])
def test_important_feature(iv, corr, consistent, reason):
    assert rate_feature(iv, corr, consistent) == '重要特征', reason


# ---------------------------------------------------------------------------
# rate_feature：一致性闸门 —— corr 提升必须同时满足「方向一致」且「|corr|>=0.05」
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('iv,corr,consistent,expect,reason', [
    (0.09, 0.06, False, '辅助特征', '方向不一致 → 不升重要，只能落辅助'),
    (0.09, 0.03, True, '辅助特征', 'corr<0.05 → 即便方向一致也不升'),
    (0.05, None, True, '辅助特征', '无 corr 信号 + IV 在 [0.02,0.1) → 辅助'),
])
def test_consistency_gate_blocks_promotion(iv, corr, consistent, expect, reason):
    assert rate_feature(iv, corr, consistent) == expect, reason


# ---------------------------------------------------------------------------
# rate_feature：辅助特征 —— IV>=0.02，或 |corr均值|>=0.05（弱信号兜底）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('iv,corr,consistent', [
    (0.03, 0.0, False),    # IV 在 [0.02,0.1)
    (0.02, None, False),   # 边界：IV 恰好 0.02
    (0.01, 0.06, False),   # IV 过低，但 corr 把它从无效救到辅助
    (0.0, -0.05, False),   # IV=0 但 |corr|=0.05 边界
])
def test_auxiliary_feature(iv, corr, consistent):
    assert rate_feature(iv, corr, consistent) == '辅助特征'


# ---------------------------------------------------------------------------
# rate_feature：无效特征 —— 以上均不满足
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('iv,corr,consistent', [
    (0.01, 0.0, False),
    (0.0, None, False),
    (0.019, 0.049, True),  # IV<0.02 且 |corr|<0.05（方向一致也救不了）
])
def test_invalid_feature(iv, corr, consistent):
    assert rate_feature(iv, corr, consistent) == '无效特征'


def test_rate_feature_corr_none_never_raises():
    """corr_mean 为 None 时不得抛错（真实数据里相关性可能整列缺失）。"""
    for iv in (0.0, 0.02, 0.1, 0.2, 0.5):
        for consistent in (True, False):
            rate_feature(iv, None, consistent)


# ---------------------------------------------------------------------------
# iv_power_label：IV 预测力分档（强/中/弱/无），口径见 calc_iv docstring
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('iv,expect', [
    (0.5, '强'),
    (0.3, '强'),     # 边界
    (0.29, '中'),
    (0.1, '中'),     # 边界
    (0.09, '弱'),
    (0.02, '弱'),    # 边界
    (0.019, '无'),
    (0.0, '无'),
    (float('nan'), '无'),  # NaN 视为无（不抛错）
])
def test_iv_power_label(iv, expect):
    assert iv_power_label(iv) == expect
