"""关 2: jsonschema 必填字段 + 类型校验."""

from __future__ import annotations

from typing import Any

from indicator_pipeline.meta_schema import validate_indicator

from . import CheckResult


def check(proposal: dict[str, Any], ctx: dict[str, Any]) -> CheckResult:
    project_root = ctx.get("project_root")
    errs = validate_indicator(proposal, project_root=project_root)
    return CheckResult(
        check_name="schema",
        passed=len(errs) == 0,
        errors=errs,
    )
