# -*- coding: utf-8 -*-
"""中文字体探测：转发到 `risk_core.font_utils`（链路级唯一权威）。

历史背景：原本只在 `risk_visualization` 用，后来 `risk_segment_univariate.boxplot`
也要画中文图，避免循环依赖把实现提到底座 font_utils（现居 `risk_core`）。这里
仅保留旧导入路径的薄壳，不要在这里再加逻辑。
"""
from __future__ import annotations


from risk_core.font_utils import configure_chinese_font, active_font  # noqa: F401

__all__ = ['configure_chinese_font', 'active_font']
