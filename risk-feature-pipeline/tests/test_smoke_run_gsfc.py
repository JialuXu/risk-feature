# -*- coding: utf-8 -*-
"""端到端 smoke：run --pipeline gsfc 全流程能抵达 Level 1。

用**纯合成数据**重建用户实际场景（客户信息 + 工商变更 + 坏客户标记，无财务侧表），
并故意把授信金额列写成带千分位逗号与 '-' 占位符的字符串，以同时覆盖两类历史回归：

  P1-1  金额列为字符串时，build_wide_table 只清洗了第一个金额列，导致特征工程
        `本行授信使用率 = 表内授信余额 / 授信总金额` 抛
        `TypeError: unsupported operand type(s) for /: 'str' and 'float'`。
  P0-1  gsfc 旧导出 `df_iv.pivot_table(index='特征', columns='分群', ...)` 按旧 schema
        取 '分群' 列，而分群内核已产出 '分群名称' 新 schema，抛 `KeyError: '分群'`，
        使 gsfc 无法抵达 Level 1。

两个 bug 任一存在，本测试都会失败（链路报错 / 不落标准产物 / 未到 Level 1）。

实现要点（见 P0-1/P1-1 调查）：
  - run_gsfc_pipeline 不接收内存 df，只按 config 相对路径读磁盘 CSV；因此把合成表
    写到临时项目根的 data/raw 下，并**只设 RISK_PROJECT_ROOT**（不要设
    RISK_OUTPUT_ROOT——它在 import 期解析输出路径，运行中改无效）。仅设 PROJECT_ROOT
    时输入读取与产物写入都会落到该临时根。
  - gsfc 修复后导出统一走 report_analysis，产物为非时间戳的标准命名，落在
    data/results/工商财务/<项目名>/ 与 output/工商财务/<项目名>/。
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from risk_pipeline import cli
from risk_pipeline.pipeline import run_gsfc_pipeline
# gsfc 导出对外项目名（report_analysis 产物前缀 / 子目录名）
from risk_export_report.scripts.config import GSFC_LLM_PROJECT_NAME


def _money_strings(values):
    """把整型金额转成带千分位逗号的字符串，并周期性插入 '-' 占位符。

    这正是历史真实数据里触发 P1-1 的形态：金额列整列是 object/str。
    """
    return ['-' if i % 29 == 0 else f'{int(v):,}' for i, v in enumerate(values)]


def _build_gsfc_dataset(root):
    """在 root 下写出 gsfc 链路所需的合成 CSV（客户信息 / 工商变更 / 坏客户标记）。

    设计：客户性质取 2 值（各 ~200 行）、总坏客户率 ~16% → 每个分群都越过
    MIN_SAMPLES(50)/MIN_BAD_SAMPLES(10)/MIN_BAD_LR(20) 门槛，使 iv_by_group 产出
    非空 iv_group_all，确实走到 P0-1 的透视表分支；金额列写成字符串（含 ',' 与 '-'）
    → 走到 P1-1 的授信使用率相除分支。
    """
    raw = root / 'data' / 'raw'
    raw.mkdir(parents=True)

    rng = np.random.RandomState(20240601)
    n = 400
    ids = [f'G{i:05d}' for i in range(n)]

    cust = pd.DataFrame({
        '客户编号': ids,
        '所属行业': ['制造业', '批发零售', '建筑业', '服务业'] * (n // 4),
        '客户性质': ['民营' if i % 2 == 0 else '国有' for i in range(n)],
        '内部评级': rng.choice(['A', 'BBB', 'BB', 'A+'], size=n),
        # 授信金额列：字符串、含千分位逗号与 '-' 占位符 → 触发 P1-1
        '授信总金额': _money_strings(rng.randint(5, 500, n) * 100000),
        '表内授信余额': _money_strings(rng.randint(1, 300, n) * 100000),
    })
    cust.to_csv(raw / '客户信息.csv', index=False, encoding='utf-8-sig')

    chg = pd.DataFrame({
        '客户编号': ids,
        '变更总次数': rng.randint(0, 20, n),
        '变更类型数': rng.randint(0, 6, n),
        '最近30天_变更次数': rng.randint(0, 4, n),
        '最近90天_变更次数': rng.randint(0, 6, n),
        '新增标记总数': rng.randint(0, 5, n),
        '退出标记总数': rng.randint(0, 5, n),
    })
    chg.to_csv(raw / '工商变更_特征.csv', index=False, encoding='utf-8-sig')

    bad_ids = [ids[i] for i in range(n) if rng.rand() < 0.16]
    pd.DataFrame({'客户编号': bad_ids}).to_csv(
        raw / '坏客户标记.csv', index=False, encoding='utf-8-sig',
    )
    return len(bad_ids)


@pytest.fixture
def gsfc_workdir(tmp_path, monkeypatch):
    """独立临时项目根：合成多表 CSV + 仅设 RISK_PROJECT_ROOT。"""
    n_bad = _build_gsfc_dataset(tmp_path)
    monkeypatch.setenv('RISK_PROJECT_ROOT', str(tmp_path))
    # 关键：清掉 RISK_OUTPUT_ROOT，避免 config import 期把输出锁成别处绝对路径。
    monkeypatch.delenv('RISK_OUTPUT_ROOT', raising=False)
    monkeypatch.chdir(tmp_path)
    return {'root': tmp_path, 'n_bad': n_bad}


def test_run_gsfc_reaches_level_1(gsfc_workdir):
    """gsfc 全链路（含字符串金额）应抵达 Level 1 并落盘标准导出产物。

    覆盖 P1-1（字符串金额相除 TypeError）+ P0-1（导出 分群 列名错配 KeyError）。
    """
    root = gsfc_workdir['root']

    rc = cli.main(['run', '--pipeline', 'gsfc', '--quiet'])
    assert rc == 0

    pname = GSFC_LLM_PROJECT_NAME
    res_dir = root / 'data' / 'results' / '工商财务' / pname
    out_dir = root / 'output' / '工商财务' / pname

    # --- P0-1 守门：IV 值透视表必须落盘（pivot(columns=...) 不再 KeyError）---
    iv_pivot = res_dir / f'{pname}_IV值透视表.csv'
    assert iv_pivot.exists(), f'缺失 gsfc IV值透视表（P0-1 回归？）: {iv_pivot}'

    # 其余标准 Level 1 产物
    assert (res_dir / f'{pname}_IV分析结果_全量.csv').exists()
    assert (res_dir / f'{pname}_综合特征分析结果.csv').exists()
    assert (res_dir / f'{pname}_逻辑回归系数.csv').exists()
    assert (out_dir / f'{pname}_LLM报告数据.json').exists()

    # --- 透视表 schema 钉死：report_analysis 以 分群名称 为行、特征为列（对外新 schema）---
    df_pivot = pd.read_csv(iv_pivot, encoding='utf-8-sig')
    assert df_pivot.columns[0] == '分群名称', (
        f'IV透视表首列应为 分群名称，实际为 {df_pivot.columns[0]!r}'
    )
    assert len(df_pivot.columns) >= 2, 'IV透视表至少应有一个特征列'

    # --- state 推进到 Level 1（解耦阶段9：与 analyze/export/trigger 统一目录，无前缀）---
    state_path = root / 'data' / 'results' / 'gsfc' / '.pipeline_state.json'
    assert state_path.exists(), f'缺失 gsfc state: {state_path}'
    legacy_state = root / 'data' / 'results' / '工商财务' / 'gsfc' / '.pipeline_state.json'
    assert not legacy_state.exists(), '不应再写带「工商财务」前缀的旧 state 目录（阶段9 已统一）'
    with open(state_path, 'r', encoding='utf-8') as f:
        state = json.load(f)
    assert state['current_level'] == 'Level 1'
    assert state['history'][-1]['pipeline'] == 'gsfc'


def test_run_gsfc_feature_engineering_handles_string_amounts(gsfc_workdir):
    """定向守门 P1-1：字符串金额（含 ',' 与 '-'）不得让特征工程抛 TypeError。

    直接调 run_gsfc_pipeline（而非 CLI），让回归在『金额未清洗导致相除报错』这步
    就能被定位，而不是只表现为 CLI 整体失败。
    """
    results = run_gsfc_pipeline(steps=['data_prep', 'feature_eng'], verbose=False)

    df = results['wide_table']
    # 原始金额列已被清洗为数值（'-' 占位符按缺失计 0）。
    assert pd.api.types.is_numeric_dtype(df['授信总金额'])
    assert pd.api.types.is_numeric_dtype(df['表内授信余额'])
    # 授信使用率衍生特征证明字符串金额已正确转数值并完成相除。
    assert '本行授信使用率' in df.columns, '本行授信使用率 缺失（P1-1：金额未清洗？）'
    assert pd.api.types.is_numeric_dtype(df['本行授信使用率'])
    assert len(results.get('feature_cols', [])) > 0, '特征工程未产出任何特征列'
