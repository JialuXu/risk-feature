"""Step 3 六道校验关. 每个 check 都是 (proposal, ctx) -> CheckResult."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckResult:
    """单条提案在某道关的结果."""
    check_name: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


__all__ = ["CheckResult"]
