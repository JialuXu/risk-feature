"""读数仓回填的 shadow_iv_response.json, 合并到 validated 提案."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema

from indicator_pipeline.io_utils import read_json


def load_response(response_path: Path, contracts_dir: Path) -> dict[str, Any]:
    """加载并 schema 校验数仓回填."""
    schema = read_json(contracts_dir / "shadow_iv_response_schema.json")
    payload = read_json(response_path)
    jsonschema.validate(payload, schema)
    return payload


def merge_response_into_proposals(
    validated: list[dict[str, Any]],
    response: dict[str, Any],
) -> list[dict[str, Any]]:
    """把 shadow_iv 结果合并到提案. 添加 shadow_* 字段."""
    by_code = {r["ind_code"]: r for r in response.get("results", [])}
    out = []
    for p in validated:
        code = p.get("ind_code")
        r = by_code.get(code)
        merged = dict(p)
        if r is None:
            merged["shadow_iv_status"] = "NOT_PROCESSED"
            out.append(merged)
            continue
        merged["shadow_iv_status"] = r.get("shadow_iv_status", "UNKNOWN")
        merged["shadow_iv"] = r.get("shadow_iv")
        merged["shadow_coverage_rate"] = r.get("shadow_coverage_rate")
        merged["shadow_credibility"] = r.get("shadow_credibility")
        merged["shadow_sample_size"] = r.get("shadow_sample_size")
        merged["shadow_risk_direction"] = r.get("shadow_risk_direction")
        merged["shadow_snap_dt"] = r.get("snap_dt")
        merged["shadow_error_msg"] = r.get("error_msg")
        merged["data_warehouse_run_id"] = response.get("data_warehouse_run_id")

        # 用影子 IV 更新 current_*
        if r.get("shadow_iv_status") == "SUCCESS":
            if r.get("shadow_iv") is not None:
                merged["current_iv"] = r["shadow_iv"]
            if r.get("shadow_coverage_rate") is not None:
                merged["current_coverage_rate"] = r["shadow_coverage_rate"]
            if r.get("shadow_credibility"):
                merged["current_iv_credibility"] = r["shadow_credibility"]
            if r.get("shadow_risk_direction"):
                merged["current_risk_direction"] = r["shadow_risk_direction"]
            # 追加到 iv_history
            history = list(merged.get("iv_history") or [])
            history.append({
                "snap_dt": r.get("snap_dt") or "",
                "iv": r.get("shadow_iv"),
                "credibility": r.get("shadow_credibility") or "",
                "sample_size": r.get("shadow_sample_size") or 0,
                "project": "shadow_iv_validation",
            })
            merged["iv_history"] = history

        out.append(merged)
    return out


def assign_priority_from_shadow(
    proposal: dict[str, Any],
    rules: dict[str, Any],
) -> str:
    """基于 shadow IV 重新分配 priority. 与方法论 §9 一致."""
    iv = proposal.get("current_iv")
    cov = proposal.get("current_coverage_rate")
    cred = proposal.get("current_iv_credibility")
    blocked = proposal.get("priority") == "P0-阻塞" and not proposal.get("shadow_iv_status") == "SUCCESS"

    iv_v = float(iv) if iv is not None else 0.0
    cov_v = float(cov) if cov is not None else 0.0

    if cred not in ("可信", None):
        return "P4-观察"
    if blocked:
        return "P0-阻塞"
    if iv_v >= 0.10 and cov_v >= 0.95:
        return "P0"
    if iv_v >= 0.10:
        return "P0-阻塞"
    if iv_v >= 0.05 and cov_v >= 0.80:
        return "P1"
    if cov_v < 0.50 and iv_v >= 0.02:
        return "P1-稀疏池"
    if iv_v >= 0.02:
        return "P2"
    return "P3-观察"
