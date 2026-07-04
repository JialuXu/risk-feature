# -*- coding: utf-8 -*-
"""解耦重构 Stage 3 不变量锁：``assemble_exports`` 是导出装配的唯一实现。

背景：``build_corr_export`` / ``build_lr_export`` / ``build_comprehensive_table`` /
``build_llm_report_data`` 的调用序列曾在 4 处各抄一份（pipeline.py 的
credit/gsfc/generic + commands/export.py 的 cmd_export）。Stage 3 收敛为
``risk_mining.export.assemble_exports``。本测试用**真实中间产物**（跑一遍
generic 的 univariate/iv/lr 得到）直接驱动该函数，锁住三条不变量：

  1. credit 型（不传 raw/derived）与 generic 型（传 raw/derived）两种参数化
     产出的导出 schema **仅相差文档化的 `特征类型` 列**，其余逐字一致
     （§5.4「三链路一致」；证明 raw/derived 只影响 `特征类型`、不泄漏别的差异）。
  2. df 缺失（cmd_export 下 prepared.csv 不存在）→ 跳过 LLM 报告数据构建，
     其余三张表照常产出（对齐 cmd_export 历史行为）。
  3. target_col 显式传 COL_TARGET 与走默认值**产物逐字相同**——这正是 credit
     「补 target_col 是一致性对齐、非行为修复」的证明。

另附 call-site #3 覆盖：直接跑 run_generic_pipeline Python API 到 export，
确保 pipeline.py 的 generic 导出段真的经过 assemble_exports 落盘（CLI 的
`run --pipeline generic` 走 cmd_export，不覆盖这条 Python API 路径）。
"""
from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd
import pytest

from risk_pipeline.config import COL_TARGET
from risk_pipeline.pipeline import run_generic_pipeline
from risk_mining.export import assemble_exports


FEATURES = [f'feat_{i}' for i in range(1, 9)]
RAW = FEATURES[:4]
DERIVED = FEATURES[4:]


def _build_df(n=1500, seed=42):
    """1500 行 / 4 分群 / 8 特征 / 20% 坏客户——足以让每个分群越过 IV/LR 门槛。"""
    rng = np.random.RandomState(seed)
    df = pd.DataFrame({
        '客户编号': [f'C{i:05d}' for i in range(n)],
        '企业规模': rng.choice(
            ['小型企业', '中型企业', '大型企业', '微型企业'],
            size=n, p=[0.4, 0.3, 0.1, 0.2],
        ),
    })
    for i in range(1, 9):
        df[f'feat_{i}'] = rng.normal(loc=10 + i, scale=2, size=n)
    score = (0.5 * df['feat_1'] - 0.3 * df['feat_3'] + 0.4 * df['feat_5']
             + rng.normal(scale=2, size=n))
    df['is_bad'] = (score > np.percentile(score, 80)).astype(int)
    return df


@pytest.fixture(scope='module')
def analysis_results():
    """跑 univariate/iv/lr（不 export、不落盘）得到真实中间产物 dict。"""
    df = _build_df()
    res = run_generic_pipeline(
        df=df, feature_cols=FEATURES, target_col='is_bad',
        raw_features=RAW, derived_features=DERIVED,
        steps=['univariate', 'iv', 'lr'], verbose=False,
    )
    assert res.get('iv_full') is not None and not res['iv_full'].empty, (
        '合成数据未产出非空 iv_full，后续 schema 断言无从谈起'
    )
    return {'results': res, 'df': df}


def _assemble(base, *, df, raw=None, derived=None, target_col=COL_TARGET):
    """在 base results 的深拷贝上跑 assemble_exports，返回被就地写回的 results。"""
    results = copy.deepcopy(base)
    assemble_exports(
        results, df=df,
        feature_cols=FEATURES, category_dims=['企业规模'], qual_dims=[],
        raw_features=raw, derived_features=derived, target_col=target_col,
    )
    return results


def test_credit_and_generic_style_schema_consistent(analysis_results):
    """不变量1：credit 型 vs generic 型导出 schema 仅相差文档化的 `特征类型` 列。"""
    base, df = analysis_results['results'], analysis_results['df']

    r_credit = _assemble(base, df=df)                       # credit/gsfc：不传 raw/derived
    r_generic = _assemble(base, df=df, raw=RAW, derived=DERIVED)  # generic/cmd_export

    # 四张导出表都应产出
    for key in ('corr_exports', 'lr_exports', 'comprehensive', 'llm_report_data'):
        assert key in r_credit, f'credit 型缺 {key}'
        assert key in r_generic, f'generic 型缺 {key}'

    # corr/lr 导出（单张 DataFrame）不吃 raw/derived → 列名必须逐字一致
    for key in ('corr_exports', 'lr_exports'):
        assert list(r_credit[key].columns) == list(r_generic[key].columns), (
            f'{key} 列名在两种参数化下应逐字一致'
        )

    # comprehensive：两种参数化的差异必须**仅限** `特征类型` 列
    cols_credit = set(r_credit['comprehensive'].columns)
    cols_generic = set(r_generic['comprehensive'].columns)
    assert cols_credit - cols_generic == set(), (
        f'credit 型不应多出 generic 型没有的列：{cols_credit - cols_generic}'
    )
    assert cols_generic - cols_credit <= {'特征类型'}, (
        f'generic 型相对 credit 型只应因 raw/derived 多出 `特征类型`，'
        f'实际多出：{cols_generic - cols_credit}'
    )
    # 核心列在两侧都必须在（下游 query/visualize 依赖）
    for col in ('特征名称', 'IV可信度'):
        assert col in cols_credit and col in cols_generic, f'comprehensive 缺核心列 {col}'


def test_df_none_skips_llm_but_keeps_rest(analysis_results):
    """不变量2：df=None（cmd_export 下 prepared.csv 缺失）→ 不建 LLM 数据，其余照常。"""
    base = analysis_results['results']
    r = _assemble(base, df=None, raw=RAW, derived=DERIVED)
    assert 'llm_report_data' not in r, 'df=None 时不应构建 llm_report_data'
    for key in ('corr_exports', 'lr_exports', 'comprehensive'):
        assert key in r, f'df=None 时 {key} 仍应产出'


def test_target_col_explicit_equals_default(analysis_results):
    """不变量3：显式传 target_col=COL_TARGET 与走默认值产物逐字相同（credit 一致性对齐证明）。"""
    base, df = analysis_results['results'], analysis_results['df']
    assert COL_TARGET == 'is_bad'

    r_explicit = _assemble(base, df=df, target_col=COL_TARGET)
    # 走 assemble_exports 默认（不传 target_col）
    r_default = copy.deepcopy(base)
    assemble_exports(
        r_default, df=df,
        feature_cols=FEATURES, category_dims=['企业规模'], qual_dims=[],
    )

    # LLM overview 里的坏客户计数等对 target_col 敏感 → 用它做逐字比对锚点
    ov_explicit = r_explicit['llm_report_data'].get('overview')
    ov_default = r_default['llm_report_data'].get('overview')
    assert json.dumps(ov_explicit, ensure_ascii=False, sort_keys=True) == \
        json.dumps(ov_default, ensure_ascii=False, sort_keys=True), (
        'target_col 显式 vs 默认应逐字一致（credit 目标列本就是 is_bad）'
    )


def test_run_generic_pipeline_api_reaches_export(tmp_path, monkeypatch):
    """call-site #3 覆盖：run_generic_pipeline Python API 经 assemble_exports 落盘到 Level 1 产物。

    CLI 的 `run --pipeline generic` 走 cmd_export（call-site #4），不经过
    pipeline.py 的 generic 导出段；此处直调 Python API 补上这条路径的端到端覆盖。
    """
    (tmp_path / 'data' / 'raw').mkdir(parents=True)
    monkeypatch.setenv('RISK_PROJECT_ROOT', str(tmp_path))
    monkeypatch.delenv('RISK_OUTPUT_ROOT', raising=False)  # 见 §7：output root 须在 import config 前定，测试里不设
    monkeypatch.chdir(tmp_path)

    df = _build_df()
    pname = 'stage3_generic_api'
    res = run_generic_pipeline(
        df=df, feature_cols=FEATURES, target_col='is_bad',
        project_name=pname, raw_features=RAW, derived_features=DERIVED,
        steps=['univariate', 'iv', 'lr', 'export'], verbose=False,
    )

    exported = res.get('exported_files') or []
    assert exported, 'generic Python API export 未落任何文件（call-site #3 回归？）'
    assert res.get('comprehensive') is not None and not res['comprehensive'].empty
    assert isinstance(res.get('llm_report_data'), dict)

    res_dir = tmp_path / 'data' / 'results' / pname
    assert (res_dir / f'{pname}_综合特征分析结果.csv').exists()
    assert (res_dir / f'{pname}_IV分析结果_全量.csv').exists()
