"""指标 ind_code 命名规范校验."""

from __future__ import annotations

import re

# 与 meta_schema.yaml indicator_schema.properties.ind_code.pattern 一致
_IND_CODE_PATTERN = re.compile(
    r"^(FIN|CRDTC|OPN|PUB|JUDI|LON|GUAR|RELA|FUND)_[MDA]_[A-Z0-9_]+$"
)
_VALID_DOMAINS = {"FIN", "CRDTC", "OPN", "PUB", "JUDI", "LON", "GUAR", "RELA", "FUND"}
_VALID_GRANULARITY = {"M", "D", "A", "EVT"}
_VALID_WINDOWS = {"SNAP", "M3", "M6", "M12", "Y1", "Y3", "Y5", "LIFE", "EVT"}
_VALID_STATS = {"CNT", "AMT", "RATIO", "FLG", "IDX", "STD", "CV", "AVG", "MAX", "MIN", "DAYS"}

MAX_LEN = 60


def validate_ind_code(code: str) -> tuple[bool, list[str]]:
    """校验 ind_code. 返回 (是否通过, 错误列表)."""
    errors: list[str] = []
    if not isinstance(code, str):
        return False, [f"ind_code 必须是字符串, got {type(code).__name__}"]
    if len(code) > MAX_LEN:
        errors.append(f"长度 {len(code)} 超过最大 {MAX_LEN}")
    if not _IND_CODE_PATTERN.match(code):
        errors.append(
            "格式不符合 {域}_{粒度}_{业务键}_(窗口)_(统计)；要求全大写、下划线分段、域∈"
            f"{sorted(_VALID_DOMAINS)}, 粒度∈{sorted(_VALID_GRANULARITY)}"
        )
    parts = code.split("_")
    if parts and parts[0] not in _VALID_DOMAINS:
        errors.append(f"域 '{parts[0]}' 不在白名单 {sorted(_VALID_DOMAINS)}")
    if len(parts) >= 2 and parts[1] not in _VALID_GRANULARITY:
        errors.append(f"粒度 '{parts[1]}' 不在白名单 {sorted(_VALID_GRANULARITY)}")
    return len(errors) == 0, errors


def parse_ind_code(code: str) -> dict[str, str]:
    """拆解 ind_code 为各组成部分."""
    parts = code.split("_")
    result = {"raw": code}
    if len(parts) >= 1:
        result["domain"] = parts[0]
    if len(parts) >= 2:
        result["granularity"] = parts[1]
    # 剩余部分: 中间业务键 + 末尾窗口/统计
    rest = parts[2:] if len(parts) > 2 else []
    if rest and rest[-1] in _VALID_STATS:
        result["stat"] = rest[-1]
        rest = rest[:-1]
    if rest and rest[-1] in _VALID_WINDOWS:
        result["window"] = rest[-1]
        rest = rest[:-1]
    if rest:
        result["business_key"] = "_".join(rest)
    return result


def suggest_ind_code(domain: str, business_key: str, window: str = "SNAP",
                     stat: str = "CNT", granularity: str = "M") -> str:
    """根据组件拼装一个候选 ind_code."""
    business_key = business_key.upper().replace(" ", "_")
    business_key = re.sub(r"[^A-Z0-9_]+", "_", business_key)
    business_key = re.sub(r"_+", "_", business_key).strip("_")
    parts = [domain, granularity, business_key, window, stat]
    return "_".join(p for p in parts if p)
