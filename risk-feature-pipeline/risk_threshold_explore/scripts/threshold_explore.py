# -*- coding: utf-8 -*-
"""候选规则阈值探索的核心算法。

对每个 (分群维度, 分群名称, 特征) 三元组：
  1) 段过滤 + 准入校验
  2) 从前序 LR/corr 推断风险方向，缺失则回落到分箱跳变方向
  3) optbinning 求候选切点列表
  4) 在切点列表中按"已锁定方向风险倍数最大"挑一个
  5) 评估 + 五道门槛判定 → (规则有效, 不通过原因)

不写盘；返回两个 DataFrame + 跳过列表，让 io_utils 负责落盘。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import (
    OPTBIN_PARAMS,
    SIGNIFICANCE_LABELS,
    merge_cfg,
)

# `Results` 仅用于类型提示，运行时按 duck-typing 取属性；避免硬依赖循环 import
try:
    from risk_result_query.scripts.results_loader import Results  # noqa: F401
except Exception:  # pragma: no cover
    Results = None  # type: ignore


# optbinning binning_table.build() 原生英文列 → 中文标准列名
_OPTBIN_RENAME = {
    'Bin': '分箱',
    'Count': '样本数',
    'Count (%)': '占比',
    'Non-event': '好客户数',
    'Event': '坏客户数',
    'Event rate': '坏率',
    'WoE': 'WoE',
    'IV': 'IV分量',
}


@dataclass
class _Skip:
    分群维度: str
    分群名称: str
    特征: str
    原因: str


@dataclass
class ExploreOutcome:
    summary_df: pd.DataFrame
    detail_df: pd.DataFrame
    skipped: List[dict] = field(default_factory=list)
    gates: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def explore_thresholds(
    df: pd.DataFrame,
    pair_list: Iterable[Tuple[str, str, str]],
    project_name: str,
    results: Optional['Results'] = None,
    target_col: str = 'is_bad',
    cfg: Optional[dict] = None,
    verbose: bool = False,
) -> ExploreOutcome:
    """对每个 (dim, group, feat) 三元组跑 optbinning 找候选阈值并评估。

    Args:
        df: 已经过 prepare_df 处理的宽表（含 target_col + 分群列 + 特征列）。
        pair_list: 列表，元素为 (分群维度, 分群名称, 特征)。
        project_name: 项目名，仅用于日志。
        results: risk_result_query.load_results() 的返回值；用于推断风险方向 + 查全局 IV。
                 缺省时风险方向回落到分箱跳变方向，全局 IV 记 NaN。
        target_col: 二分类目标列名。
        cfg: 覆盖 THRESHOLD_EXPLORE_CFG 的字段；CLI 用此传 --min-risk-ratio 等。
        verbose: 打印每个 pair 的进度。

    Returns:
        ExploreOutcome(summary_df, detail_df, skipped, gates)
    """
    cfg = merge_cfg(cfg)

    rows: List[dict] = []
    details: List[pd.DataFrame] = []
    skipped: List[dict] = []

    iv_full = getattr(results, 'iv_full', None) if results is not None else None
    iv_group = getattr(results, 'iv_group_all', None) if results is not None else None
    lr_long = getattr(results, 'lr_coef_long', None) if results is not None else None
    corr_long = getattr(results, 'corr_long', None) if results is not None else None

    for dim, group, feat in pair_list:
        ctx = (str(dim), str(group), str(feat))
        if verbose:
            print(f'[explore] 处理 {ctx[0]}.{ctx[1]} - {ctx[2]}')

        skip_reason = _validate_inputs(df, dim, group, feat, target_col, cfg)
        if skip_reason:
            skipped.append({'分群维度': ctx[0], '分群名称': ctx[1], '特征': ctx[2], '原因': skip_reason})
            if verbose:
                print(f'  [跳过] {skip_reason}')
            continue

        sub = df[df[dim] == group]
        n_total = len(sub)
        n_bad = int(pd.to_numeric(sub[target_col], errors='coerce').fillna(0).sum())
        bad_rate_seg = n_bad / n_total if n_total else 0.0

        x_raw = pd.to_numeric(sub[feat], errors='coerce').values
        y = pd.to_numeric(sub[target_col], errors='coerce').fillna(0).astype(int).values

        # optbinning fit
        optb_out = _optbin_segment(x_raw, y, feat, cfg)
        splits = np.array([])
        data_rows = pd.DataFrame()
        cutoff_source = 'optbinning'

        if optb_out is not None:
            splits, data_rows = optb_out

        # 主路径：optbinning 拿到 ≥1 split 且 ≥2 行
        if len(splits) > 0 and len(data_rows) >= 2:
            direction, source = _infer_risk_direction(
                dim, group, feat, lr_long, corr_long, data_rows, splits,
            )
            if direction is None:
                skipped.append({'分群维度': ctx[0], '分群名称': ctx[1], '特征': ctx[2], '原因': '方向无法推断'})
                if verbose:
                    print('  [跳过] 方向无法推断')
                continue
            cutoff = _pick_cutoff_by_direction(splits, x_raw, y, direction, cfg)
            if cutoff is None:
                skipped.append({'分群维度': ctx[0], '分群名称': ctx[1], '特征': ctx[2], '原因': '无有效切点'})
                if verbose:
                    print('  [跳过] 无有效切点')
                continue
        else:
            # 兜底路径：zero-inflated count 特征 → 用 "> mode" 作为手工切点
            mode_val = _check_zero_inflated(
                x_raw, cfg.get('ZERO_INFLATE_RATIO_THRESHOLD', 0.80),
            )
            if mode_val is None:
                reason = 'optbinning未收敛' if optb_out is None else '无有效分箱'
                skipped.append({'分群维度': ctx[0], '分群名称': ctx[1], '特征': ctx[2], '原因': reason})
                if verbose:
                    print(f'  [跳过] {reason}')
                continue
            # 没有 binning_table；风险方向只能走 lr/corr，不能走 bin_jump
            direction, source = _infer_risk_direction(
                dim, group, feat, lr_long, corr_long, pd.DataFrame(), np.array([mode_val]),
            )
            if direction is None:
                skipped.append({'分群维度': ctx[0], '分群名称': ctx[1], '特征': ctx[2], '原因': 'zero_inflated但无方向'})
                if verbose:
                    print('  [跳过] zero_inflated 但 LR/corr 方向缺失')
                continue
            cutoff = float(mode_val)
            data_rows = _build_manual_binning_rows(x_raw, y, cutoff)
            splits = np.array([cutoff])
            cutoff_source = 'zero_inflate_fallback'
            if verbose:
                print(f'  [兜底] zero_inflated mode={mode_val} → 手工切点 > {mode_val}')

        metrics = _evaluate_rule(x_raw, y, cutoff, direction, cfg)

        # 参考 IV：优先分群 IV，回落全样本 IV
        iv_val, iv_source = _lookup_iv(iv_full, iv_group, ctx[0], ctx[1], ctx[2])

        valid, fail_reason = _judge_validity(metrics, iv_val, cfg)
        sig = _significance_label(metrics['卡方p值'])
        rule_text = _build_rule_text(feat, cutoff, direction, metrics)

        rows.append({
            '分群维度': ctx[0],
            '分群名称': ctx[1],
            '特征': ctx[2],
            '风险方向': direction,
            '方向来源': source,
            '段总样本数': n_total,
            '段坏客户数': n_bad,
            '段坏率': round(bad_rate_seg, 4),
            '候选阈值': round(float(cutoff), 6),
            '切点来源': cutoff_source,
            '高风险侧样本数': metrics['高风险侧样本数'],
            '高风险侧坏客户数': metrics['高风险侧坏客户数'],
            '高风险侧坏率': round(metrics['高风险侧坏率'], 4),
            '低风险侧样本数': metrics['低风险侧样本数'],
            '低风险侧坏客户数': metrics['低风险侧坏客户数'],
            '低风险侧坏率': round(metrics['低风险侧坏率'], 4),
            '风险倍数': round(metrics['风险倍数'], 2),
            '卡方p值': round(metrics['卡方p值'], 6),
            '显著性': sig,
            '触警率': round(metrics['触警率'], 4),
            '全局IV': round(iv_val, 4) if iv_val is not None and not pd.isna(iv_val) else np.nan,
            'IV来源': iv_source,
            '规则有效': bool(valid),
            '不通过原因': fail_reason,
            '规则文本': rule_text,
        })

        # 分箱明细：标注候选阈值落在哪条边界
        detail = data_rows.copy()
        detail.insert(0, '分群维度', ctx[0])
        detail.insert(1, '分群名称', ctx[1])
        detail.insert(2, '特征', ctx[2])
        detail['是否候选阈值边界'] = _mark_cutoff_boundary(detail, splits, cutoff)
        details.append(detail)

        if verbose:
            print(
                f'  阈值={cutoff:.4f} | 方向={direction}({source}) | '
                f'风险倍数={metrics["风险倍数"]:.2f}x | p={metrics["卡方p值"]:.4f} {sig} | '
                f'触警率={metrics["触警率"]:.1%} | 有效={valid}'
            )

    summary_df = pd.DataFrame(rows)
    detail_df = pd.concat(details, ignore_index=True) if details else pd.DataFrame()

    return ExploreOutcome(summary_df=summary_df, detail_df=detail_df,
                           skipped=skipped, gates=_export_gates(cfg))


# ---------------------------------------------------------------------------
# 内部步骤
# ---------------------------------------------------------------------------

def _validate_inputs(df, dim, group, feat, target_col, cfg) -> Optional[str]:
    if dim not in df.columns:
        return f'分群维度列不存在: {dim}'
    if feat not in df.columns:
        return f'特征列不存在: {feat}'
    if target_col not in df.columns:
        return f'目标列不存在: {target_col}'

    mask = df[dim] == group
    if not mask.any():
        return f'分群无样本: {group}'
    sub = df[mask]
    n_total = len(sub)
    n_bad = int(pd.to_numeric(sub[target_col], errors='coerce').fillna(0).sum())

    if n_total < cfg['MIN_SEGMENT_SAMPLES']:
        return f'段样本不足(n={n_total}<{cfg["MIN_SEGMENT_SAMPLES"]})'
    if n_bad < cfg['MIN_SEGMENT_BADS']:
        return f'段坏客户不足(bad={n_bad}<{cfg["MIN_SEGMENT_BADS"]})'
    if n_bad == n_total or n_bad == 0:
        return '段内单类别目标'

    s = pd.to_numeric(sub[feat], errors='coerce')
    if s.notna().sum() == 0 or s.nunique(dropna=True) <= 1:
        return '特征无变异'
    return None


def _optbin_segment(
    x_raw, y, feat, cfg: Optional[dict] = None,
) -> Optional[Tuple[np.ndarray, pd.DataFrame]]:
    """跑 optbinning，返回 (splits, data_rows)；失败返回 None。

    cfg 可覆盖 OPTBIN_PARAMS['min_bin_size']（通过 cfg['OPTBIN_MIN_BIN_SIZE']，CLI --min-bin-size）。
    """
    try:
        from optbinning import OptimalBinning  # 延迟导入：让没装 optbinning 的环境只在调用时炸
    except ImportError as e:
        raise RuntimeError(
            'risk_threshold_explore 需要 optbinning 包。请安装：pip install optbinning'
        ) from e

    params = dict(OPTBIN_PARAMS)
    if cfg is not None and cfg.get('OPTBIN_MIN_BIN_SIZE') is not None:
        params['min_bin_size'] = cfg['OPTBIN_MIN_BIN_SIZE']

    x = pd.Series(x_raw).fillna(pd.Series(x_raw).median()).values
    try:
        optb = OptimalBinning(name=feat, **params)
        optb.fit(x, y)
    except Exception:
        return None

    if optb.status not in ('OPTIMAL', 'FEASIBLE'):
        return None

    splits = np.asarray(optb.splits)
    bt = optb.binning_table.build()
    data_rows = bt[~bt['Bin'].isin(['Special', 'Missing', ''])].copy()
    data_rows = data_rows.reset_index(drop=True)
    # 末行可能是 Totals；剔除
    if 'Bin' in data_rows.columns:
        data_rows = data_rows[~data_rows['Bin'].astype(str).str.lower().str.contains('total')].reset_index(drop=True)
    # 列名汉化：与 pipeline 风格一致（IV分量 / 坏率 / 样本数 ...）
    data_rows = data_rows.rename(columns=_OPTBIN_RENAME)
    # 业务用不到 JS（Jensen-Shannon），丢掉
    data_rows = data_rows.drop(columns=['JS'], errors='ignore')
    return splits, data_rows


def _check_zero_inflated(x_raw, threshold: float = 0.80) -> Optional[float]:
    """某常值占比 ≥ threshold 时返回该常值，否则 None。

    用于 zero-inflated count 特征（如某占比 95% 为 0）：optbinning 拿不出 splits 时，
    用 "> 常值" 作为手工切点兜底。
    """
    s = pd.Series(x_raw).dropna()
    if s.empty:
        return None
    mode_val = s.mode()
    if mode_val.empty:
        return None
    mv = mode_val.iloc[0]
    try:
        mv_f = float(mv)
    except (TypeError, ValueError):
        return None
    if (s == mv).mean() >= threshold:
        return mv_f
    return None


def _build_manual_binning_rows(x_raw, y, cutoff: float) -> pd.DataFrame:
    """zero-inflated 兜底切点产生的"≤ cutoff vs > cutoff" 两行手工分箱明细。

    与 optbinning binning_table.build() 中文列对齐：分箱 / 样本数 / 占比 / 好客户数 /
    坏客户数 / 坏率 / WoE / IV分量。
    WoE 与 IV分量按口径手算（与全局 IV 不一致时可能略有偏差，但仅用于落 CSV 参考）。
    """
    x = pd.to_numeric(pd.Series(x_raw), errors='coerce')
    y_arr = pd.Series(y).astype(int)
    n_total = int(x.notna().sum())
    n_bad_total = int(((x.notna()) & (y_arr == 1)).sum())
    n_good_total = n_total - n_bad_total

    rows = []
    for label, mask in [
        (f'(-inf, {cutoff:.4f}]', (x <= cutoff)),
        (f'({cutoff:.4f}, inf)', (x > cutoff)),
    ]:
        n = int(mask.sum())
        n_bad = int(((mask) & (y_arr == 1)).sum())
        n_good = n - n_bad
        rate = (n_bad / n) if n else 0.0
        # WoE = ln(分布好 / 分布坏)；零保护
        p_good = n_good / max(n_good_total, 1)
        p_bad = n_bad / max(n_bad_total, 1)
        if p_good > 0 and p_bad > 0:
            woe = float(np.log(p_good / p_bad))
            iv_part = float((p_good - p_bad) * woe)
        else:
            woe = 0.0
            iv_part = 0.0
        rows.append({
            '分箱': label,
            '样本数': n,
            '占比': round(n / max(n_total, 1), 6),
            '好客户数': n_good,
            '坏客户数': n_bad,
            '坏率': round(rate, 6),
            'WoE': round(woe, 6),
            'IV分量': round(iv_part, 6),
        })
    return pd.DataFrame(rows)


def _infer_risk_direction(
    dim, group, feat, lr_long, corr_long, data_rows, splits,
) -> Tuple[Optional[str], Optional[str]]:
    """优先级：lr 系数 → corr → 分箱跳变方向。返回 (direction, source)。"""
    def _normalize(d):
        if isinstance(d, pd.DataFrame) and not d.empty:
            return d
        return None

    lr = _normalize(lr_long)
    if lr is not None and {'分群维度', '分群名称', '特征', '系数'}.issubset(lr.columns):
        m = (lr['分群维度'] == dim) & (lr['分群名称'] == group) & (lr['特征'] == feat)
        if m.any():
            coef = pd.to_numeric(lr.loc[m, '系数'], errors='coerce').dropna()
            if not coef.empty and abs(coef.iloc[0]) > 1e-6:
                return ('positive' if coef.iloc[0] > 0 else 'negative'), 'lr'

    co = _normalize(corr_long)
    if co is not None and {'分群维度', '分群名称', '特征', '相关系数'}.issubset(co.columns):
        m = (co['分群维度'] == dim) & (co['分群名称'] == group) & (co['特征'] == feat)
        if m.any():
            cval = pd.to_numeric(co.loc[m, '相关系数'], errors='coerce').dropna()
            if not cval.empty and abs(cval.iloc[0]) > 1e-6:
                return ('positive' if cval.iloc[0] > 0 else 'negative'), 'corr'

    # 回落：分箱跳变方向
    if '坏率' in data_rows.columns and len(data_rows) >= 2:
        rates = pd.to_numeric(data_rows['坏率'], errors='coerce').values
        diffs = np.diff(rates)
        if np.all(np.isnan(diffs)) or len(diffs) == 0:
            return None, None
        idx = int(np.nanargmax(np.abs(diffs)))
        if not np.isfinite(diffs[idx]) or diffs[idx] == 0:
            return None, None
        return ('positive' if diffs[idx] > 0 else 'negative'), 'bin_jump'

    return None, None


def _pick_cutoff_by_direction(splits, x_raw, y, direction, cfg) -> Optional[float]:
    """在 splits 中枚举切点，按已锁定方向计算风险倍数，取最大者。"""
    x = pd.Series(x_raw).fillna(pd.Series(x_raw).median()).values
    best_cut = None
    best_ratio = -1.0
    for s in splits:
        m_eval = _evaluate_rule(x, y, float(s), direction, cfg)
        rr = m_eval['风险倍数']
        # NaN 检查
        if rr is None or (isinstance(rr, float) and not np.isfinite(rr) and rr != cfg['RISK_RATIO_CAP']):
            continue
        if rr > best_ratio:
            best_ratio = rr
            best_cut = float(s)
    return best_cut


def _evaluate_rule(x_raw, y, cutoff, direction, cfg) -> dict:
    """已知 cutoff 与方向，算高/低风险侧的统计量 + 卡方 p + 触警率。"""
    x = pd.Series(x_raw).fillna(pd.Series(x_raw).median()).values
    y = np.asarray(y).astype(int)

    above = x > cutoff
    below = ~above
    n_above = int(above.sum())
    n_below = int(below.sum())
    bad_above = int(y[above].sum())
    bad_below = int(y[below].sum())
    rate_above = bad_above / n_above if n_above else 0.0
    rate_below = bad_below / n_below if n_below else 0.0

    if direction == 'positive':
        # 大于 cutoff = 高风险侧
        high_n, low_n = n_above, n_below
        high_bad, low_bad = bad_above, bad_below
        high_rate, low_rate = rate_above, rate_below
    else:
        # negative：小于等于 cutoff = 高风险侧
        high_n, low_n = n_below, n_above
        high_bad, low_bad = bad_below, bad_above
        high_rate, low_rate = rate_below, rate_above

    if low_rate <= 0:
        risk_ratio = cfg['RISK_RATIO_CAP']
    else:
        risk_ratio = min(high_rate / low_rate, cfg['RISK_RATIO_CAP'])

    # 卡方
    p_val = 1.0
    try:
        from scipy.stats import chi2_contingency
        table = np.array([
            [high_bad, high_n - high_bad],
            [low_bad, low_n - low_bad],
        ])
        if table.min() >= 0 and table.sum() > 0 and (table.sum(axis=1) > 0).all() and (table.sum(axis=0) > 0).all():
            _, p_val, _, _ = chi2_contingency(table)
    except Exception:
        p_val = 1.0

    total_n = n_above + n_below
    alert_rate = high_n / total_n if total_n else 0.0

    return {
        '高风险侧样本数': high_n,
        '低风险侧样本数': low_n,
        '高风险侧坏客户数': high_bad,
        '低风险侧坏客户数': low_bad,
        '高风险侧坏率': high_rate,
        '低风险侧坏率': low_rate,
        '风险倍数': float(risk_ratio),
        '卡方p值': float(p_val),
        '触警率': float(alert_rate),
    }


def _judge_validity(metrics: dict, iv_val, cfg) -> Tuple[bool, str]:
    """五道门槛 AND。失败时返回最先未通过的门槛名；通过时返回 '-' 哨兵。

    iv_val: 由 _lookup_iv 返回，优先分群 IV、缺失回落全样本 IV。
    """
    min_iv = cfg.get('MIN_IV', cfg.get('MIN_IV_FULL', 0.02))
    # 1. 风险倍数
    if not (metrics['风险倍数'] >= cfg['MIN_RISK_RATIO']):
        return False, f'风险倍数 < {cfg["MIN_RISK_RATIO"]}'
    # 2. p 值
    if not (metrics['卡方p值'] <= cfg['MAX_P_VALUE']):
        return False, f'卡方p值 > {cfg["MAX_P_VALUE"]}'
    # 3. 高风险侧坏客户数
    if not (metrics['高风险侧坏客户数'] >= cfg['MIN_BAD_HIGH_SIDE']):
        return False, f'高风险侧坏客户数 < {cfg["MIN_BAD_HIGH_SIDE"]}'
    # 4. 触警率区间
    if metrics['触警率'] < cfg['ALERT_RATE_MIN']:
        return False, f'触警率 < {cfg["ALERT_RATE_MIN"]:.1%}'
    if metrics['触警率'] > cfg['ALERT_RATE_MAX']:
        return False, f'触警率 > {cfg["ALERT_RATE_MAX"]:.1%}'
    # 5. 参考 IV
    if iv_val is None or (isinstance(iv_val, float) and pd.isna(iv_val)):
        return False, 'IV缺失'
    if iv_val < min_iv:
        return False, f'IV < {min_iv}'
    return True, '-'


def _lookup_iv_full(iv_full: Optional[pd.DataFrame], feat: str) -> Optional[float]:
    if iv_full is None or iv_full.empty:
        return None
    feat_col = '特征' if '特征' in iv_full.columns else ('特征名称' if '特征名称' in iv_full.columns else None)
    if feat_col is None or 'IV值' not in iv_full.columns:
        return None
    m = iv_full[feat_col].astype(str) == str(feat)
    if not m.any():
        return None
    v = pd.to_numeric(iv_full.loc[m, 'IV值'], errors='coerce').dropna()
    return float(v.iloc[0]) if not v.empty else None


def _lookup_iv(
    iv_full: Optional[pd.DataFrame],
    iv_group_all: Optional[pd.DataFrame],
    dim: str, group: str, feat: str,
) -> Tuple[Optional[float], str]:
    """优先分群 IV (iv_group_all)，缺失回落到全样本 IV (iv_full)。

    Returns:
        (iv_value, source) - source ∈ {'group', 'full', 'missing'}
    """
    # 1. 分群 IV
    if iv_group_all is not None and not iv_group_all.empty:
        cols = iv_group_all.columns
        feat_col = '特征' if '特征' in cols else ('特征名称' if '特征名称' in cols else None)
        if feat_col and {'分群维度', '分群名称', 'IV值'}.issubset(cols):
            m = (
                (iv_group_all['分群维度'].astype(str) == str(dim))
                & (iv_group_all['分群名称'].astype(str) == str(group))
                & (iv_group_all[feat_col].astype(str) == str(feat))
            )
            if m.any():
                v = pd.to_numeric(iv_group_all.loc[m, 'IV值'], errors='coerce').dropna()
                if not v.empty:
                    return float(v.iloc[0]), 'group'
    # 2. 全样本 IV 兜底
    v_full = _lookup_iv_full(iv_full, feat)
    if v_full is not None and not pd.isna(v_full):
        return float(v_full), 'full'
    return None, 'missing'


def _significance_label(p_val: float) -> str:
    for thresh, label in SIGNIFICANCE_LABELS:
        if p_val < thresh:
            return label
    return 'ns'


def _build_rule_text(feat: str, cutoff: float, direction: str, metrics: dict) -> str:
    op = '大于' if direction == 'positive' else '小于等于'
    return (
        f'{feat} {op} {cutoff:.4f} 时，'
        f'坏客户率 {metrics["高风险侧坏率"]:.2%}，'
        f'是低风险侧的 {metrics["风险倍数"]:.1f} 倍，'
        f'触警率 {metrics["触警率"]:.1%}'
    )


def _mark_cutoff_boundary(detail: pd.DataFrame, splits, cutoff: float) -> List[int]:
    """对每条分箱行，若它的右边界与候选阈值重合则标 1，否则 0。"""
    flags = [0] * len(detail)
    # splits 是 numpy array of split points；cutoff 一定来自其中之一
    # 简单策略：对每行 bin 文本（如 "(-inf, 0.42]"）尝试解析右端，与 cutoff 比较
    for i, row in detail.iterrows():
        bin_str = str(row.get('分箱', ''))
        if not bin_str:
            continue
        # 解析形如 "(-inf, 0.42]" / "(0.42, 0.78]" / "(0.78, inf)"
        rhs = bin_str.split(',')[-1].strip(' ])')
        try:
            rhs_val = float(rhs)
        except (ValueError, TypeError):
            continue
        if np.isfinite(rhs_val) and abs(rhs_val - float(cutoff)) < 1e-9:
            flags[i] = 1
    return flags


def _export_gates(cfg: dict) -> dict:
    return {
        'min_risk_ratio': cfg['MIN_RISK_RATIO'],
        'max_p': cfg['MAX_P_VALUE'],
        'min_bad_high': cfg['MIN_BAD_HIGH_SIDE'],
        'alert_rate_min': cfg['ALERT_RATE_MIN'],
        'alert_rate_max': cfg['ALERT_RATE_MAX'],
        'min_iv': cfg['MIN_IV_FULL'],
    }


__all__ = ['explore_thresholds', 'ExploreOutcome']
