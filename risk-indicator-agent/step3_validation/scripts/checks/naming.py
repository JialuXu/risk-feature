"""关 1: 命名规范校验."""

from __future__ import annotations

from typing import Any

from indicator_pipeline.naming import validate_ind_code

from . import CheckResult


def check(proposal: dict[str, Any], ctx: dict[str, Any]) -> CheckResult:
    code = proposal.get("ind_code", "")
    ok, errs = validate_ind_code(code)
    return CheckResult(
        check_name="naming",
        passed=ok,
        errors=errs,
    )
