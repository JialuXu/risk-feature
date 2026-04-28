"""关 5: calc_logic 静态解析. 不要求可执行 SQL, 但要能从中识别函数和列引用."""

from __future__ import annotations

from typing import Any

from indicator_pipeline.sql_static import analyze_calc_logic

from . import CheckResult


def check(proposal: dict[str, Any], ctx: dict[str, Any]) -> CheckResult:
    calc = proposal.get("calc_logic", "")
    if not calc or len(calc) < 5:
        return CheckResult(
            check_name="calc_logic",
            passed=False,
            errors=["calc_logic 为空或过短"],
        )

    result = analyze_calc_logic(calc)
    errors: list[str] = []
    warnings: list[str] = []

    if not result.parseable:
        # 伪式不一定能 parse, 不强制 reject; 但记录 warning
        warnings.append(f"sqlglot 无法解析 (伪式可接受): {result.parse_error}")

    # 禁词检查
    if result.forbidden_used:
        errors.append(
            f"使用了被禁的时间函数 {result.forbidden_used}; "
            f"参考日期请走 ref_date_logic 字段约定 (BATCH_MAX 等)"
        )

    return CheckResult(
        check_name="calc_logic",
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        extra={
            "parseable": result.parseable,
            "referenced_columns": result.referenced_columns,
            "referenced_functions": result.referenced_functions,
        },
    )
