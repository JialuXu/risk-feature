# -*- coding: utf-8 -*-
"""分层红线锁（DECOUPLING-DESIGN §4.1）：静态 import + 字符串式动态 import 一并检查。

旧的 grep 红线只看 ``import`` 语句，抓不到 ``importlib.import_module('risk_x...')`` /
``_load_module('risk_x', ...)`` 这类字符串导入——挖掘内核曾借此调用子 skill。本文件把
「调用参数里出现的项目包名字符串」也视为依赖：

  1. 挖掘内核（risk_mining 的 analysis / pipeline / pipeline_state / export）只依赖
     risk_core 与内核自身；唯一例外是导出步的实现 risk_export_report（§4.2 明示不拆）。
  2. risk_core 是叶子：不依赖任何其它项目包。
  3. 除兼容 shim 自身外，任何生产代码都不得依赖 risk_pipeline / shared
     （保证两个 shim 可在下个版本整体删除）。
  4. 进程级：只 import 挖掘内核，sys.modules 里不得出现子 skill / 组合根 / shim。
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

KERNEL_FILES = [
    'risk_mining/analysis/__init__.py',
    'risk_mining/analysis/engine.py',
    'risk_mining/analysis/iv_core.py',
    'risk_mining/pipeline.py',
    'risk_mining/pipeline_state.py',
    'risk_mining/export.py',
]
KERNEL_MODULES = {f[:-3].replace('/', '.').removesuffix('.__init__') for f in KERNEL_FILES}
# 导出步的实现（§4.2「risk_export_report ✗ 不拆：是 export 步的实现，归 risk_mining.export 调用」）
KERNEL_ALLOWED_SKILLS = {'risk_export_report'}

_PKG_STRING = re.compile(r'^(risk_[a-z_]+|shared)(\.[A-Za-z_][A-Za-z0-9_]*)*$')


def _project_packages() -> set[str]:
    return {p.name for p in REPO_ROOT.iterdir()
            if p.is_dir() and (p / '__init__.py').exists()
            and (p.name.startswith('risk_') or p.name == 'shared')}


def _module_name(py: Path) -> str:
    parts = py.relative_to(REPO_ROOT).with_suffix('').parts
    if parts[-1] == '__init__':
        parts = parts[:-1]
    return '.'.join(parts)


def _dependencies(source: str, package: str) -> set[str]:
    """返回源码引用的全部模块名：静态 import（相对 import 按 package 解析）+ 调用参数中的包名字符串。"""
    tree = ast.parse(source)
    deps: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            deps.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split('.')
                base = base[:len(base) - (node.level - 1)]
                target = '.'.join(base + ([node.module] if node.module else []))
            else:
                target = node.module or ''
            deps.add(target)
            # `from pkg import submodule` 也可能引用子模块
            deps.update(f'{target}.{a.name}' for a in node.names)
        elif isinstance(node, ast.Call):
            args = list(node.args) + [k.value for k in node.keywords]
            for a in args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str) \
                        and _PKG_STRING.match(a.value):
                    deps.add(a.value)
    return deps


def _project_deps(py: Path) -> set[str]:
    mod = _module_name(py)
    package = mod if py.name == '__init__.py' else mod.rpartition('.')[0]
    pkgs = _project_packages()
    return {d for d in _dependencies(py.read_text(encoding='utf-8'), package)
            if d.split('.')[0] in pkgs}


def test_string_import_detector_catches_load_module():
    """自检：检测器必须能抓到字符串式导入与相对导入（否则红线形同虚设）。"""
    deps = _dependencies(
        "import importlib\n"
        "from ..commands import cmd_run\n"
        "def f():\n"
        "    print('risk_iv_diagnosis 只是日志文字')\n"
        "    _load_module('risk_iv_diagnosis', 'iv_group_diagnosis')\n"
        "    importlib.import_module('risk_trigger_extraction.scripts.trigger_extraction')\n",
        package='risk_mining.analysis',
    )
    assert 'risk_mining.commands' in deps
    assert 'risk_iv_diagnosis' in deps
    assert 'risk_trigger_extraction.scripts.trigger_extraction' in deps


def test_kernel_depends_only_on_core_and_itself():
    offenders = []
    for rel in KERNEL_FILES:
        for dep in sorted(_project_deps(REPO_ROOT / rel)):
            top = dep.split('.')[0]
            if top == 'risk_core' or top in KERNEL_ALLOWED_SKILLS:
                continue
            if dep == 'risk_mining' or any(dep == k or dep.startswith(k + '.') for k in KERNEL_MODULES):
                continue
            offenders.append(f'{rel}: {dep}')
    assert not offenders, '挖掘内核引用了组合根 / 子 skill / shim：\n' + '\n'.join(offenders)


def test_risk_core_is_leaf():
    offenders = [
        f'{py.relative_to(REPO_ROOT)}: {dep}'
        for py in sorted((REPO_ROOT / 'risk_core').rglob('*.py'))
        for dep in sorted(_project_deps(py))
        if dep.split('.')[0] != 'risk_core'
    ]
    assert not offenders, 'risk_core 反向依赖了上层：\n' + '\n'.join(offenders)


def test_no_production_code_depends_on_shims():
    offenders = []
    for pkg in sorted(_project_packages() - {'risk_pipeline', 'shared'}):
        for py in sorted((REPO_ROOT / pkg).rglob('*.py')):
            for dep in sorted(_project_deps(py)):
                if dep.split('.')[0] in ('risk_pipeline', 'shared'):
                    offenders.append(f'{py.relative_to(REPO_ROOT)}: {dep}')
    assert not offenders, '生产代码仍依赖兼容 shim（shim 将无法删除）：\n' + '\n'.join(offenders)


def test_kernel_import_isolation():
    """子进程只 import 挖掘内核：不得连带加载子 skill / 组合根 / shim。"""
    code = (
        'import sys\n'
        + ''.join(f'import {m}\n' for m in sorted(KERNEL_MODULES))
        + "bad = sorted({m for m in sys.modules\n"
          "              if m.split('.')[0].startswith('risk_') or m.split('.')[0] == 'shared'}\n"
          "             - {m for m in sys.modules if m.split('.')[0] == 'risk_core'}\n"
          f"             - set({sorted(KERNEL_MODULES | {'risk_mining'})!r}))\n"
          "assert not bad, f'import 挖掘内核后被加载: {bad}'\n"
    )
    proc = subprocess.run([sys.executable, '-c', code], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr


def test_importing_shim_package_is_lazy():
    """``import risk_pipeline``（每次 ``python -m risk_pipeline`` 都会执行）不得连带加载 config / 分析内核。"""
    code = (
        'import sys, risk_pipeline\n'
        "loaded = sorted(m for m in sys.modules if m.startswith(('risk_core', 'risk_mining')))\n"
        "assert not loaded, loaded\n"
        'import risk_pipeline.paths, risk_core.paths\n'
        'assert risk_pipeline.paths is risk_core.paths\n'
        'import risk_pipeline.analysis.engine as a, risk_mining.analysis.engine as b\n'
        'assert a is b\n'
    )
    proc = subprocess.run([sys.executable, '-c', code], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
