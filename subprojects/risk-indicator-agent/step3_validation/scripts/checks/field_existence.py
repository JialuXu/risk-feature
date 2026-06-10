"""关 3: 依赖字段在「表字段清单.csv」中真的存在.

source_fields 期望格式: `表英文名.字段英文名(中文)` 或 `表英文名.字段英文名`.
对每条做 exact lookup; 找不到 → 警告 (不直接 reject, 因为可能是缺口表 + 提案 P0-阻塞).
"""

from __future__ import annotations

import re
from typing import Any

from indicator_pipeline.field_dict import FieldDict

from . import CheckResult

_FIELD_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]+)\.([A-Z][A-Z0-9_]+)")


def check(proposal: dict[str, Any], ctx: dict[str, Any]) -> CheckResult:
    fd: FieldDict | None = ctx.get("field_dict")
    if fd is None:
        return CheckResult(check_name="field_existence", passed=True,
                          warnings=["field_dict 未提供, 跳过"])

    source_tables = proposal.get("source_tables") or []
    source_fields = proposal.get("source_fields") or []
    errors: list[str] = []
    warnings: list[str] = []

    # 1) source_tables 在表清单中
    known_tables = set(fd.list_tables())
    for t in source_tables:
        if t not in known_tables:
            warnings.append(f"表 '{t}' 不在表字段清单中 (可能是缺口表, 检查 priority 是否=P0-阻塞)")

    # 2) source_fields 解析 + exact 查
    for sf in source_fields:
        m = _FIELD_PATTERN.match(sf)
        if not m:
            warnings.append(f"source_fields 格式可疑 (期望 表名.字段名(中文)): {sf}")
            continue
        tbl, fld = m.group(1), m.group(2)
        if tbl not in known_tables:
            # 已在 warnings 里,跳过
            continue
        if not fd.field_exists(tbl, fld):
            errors.append(f"字段不存在: {tbl}.{fld}")

    # 3) 若 priority=P0-阻塞 则允许 source_tables 缺失
    priority = proposal.get("priority", "")
    if priority == "P0-阻塞" and warnings:
        # 阻塞类降级 errors 为 warnings 已 OK; 仍要检查至少有 1 个表
        pass
    elif not source_tables and priority != "P0-阻塞":
        errors.append("source_tables 为空且 priority 不是 P0-阻塞")

    return CheckResult(
        check_name="field_existence",
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
