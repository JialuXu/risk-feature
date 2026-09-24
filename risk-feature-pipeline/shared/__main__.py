# -*- coding: utf-8 -*-
"""DEPRECATION SHIM：`python -m shared` 入口 → 转发到 risk_pipeline.pipeline.main。

`python -m shared --pipeline credit` 可用（兼容入口），并打印 deprecation 警告；
正式入口是 `python -m risk_pipeline run --pipeline X`。
"""
import sys

print(
    "[DEPRECATION] `python -m shared` 是兼容入口，下一版本移除；"
    "请改用 `python -m risk_pipeline run --pipeline <generic|credit|gsfc>`。",
    file=sys.stderr,
)

from risk_pipeline.pipeline import main as _legacy_main  # noqa: E402

_legacy_main()
