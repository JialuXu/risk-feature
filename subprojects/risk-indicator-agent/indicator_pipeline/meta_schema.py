"""把 meta_schema.yaml 编译成 jsonschema validator."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from .config_loader import load_meta_schema


@lru_cache(maxsize=1)
def _get_validator(project_root_str: str | None = None) -> Draft202012Validator:
    project_root = Path(project_root_str) if project_root_str else None
    schema_doc = load_meta_schema(project_root)
    indicator_schema = schema_doc["indicator_schema"]
    return Draft202012Validator(indicator_schema)


def validate_indicator(record: dict[str, Any], project_root: Path | None = None) -> list[str]:
    """校验单条指标记录. 返回错误信息列表;空表示通过."""
    validator = _get_validator(str(project_root) if project_root else None)
    errors = []
    for err in validator.iter_errors(record):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"[{path}] {err.message}")
    return errors


def get_meta_schema(project_root: Path | None = None) -> dict[str, Any]:
    """返回完整 schema (含 enum / 默认值等元数据)."""
    return load_meta_schema(project_root)


def get_required_fields(project_root: Path | None = None) -> list[str]:
    return get_meta_schema(project_root)["indicator_schema"]["required"]


def get_field_enum(field_name: str, project_root: Path | None = None) -> list[str] | None:
    schema = get_meta_schema(project_root)["indicator_schema"]["properties"]
    if field_name not in schema:
        return None
    return schema[field_name].get("enum")


def get_domain_prefixes(project_root: Path | None = None) -> dict[str, str]:
    return get_meta_schema(project_root).get("domain_prefixes", {})


def get_default_post_processing(domain: str, project_root: Path | None = None) -> str:
    defaults = get_meta_schema(project_root).get("default_post_processing", {})
    return defaults.get(domain, "NONE")


__all__ = [
    "validate_indicator",
    "get_meta_schema",
    "get_required_fields",
    "get_field_enum",
    "get_domain_prefixes",
    "get_default_post_processing",
    "ValidationError",
]
