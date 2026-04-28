"""关 4: 与元表已有指标做去重 (rapidfuzz)."""

from __future__ import annotations

from typing import Any

from indicator_pipeline.dedup import check_duplicate

from . import CheckResult


def check(proposal: dict[str, Any], ctx: dict[str, Any]) -> CheckResult:
    existing_pairs: list[tuple[str, str]] = ctx.get("existing_pairs", [])
    threshold = ctx.get("dedup_threshold", 85.0)
    method = ctx.get("dedup_method", "token_set_ratio")

    result = check_duplicate(
        proposal,
        existing_pairs=existing_pairs,
        threshold=threshold,
        method=method,
    )

    extra = {
        "matched_code": result.matched_code,
        "matched_name": result.matched_name,
        "score": result.score,
    }

    if result.is_duplicate:
        return CheckResult(
            check_name="dedup",
            passed=False,
            errors=[
                f"与元表已有指标重复 (score={result.score:.1f} >= {threshold}): "
                f"{result.matched_code} ({result.matched_name})"
            ],
            extra=extra,
        )

    # 高分但不到阈值 → 警告
    warnings = []
    if result.score >= threshold * 0.85:
        warnings.append(
            f"与 {result.matched_code} ({result.matched_name}) 相似度 {result.score:.1f}, "
            f"建议人审确认"
        )

    return CheckResult(
        check_name="dedup",
        passed=True,
        warnings=warnings,
        extra=extra,
    )
