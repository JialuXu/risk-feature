# -*- coding: utf-8 -*-
"""中文字体探测：转发到 `risk_pipeline.font_utils`（链路级唯一权威）。

历史背景：原本只在 `risk_visualization` 用，后来 `risk_segment_univariate.boxplot`
也要画中文图，避免循环依赖把实现提到 `risk_pipeline.font_utils`。这里仅保留
旧导入路径的薄壳，不要在这里再加逻辑。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 确保 risk-feature-pipeline/ 在 sys.path 上（被 chart_*.py from . import 触发时仍可用）
_SKILL_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)

from risk_pipeline.font_utils import configure_chinese_font, active_font  # noqa: F401

__all__ = ['configure_chinese_font', 'active_font']
