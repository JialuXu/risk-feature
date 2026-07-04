# -*- coding: utf-8 -*-
"""解耦重构 Stage 5 不变量锁：risk_result_query 是只依赖 risk_core 的独立子 skill（首拆样板）。

锁四件事（DECOUPLING-DESIGN §9 阶段5 + §6「首拆样板」）：
  1. **AST 红线**：risk_result_query/ 全部 .py 的 import 不得出现 risk_pipeline /
     risk_mining / shared / 任何其它 risk_* 子 skill（只许 risk_core + 自身相对
     import）。AST 级比 grep 更严——函数体内的延迟 import 一并覆盖。
  2. **进程级 import 隔离**：全新子进程仅 import 本 skill 时，sys.modules 不得
     被 risk_pipeline / risk_mining / shared 污染——证明该 skill 可在不加载挖掘
     内核与组合根的前提下独立工作（「独立子 skill」的定义性质）。
  3. **薄独立入口**：`python -m risk_result_query <project> --kind iv` 在全新
     子进程里对真实导出结果出 top-N。该入口不进 agent 模板、不参与 argspec
     （§4.3）；agent 路径仍是 `python -m risk_pipeline query`（smoke 已锁）。
  4. **唯一读取器卸职**：load_results 的权威在 risk_core.results_loader；
     全仓除组合根 cmd_query（要 top_features 查询糖）外，任何非测试代码不得再
     import risk_result_query——防止它悄悄变回「事实公共读取器」（§3 耦合枢纽②）。
  5. **运行时隔离**（对抗审查确认的变异逃逸补锁）：锁1 的 AST 只见 import 语句，
     抓不住 `importlib.import_module('risk_pipeline')` / `__import__(...)` 字符串式
     动态 import；锁2 只 import 不执行函数体。补法：真实执行路径（四种 kind 的
     top_features 全分支）跑完后检查 sys.modules——动态 import 只要发生必然现形。
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / 'risk_result_query'


def _abs_imports(py_path: Path):
    """AST 提取一个 .py 的全部绝对 import 模块名（含函数体内延迟 import）。"""
    tree = ast.parse(py_path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:  # 相对 import（level>0）属自身，放行
                yield node.module


def _iter_py(root: Path):
    for py in root.rglob('*.py'):
        if '__pycache__' not in py.parts:
            yield py


# ---------------------------------------------------------------------------
# 锁1：AST 红线——本 skill 只依赖 risk_core
# ---------------------------------------------------------------------------

def test_skill_imports_only_risk_core():
    offenders = []
    for py in _iter_py(SKILL_DIR):
        for mod in _abs_imports(py):
            top = mod.split('.')[0]
            if top == 'shared' or (
                top.startswith('risk_') and top not in ('risk_core', 'risk_result_query')
            ):
                offenders.append(f'{py.relative_to(REPO_ROOT)}: import {mod}')
    assert not offenders, (
        'risk_result_query 出现 risk_core 之外的项目内 import（独立性破坏）：\n'
        + '\n'.join(offenders)
    )


# ---------------------------------------------------------------------------
# 锁4：全仓唯一合法 importer = 组合根 cmd_query（查询糖调用方）
# ---------------------------------------------------------------------------

_SCAN_DIRS = (
    'risk_core', 'risk_mining', 'risk_pipeline', 'shared',
    'risk_data_prep', 'risk_feature_engineering', 'risk_segment_univariate',
    'risk_iv_diagnosis', 'risk_logistic_regression', 'risk_rule_mining',
    'risk_export_report', 'risk_trigger_extraction', 'risk_docx_report',
    'risk_visualization', 'risk_threshold_explore',
)
_ALLOWED_IMPORTERS = {Path('risk_mining/commands/query.py')}


def test_only_cmd_query_imports_this_skill():
    importers = set()
    for d in _SCAN_DIRS:
        root = REPO_ROOT / d
        if not root.is_dir():
            continue
        for py in _iter_py(root):
            if any(m.split('.')[0] == 'risk_result_query' for m in _abs_imports(py)):
                importers.add(py.relative_to(REPO_ROOT))
    assert importers == _ALLOWED_IMPORTERS, (
        f'risk_result_query 的非测试 importer 应恰为 {_ALLOWED_IMPORTERS}'
        f'（查询糖唯一调用方），实际：{importers}——'
        f'load_results 消费方请改 import risk_core.results_loader'
    )


# ---------------------------------------------------------------------------
# 锁2：进程级 import 隔离（不拉起内核/组合根）
# ---------------------------------------------------------------------------

def test_import_isolation_no_kernel_pollution():
    code = (
        "import sys; "
        "from risk_result_query.scripts import load_results, top_features; "
        "bad = sorted({m.split('.')[0] for m in sys.modules "
        "              if m.split('.')[0] in ('risk_pipeline', 'risk_mining', 'shared')}); "
        "assert not bad, f'import 本 skill 竟拉起了 {bad}'; "
        "assert callable(load_results) and callable(top_features)"
    )
    proc = subprocess.run(
        [sys.executable, '-c', code],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f'进程级隔离验证失败：\n{proc.stderr}'


# ---------------------------------------------------------------------------
# 锁3：薄独立入口 python -m risk_result_query（真实导出结果上的端到端）
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def exported_root(tmp_path_factory, synthetic_dataframe):
    """跑一遍 generic 全链路，返回含已导出结果的项目根（模块内共享，只跑一次）。"""
    root = tmp_path_factory.mktemp('rq_standalone')
    raw = root / 'data' / 'raw'
    raw.mkdir(parents=True)
    wide = raw / 'wide.csv'
    bad = raw / 'bad_customers.csv'
    synthetic_dataframe.to_csv(wide, index=False, encoding='utf-8-sig')
    synthetic_dataframe.loc[
        synthetic_dataframe['is_bad'] == 1, ['客户编号']
    ].to_csv(bad, index=False, encoding='utf-8-sig')

    mp = pytest.MonkeyPatch()
    mp.setenv('RISK_PROJECT_ROOT', str(root))
    mp.delenv('RISK_OUTPUT_ROOT', raising=False)
    try:
        from risk_pipeline import cli
        rc = cli.main([
            'run', '--pipeline', 'generic',
            '--wide', str(wide), '--bad-customer', str(bad),
            '--id-col', '客户编号', '--target-col', 'is_bad',
            '--project', 'rq_standalone',
            '--quiet', '--confirmed-new-dataset',
        ])
        assert rc == 0
    finally:
        mp.undo()
    return root


def _standalone_env(root):
    env = dict(os.environ)
    env['RISK_PROJECT_ROOT'] = str(root)
    env.pop('RISK_OUTPUT_ROOT', None)
    return env


def test_python_m_standalone_entry(exported_root):
    proc = subprocess.run(
        [sys.executable, '-m', 'risk_result_query',
         'rq_standalone', '--kind', 'iv', '--top', '3'],
        cwd=REPO_ROOT, env=_standalone_env(exported_root),
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f'薄入口执行失败：\n{proc.stderr}'
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    assert len(lines) >= 4, f'top-3 输出应至少 表头+3 行，实际：\n{proc.stdout}'
    assert 'IV值' in proc.stdout


def test_runtime_import_isolation_after_real_query(exported_root):
    """锁5：真实执行 load_results + 四种 kind 的 top_features 后，sys.modules
    仍不得出现 risk_pipeline / risk_mining / shared（静态锁抓不到的
    importlib/__import__ 动态 import 在这里必然现形——变异实验验证过）。"""
    code = (
        "import sys\n"
        "from risk_result_query.__main__ import main\n"
        "for k in ('iv', 'iv_group', 'corr', 'lr'):\n"
        "    rc = main(['rq_standalone', '--kind', k, '--top', '3'])\n"
        "    assert rc == 0, (k, rc)\n"
        "bad = sorted({m.split('.')[0] for m in sys.modules\n"
        "              if m.split('.')[0] in ('risk_pipeline', 'risk_mining', 'shared')})\n"
        "assert not bad, f'真实执行后 sys.modules 被污染: {bad}'\n"
    )
    proc = subprocess.run(
        [sys.executable, '-c', code],
        cwd=REPO_ROOT, env=_standalone_env(exported_root),
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f'运行时隔离验证失败：\n{proc.stderr}'


def test_python_m_standalone_missing_project_exit_1(exported_root):
    proc = subprocess.run(
        [sys.executable, '-m', 'risk_result_query', '不存在的项目'],
        cwd=REPO_ROOT, env=_standalone_env(exported_root),
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 1
    assert '[risk_result_query]' in proc.stderr
