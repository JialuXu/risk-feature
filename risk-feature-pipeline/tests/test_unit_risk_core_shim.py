# -*- coding: utf-8 -*-
"""解耦重构 Stage 1 不变量锁：risk_pipeline→risk_core 模块别名 + contracts 契约。

这些用例把「shim 是同一对象」「§5.4 读端白名单 ⊇ 写端元信息列」「§5.1 主键 str 往返」
等 pytest 之前覆盖不到的约束固化下来，防止后续阶段（2–10）无声破坏。
"""
import importlib

import pandas as pd

# risk_pipeline/__init__.py 用模块别名转发到 risk_core 的 7 个子模块
_ALIASED = [
    'paths', 'config', 'config_loader', 'column_mapper',
    'io_utils', 'font_utils', 'results_loader',
]


def test_shim_module_identity_is_same_object():
    """import risk_pipeline.X 与 risk_core.X 必须是同一模块对象（非 import * 拷贝）。"""
    for name in _ALIASED:
        rp = importlib.import_module(f'risk_pipeline.{name}')
        rc = importlib.import_module(f'risk_core.{name}')
        assert rp is rc, f'risk_pipeline.{name} is not risk_core.{name}'


def test_shim_private_name_reachable_and_shared():
    """私有名（如 test_unit_cli_roots_stamp 依赖的 _warned_no_data_dir）经别名可达且共享。"""
    import risk_core.paths as rcp
    import risk_pipeline.paths as rpp
    assert rpp._warned_no_data_dir is rcp._warned_no_data_dir


def test_contracts_schema_constants_faithful():
    """contracts.py §5 常量数量/取值对齐权威来源（未消费也不许 drift）。"""
    from risk_core import contracts
    assert len(contracts.FEATURES_JSON_KEYS) == 15
    assert set(contracts.FEATURES_AUDIT_GROUPS) == {
        'segment_dims', 'credit_category_dims', 'amount_cols',
    }
    assert set(contracts.FEATURES_AUDIT_GROUP_KEYS) == {
        'expected', 'actual', 'missing', 'hit_rate',
    }
    assert len(contracts.INTERMEDIATE_SIMPLE_KEYS) == 8
    assert len(contracts.INTERMEDIATE_WIDE_DICT_KEYS) == 4
    assert contracts.QUAL_WIDE_DIM_KEY == '资质标签'
    assert contracts.MANIFEST_SCHEMA_VERSION == 1
    assert contracts.FINGERPRINT_SCHEMA_VERSION == 2
    assert contracts.FINGERPRINT_HEAD_BYTES == contracts.FINGERPRINT_TAIL_BYTES == 256 * 1024
    assert contracts.LEVEL_ORDER == ['前置', '过渡态', 'Level 1', 'Level 2', 'Level 3']


def test_contracts_reader_whitelist_superset_of_writer_meta_cols():
    """§5.4 关键不变量：读端 KNOWN_META_COLS 必须 ⊇ 写端 corr/lr 元信息列，否则伪特征混入 top-N。"""
    from risk_core import contracts
    assert set(contracts.CORR_EXPORT_META_COLS) <= contracts.KNOWN_META_COLS
    assert set(contracts.LR_EXPORT_META_COLS) <= contracts.KNOWN_META_COLS


def test_read_prepared_preserves_leading_zero_id(tmp_path):
    """§5.1 契约：write→read_prepared 往返，带前导零的主键必须保持字符串不丢零。"""
    from risk_core import contracts
    df = pd.DataFrame({'客户编号': ['000123', '004560', '010'], 'is_bad': [0, 1, 0]})
    p = tmp_path / 'prepared.csv'
    contracts.write_prepared(df, p)
    back = contracts.read_prepared(p, '客户编号')
    assert list(back['客户编号']) == ['000123', '004560', '010']
