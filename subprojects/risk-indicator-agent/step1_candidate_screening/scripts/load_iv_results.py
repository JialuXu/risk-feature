"""跨项目加载 IV 结果. 优先用 risk_result_query, 失败则降级直读 CSV."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# 缺省: 同仓库的 risk-feature-pipeline/ (本文件位于 subprojects/risk-indicator-agent/step1_*/scripts/)
_DEFAULT_PIPELINE_ROOT = Path(__file__).resolve().parents[4] / "risk-feature-pipeline"


def _try_use_risk_result_query(pipeline_root: Path) -> bool:
    """尝试把 risk-feature-pipeline 加到 sys.path 以便 import risk_result_query."""
    if str(pipeline_root) not in sys.path:
        sys.path.insert(0, str(pipeline_root))
    try:
        import risk_result_query  # noqa: F401
        return True
    except ImportError as e:
        logger.warning("无法 import risk_result_query: %s; 将直读 CSV", e)
        return False


def _load_via_query(project_dir: Path) -> dict[str, pd.DataFrame] | None:
    """复用姊妹项目的 load_results.

    load_results(project_name, project_root, results_base) 期望 project_root
    下有 results_base/subdir 结构. 这里反推:
        results_base = project_dir.parent.relative_to(project_root)
    """
    project_name = project_dir.name
    parent = project_dir.parent
    # 推断 project_root: 找包含 'data/results' 的最近祖先
    project_root = None
    for anc in [parent.parent, parent.parent.parent]:
        if (anc / "data" / "results").exists():
            project_root = anc
            break
    if project_root is None:
        return None
    try:
        from risk_result_query.scripts import load_results
        rel_base = parent.relative_to(project_root)
        result = load_results(
            project_name,
            project_root=str(project_root),
            results_base=str(rel_base),
        )
    except Exception as e:
        logger.warning("load_results(%s) 失败: %s; 改用直读", project_name, e)
        return None
    return {
        "iv_full": getattr(result, "iv_full", None),
        "lr_coef_long": getattr(result, "lr_coef_long", None),
        "comprehensive": getattr(result, "comprehensive", None),
    }


def _load_via_csv(project_dir: Path) -> dict[str, pd.DataFrame]:
    """直读 CSV (fallback)."""
    project_name = project_dir.name
    pattern = f"{project_name}_"
    out: dict[str, pd.DataFrame] = {}
    candidates = {
        "iv_full": "IV分析结果.csv",
        "lr_coef_long": "逻辑回归系数.csv",
        "comprehensive": "综合特征分析结果.csv",
    }
    for key, suffix in candidates.items():
        p = project_dir / f"{pattern}{suffix}"
        if p.exists():
            try:
                out[key] = pd.read_csv(p, encoding="utf-8-sig")
            except Exception as e:
                logger.warning("读 %s 失败: %s", p, e)
    return out


def aggregate_iv(results_dirs: list[str | Path],
                 pipeline_root: Path | None = None) -> pd.DataFrame:
    """跨多个 project 加载 iv_full 并合并. 列含 项目名."""
    frames = []
    has_query = _try_use_risk_result_query(pipeline_root or _DEFAULT_PIPELINE_ROOT)

    for d in results_dirs:
        d = Path(d)
        if not d.exists():
            logger.warning("results 目录不存在: %s", d)
            continue
        loaded = _load_via_query(d) if has_query else None
        if loaded is None or loaded.get("iv_full") is None:
            loaded = _load_via_csv(d)
        iv_df = loaded.get("iv_full")
        if iv_df is None or iv_df.empty:
            logger.warning("项目 %s 无 iv_full", d.name)
            continue
        iv_df = iv_df.copy()
        iv_df["项目"] = d.name
        frames.append(iv_df)

    if not frames:
        return pd.DataFrame(columns=["分群", "特征", "IV值", "IV可信度",
                                     "缺失样本数", "分群总样本数", "项目"])
    return pd.concat(frames, ignore_index=True)


def aggregate_lr(results_dirs: list[str | Path],
                 pipeline_root: Path | None = None) -> pd.DataFrame:
    """跨项目加载 LR 系数. 用于推断风险方向."""
    frames = []
    has_query = _try_use_risk_result_query(pipeline_root or _DEFAULT_PIPELINE_ROOT)

    for d in results_dirs:
        d = Path(d)
        if not d.exists():
            continue
        loaded = _load_via_query(d) if has_query else None
        if loaded is None or loaded.get("lr_coef_long") is None:
            loaded = _load_via_csv(d)
        df = loaded.get("lr_coef_long")
        if df is None or df.empty:
            continue
        df = df.copy()
        df["项目"] = d.name
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


__all__ = ["aggregate_iv", "aggregate_lr"]
