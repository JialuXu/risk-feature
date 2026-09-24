# -*- coding: utf-8 -*-
"""兼容别名工具：让 ``risk_pipeline.X`` 与目标模块是**同一模块对象**。

每个别名子模块只有一行 ``alias(__name__, '<目标模块>')``：执行时把自身在
``sys.modules`` 中替换为目标模块（CPython 导入协议保证 import 语句返回替换后的对象），
于是 ``import risk_pipeline.paths is risk_core.paths`` 为 True、私有名可达、
monkeypatch 作用于同一对象。别名按需加载——``import risk_pipeline`` 本身不
连带加载 config / 分析内核。
"""
import importlib
import sys


def alias(name: str, target: str) -> None:
    sys.modules[name] = importlib.import_module(target)
