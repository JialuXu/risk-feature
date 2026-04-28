"""组装 seeds.json. 跨项目去重 + domain 归口 + 与元表对照."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

# 项目名 → domain 启发式映射 (用户当前项目命名约定)
_PROJECT_TO_DOMAIN = {
    "财务行业风险分析": "FIN",
    "腰部企业征信分析": "CRDTC",
    "舆情特征分析": "PUB",
    "舆情特征宽表分析": "PUB",
    "舆情风险特征分析": "PUB",
    "工商变更特征分析": "OPN",
}


def project_to_domain(project_name: str) -> str:
    """项目名 → domain 推断. 找不到时返回 UNKNOWN."""
    if project_name in _PROJECT_TO_DOMAIN:
        return _PROJECT_TO_DOMAIN[project_name]
    # fallback 关键词匹配
    name = project_name
    if "财务" in name:
        return "FIN"
    if "征信" in name:
        return "CRDTC"
    if "舆情" in name:
        return "PUB"
    if "工商" in name or "变更" in name:
        return "OPN"
    if "司法" in name or "执行" in name:
        return "JUDI"
    if "担保" in name:
        return "GUAR"
    return "UNKNOWN"


def build_seeds(
    iv_filtered: pd.DataFrame,
    risk_directions: dict[str, str],
    existing_ind_names: set[str],
    signal_thresholds: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """构造 seeds 列表 + 统计信息."""
    from .apply_filters import signal_strength

    # 跨项目去重: 同名特征保留 IV 最大那条
    if iv_filtered.empty:
        return [], {"total": 0, "after_filter": 0, "to_propose": 0,
                    "already_registered": 0, "by_domain": {}}
    df = iv_filtered.sort_values("IV值", ascending=False).drop_duplicates("特征")

    seeds: list[dict[str, Any]] = []
    by_domain: dict[str, int] = {}
    already = 0

    for _, r in df.iterrows():
        feat = str(r["特征"])
        domain = project_to_domain(str(r.get("项目", "")))
        coverage = float(r.get("coverage_rate", 0.0)) if pd.notna(
            r.get("coverage_rate", 0.0)
        ) else 0.0
        iv = float(r["IV值"]) if pd.notna(r["IV值"]) else 0.0
        cred = str(r.get("IV可信度", "未做IV分析"))
        signal = signal_strength(iv, cred, signal_thresholds)
        registered = feat in existing_ind_names

        seed = {
            "feature_name_cn": feat,
            "source_project": str(r.get("项目", "")),
            "domain": domain,
            "iv": round(iv, 4),
            "iv_credibility": cred,
            "coverage_rate": round(coverage, 4),
            "signal_strength": signal,
            "risk_direction": risk_directions.get(feat, "待验证"),
            "sample_size_total": int(r.get("分群总样本数", 0))
                if pd.notna(r.get("分群总样本数")) else 0,
            "bad_size": int(r.get("分群坏客户数", 0))
                if pd.notna(r.get("分群坏客户数", 0)) else 0,
            "already_registered": registered,
            "candidate_source": "mining_supplement",
        }
        seeds.append(seed)
        by_domain[domain] = by_domain.get(domain, 0) + 1
        if registered:
            already += 1

    stats = {
        "total": len(df),
        "after_filter": len(df),
        "to_propose": len(df) - already,
        "already_registered": already,
        "by_domain": by_domain,
    }
    return seeds, stats


def assemble_payload(batch_id: str, seeds: list[dict[str, Any]],
                     stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "stats": stats,
        "seeds": seeds,
    }


__all__ = ["project_to_domain", "build_seeds", "assemble_payload"]
