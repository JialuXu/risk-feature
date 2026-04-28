# -*- coding: utf-8 -*-
"""DEPRECATION SHIM：`python -m shared` 入口 → 转发到 risk_pipeline。

旧命令 `python -m shared --pipeline credit` 仍可工作（保持向后兼容），但会
打印 deprecation 警告。Phase 5 会把这里改成转发到新 CLI（`run --pipeline X`）。
"""
import sys

print(
    "[DEPRECATION] `python -m shared` 已重命名为 `python -m risk_pipeline`；"
    "下一版本会移除老入口。",
    file=sys.stderr,
)

from risk_pipeline.pipeline import main as _legacy_main  # noqa: E402

_legacy_main()
