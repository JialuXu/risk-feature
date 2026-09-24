# -*- coding: utf-8 -*-
"""中文字体探测：转发到 `risk_core.font_utils`（链路级唯一权威）。

本模块只是保留导入路径的兼容薄壳，不要在这里加逻辑。
"""
from __future__ import annotations


from risk_core.font_utils import configure_chinese_font, active_font  # noqa: F401

__all__ = ['configure_chinese_font', 'active_font']
