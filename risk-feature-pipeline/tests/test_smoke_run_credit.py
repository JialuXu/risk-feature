# -*- coding: utf-8 -*-
"""端到端 smoke：run_credit_pipeline 抵达 export 段（解耦重构 Stage 3 call-site #1 覆盖）。

Stage 3 把导出装配收敛到 ``risk_mining.export.assemble_exports``，credit 链路的导出段
（pipeline.py 内 credit 分支）是四个调用点之一。gsfc/generic 已有 smoke，credit 却
**零覆盖**——一旦 credit 导出段的 assemble_exports 传参写错（变量名/关键字/缩进），
现有测试全绿也发现不了。本测试用**合成征信多表**（客户信息 + 征信数据 + 坏客户标记）
真跑 credit 链路到 export，锁住该调用点。

设计（对齐 test_smoke_run_gsfc 的隔离约定）：
  - credit 链路只按 config 相对路径读磁盘 CSV，不接收内存 df；故把合成表写到临时
    项目根的 data/raw 下，**只设 RISK_PROJECT_ROOT**（不设 RISK_OUTPUT_ROOT——它在
    import 期冻结输出路径，运行中改无效），输入读取与产物写入都落到该临时根。
  - 跳过 feature_engineering 步（steps 不含），feature_cols 直接取征信数据里的原始特征列，
    绕开 create_credit_features 的 25 个衍生特征公式，聚焦护住导出段本身。
  - 产业数据文件不提供（可选表，load_credit_data 仅打印警告不报错）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from risk_pipeline.config import COL_CUSTOMER_ID, COL_REPORT_DATE
from risk_pipeline.pipeline import run_credit_pipeline
from risk_data_prep.scripts.config import CREDIT_CONFIG


# credit raw_features（征信数据侧）——只需这些列存在，feature_cols 即取它们
_RAW_FEATURES = CREDIT_CONFIG['raw_features']


def _build_credit_dataset(root):
    """在 root 下写出 credit 链路所需的合成 CSV（客户信息 / 征信数据 / 坏客户标记）。

    600 户、企业规模 2 值（各 300）、坏客户率 ~20% → 每分群坏客户 ~60，
    越过 MIN_BAD_SAMPLES(10)/MIN_BAD_CORR(15)/MIN_BAD_LR(20)/MIN_GOOD_LR(50)，
    使 iv/lr 产出非空、导出段真正构建 comprehensive + LLM 数据。
    """
    raw = root / 'data' / 'raw'
    raw.mkdir(parents=True)

    rng = np.random.RandomState(20240701)
    n = 600
    ids = [f'K{i:05d}' for i in range(n)]

    # 客户信息：主键 + 企业规模（唯一分群维度，取 credit_category_dims 中的一个）
    cust = pd.DataFrame({
        COL_CUSTOMER_ID: ids,
        '企业规模': ['小型企业' if i % 2 == 0 else '中型企业' for i in range(n)],
    })
    cust.to_csv(raw / '客户信息.csv', index=False, encoding='utf-8-sig')

    # 征信数据：主键 + 报告日期 + 9 个原始特征（非零方差，部分与坏客户弱相关）
    credit = pd.DataFrame({COL_CUSTOMER_ID: ids})
    credit[COL_REPORT_DATE] = '2024-01-15'
    latent = rng.normal(size=n)
    for j, feat in enumerate(_RAW_FEATURES):
        credit[feat] = (rng.poisson(lam=3 + j, size=n)
                        + (latent * (1 if j % 2 == 0 else 0)).round().astype(int).clip(min=0))
    credit.to_csv(raw / '征信数据.csv', index=False, encoding='utf-8-sig')

    # 坏客户标记：坏客户率与 latent 挂钩，保证特征有区分度
    bad_score = latent + rng.normal(scale=0.5, size=n)
    bad_mask = bad_score > np.percentile(bad_score, 80)
    bad_ids = [ids[i] for i in range(n) if bad_mask[i]]
    pd.DataFrame({COL_CUSTOMER_ID: bad_ids}).to_csv(
        raw / '坏客户标记.csv', index=False, encoding='utf-8-sig',
    )
    return len(bad_ids)


@pytest.fixture
def credit_workdir(tmp_path, monkeypatch):
    n_bad = _build_credit_dataset(tmp_path)
    monkeypatch.setenv('RISK_PROJECT_ROOT', str(tmp_path))
    monkeypatch.delenv('RISK_OUTPUT_ROOT', raising=False)
    monkeypatch.chdir(tmp_path)
    return {'root': tmp_path, 'n_bad': n_bad}


def test_run_credit_reaches_export(credit_workdir):
    """credit 全链路（跳过 feature_engineering）应跑到 export 段并产出标准导出。

    直接护住 pipeline.py credit 分支的 assemble_exports 调用点（Stage 3 call-site #1）。
    """
    results = run_credit_pipeline(
        steps=['data_prep', 'univariate', 'iv', 'lr', 'export'],
        verbose=False,
    )

    # 数据准备正确：企业规模被识别为分群维度、特征列取自征信数据原始特征
    assert results.get('category_dims') == ['企业规模'], (
        f"未识别到唯一分群维度 企业规模：{results.get('category_dims')}"
    )
    assert set(results.get('feature_cols', [])) <= set(_RAW_FEATURES)
    assert len(results.get('feature_cols', [])) >= 5, 'credit 特征列过少，导出无从谈起'

    # IV/导出段真跑：iv_full 非空 → assemble_exports 应构建 comprehensive + LLM 数据
    iv_full = results.get('iv_full')
    assert iv_full is not None and not iv_full.empty, 'credit iv_full 为空，导出段未被有效驱动'

    comp = results.get('comprehensive')
    assert comp is not None and not comp.empty, 'credit 导出段未构建 comprehensive（call-site #1 回归？）'
    assert '特征名称' in comp.columns and 'IV可信度' in comp.columns
    # credit 不传 raw/derived → comprehensive 不应出现 generic 专属的 特征类型 列
    assert '特征类型' not in comp.columns, 'credit 导出不应含 特征类型（未传 raw/derived）'

    assert isinstance(results.get('llm_report_data'), dict), 'credit 未构建 LLM 报告数据'

    # 标准导出文件落盘（返回的路径列表，不依赖 timestamp 子目录名）
    exported = [str(p) for p in (results.get('exported_files') or [])]
    assert exported, 'credit 导出段未落任何文件'
    assert any('综合特征分析结果' in p for p in exported), '缺 综合特征分析结果 导出'
    assert any('IV分析结果' in p for p in exported), '缺 IV分析结果 导出'


def test_run_credit_state_unified_and_visible_downstream(credit_workdir):
    """解耦阶段9 锁：run credit 的 state 落 data/results/credit/（无「征信」前缀），
    且下游 require_level（trigger/report/explore 的默认解析路径）能看见 Level 1。

    修复前 cmd_run credit 把 state 特判到 data/results/征信/credit/，而下游命令
    默认从 data/results/credit/ 读 → run credit 推进的 Level 1 对下游不可见，
    trigger/report 会被 require_level 误拦。
    """
    import json as _json

    from risk_pipeline import cli
    from risk_pipeline.pipeline_state import load_state

    rc = cli.main([
        'run', '--pipeline', 'credit', '--quiet',
        '--steps', 'data_prep,univariate,iv,lr,export',  # 跳过 FE（合成数据无衍生公式列）
    ])
    assert rc == 0

    root = credit_workdir['root']
    unified = root / 'data' / 'results' / 'credit' / '.pipeline_state.json'
    legacy = root / 'data' / 'results' / '征信' / 'credit' / '.pipeline_state.json'
    assert unified.exists(), f'state 未落统一目录: {unified}'
    assert not legacy.exists(), '不应再写带「征信」前缀的旧 state 目录（阶段9 已统一）'

    with open(unified, 'r', encoding='utf-8') as f:
        raw = _json.load(f)
    assert raw['current_level'] == 'Level 1'

    # 下游可见性：与 trigger/report/explore 相同的默认解析路径必须直接看到 Level 1
    st = load_state('credit', project_root=str(root))
    st.require_level('Level 1')  # 不抛 = 下游命令不再被误拦
