"""把 validated 提案打包成给数仓的工单 JSON + SQL 骨架."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import jinja2

from indicator_pipeline.config import AgentConfig


def build_request_payload(
    batch_id: str,
    validated_proposals: list[dict[str, Any]],
    submitter: str = "risk-indicator-agent",
    response_timeout_hours: int = 168,
) -> dict[str, Any]:
    """工单 JSON."""
    expected = (datetime.now() + _td_hours(response_timeout_hours)).date().isoformat()
    indicators = []
    for p in validated_proposals:
        indicators.append({
            "ind_code": p.get("ind_code"),
            "ind_version": int(p.get("ind_version", 1)),
            "ind_name_cn": p.get("ind_name_cn", ""),
            "domain": p.get("domain", ""),
            "biz_definition": p.get("biz_definition", ""),
            "calc_logic_pseudo": p.get("calc_logic", ""),
            "source_tables": p.get("source_tables", []),
            "source_fields": p.get("source_fields", []),
            "ref_date_logic": p.get("ref_date_logic", "BATCH_MAX"),
            "null_handling": p.get("null_handling", []),
            "post_processing_rule": p.get("post_processing_rule", "NONE"),
            "is_dynamic_expansion": int(p.get("is_dynamic_expansion", 0)),
            "dynamic_template": p.get("dynamic_template"),
            "expected_iv_range": _expected_iv_range(p),
            "expected_coverage_rate": p.get("current_coverage_rate"),
            "sql_skeleton_hint_path": (
                f"sql_skeletons/{p.get('ind_code')}.sql"
            ),
        })

    return {
        "batch_id": batch_id,
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "submitter": submitter,
        "expected_response_by": expected,
        "verification_window": {
            "snap_dt_start": "${TBD_BY_DATAWAREHOUSE}",
            "snap_dt_end": "${TBD_BY_DATAWAREHOUSE}",
            "sample_size_target": 5000,
        },
        "indicators": indicators,
    }


def _td_hours(hours: int):
    from datetime import timedelta
    return timedelta(hours=hours)


def _expected_iv_range(p: dict[str, Any]) -> list[float] | None:
    """基于已知 current_iv 给数仓一个期望区间."""
    iv = p.get("current_iv")
    if iv is None:
        return None
    iv = float(iv)
    return [round(max(0.0, iv * 0.7), 4), round(iv * 1.3, 4)]


def render_sql_skeletons(
    project_root: Path,
    indicators: list[dict[str, Any]],
    out_dir: Path,
) -> list[Path]:
    """为每条提案渲染一份 SQL 骨架到 batch 目录."""
    template_path = project_root / "step4_shadow_iv" / "contracts" / "sql_skeleton_template.sql.j2"
    template_text = template_path.read_text(encoding="utf-8")
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    template = env.from_string(template_text)

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    generated_at = datetime.now().isoformat(timespec="seconds")
    for ind in indicators:
        ctx = {
            "ind_code": ind["ind_code"],
            "ind_name_cn": ind.get("ind_name_cn", ""),
            "ind_version": ind.get("ind_version", 1),
            "domain": ind.get("domain", ""),
            "biz_definition": ind.get("biz_definition", ""),
            "calc_logic_pseudo": ind.get("calc_logic_pseudo", ""),
            "source_tables": ind.get("source_tables", []) or ["TODO_SOURCE_TABLE"],
            "source_fields": ind.get("source_fields", []) or ["TODO"],
            "ref_date_logic": ind.get("ref_date_logic", "BATCH_MAX"),
            "null_handling": ind.get("null_handling", []) or ["KEEP_NULL"],
            "post_processing_rule": ind.get("post_processing_rule", "NONE"),
            "generated_at": generated_at,
        }
        sql = template.render(**ctx)
        path = out_dir / f"{ind['ind_code']}.sql"
        path.write_text(sql, encoding="utf-8")
        paths.append(path)
    return paths
