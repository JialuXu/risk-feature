# -*- coding: utf-8 -*-
"""解耦重构 Stage 6 契约锁：prepared.csv（§5.1）+ features.json（§5.2）。

§5.1 是设计文档点名「本重构应顺手修掉」的**真 bug**：prepare_df 内部把主键
astype(str) 规避前导零，但落盘 CSV 后字符串性丢失，读回被推断成 int →
trigger 输出的客户编号变 '123'，业务侧拿它与客户宽表（'00123'）merge 0 命中
→ 全 0 预警名单。修法 = 全部读写点收敛到 contracts.read/write_prepared，
读时强制 dtype={id_col: str}。

锁三件事：
  1. 往返锁：write_prepared → read_prepared 前导零无损；同时**演示**裸
     pd.read_csv 确实丢前导零（证明契约是承重墙，不是装饰）。
  2. features.json schema 锁：prepare 落盘的键集合 == FEATURES_JSON_KEYS
     （15 键），confirmation / column_mapping_audit 子 schema 齐全——写点
     （cmd_prepare）与读点（analyze/trigger 的 .get 链）分属不同模块后，
     键名漂移只能靠这里抓。
  3. 端到端回归锁：纯数字带前导零的客户编号跑 prepare→analyze→export→
     trigger 全链路，trigger 落盘宽表的客户编号必须原样保留前导零。
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from risk_core.contracts import (
    FEATURES_AUDIT_GROUP_KEYS,
    FEATURES_AUDIT_GROUPS,
    FEATURES_CONFIRMATION_KEYS,
    FEATURES_JSON_KEYS,
    PREPARED_CSV_ENCODING,
    read_prepared,
    write_prepared,
)


# ---------------------------------------------------------------------------
# 锁1：前导零往返
# ---------------------------------------------------------------------------

def test_roundtrip_preserves_leading_zeros(tmp_path):
    df = pd.DataFrame({
        '客户编号': ['00123', '00456', '7'],
        'feat_1': [1.0, 2.0, 3.0],
        'is_bad': [0, 1, 0],
    })
    path = tmp_path / 'prepared.csv'
    write_prepared(df, path)

    back = read_prepared(path, id_col='客户编号')
    assert back['客户编号'].tolist() == ['00123', '00456', '7'], '契约读回丢前导零'
    assert pd.api.types.is_string_dtype(back['客户编号']), (
        f"主键读回应为字符串型 dtype，实际 {back['客户编号'].dtype}"
    )

    # 演示被修掉的 bug：裸 read_csv 把带前导零的纯数字主键推断成 int
    naked = pd.read_csv(path, encoding=PREPARED_CSV_ENCODING)
    assert naked['客户编号'].tolist() == [123, 456, 7], (
        '裸读竟保住了前导零？pandas 推断行为变了，请重新评估 §5.1 契约的必要性'
    )


def test_read_prepared_tolerates_none_and_missing_id_col(tmp_path):
    df = pd.DataFrame({'a': [1], 'b': [2]})
    path = tmp_path / 'prepared.csv'
    write_prepared(df, path)
    # id_col=None（features.json 缺失）→ 普通读不炸
    assert read_prepared(path, id_col=None).shape == (1, 2)
    # id_col 不在 CSV 中（pandas 静默忽略 dtype 未知键）→ 不炸
    assert read_prepared(path, id_col='不存在的列').shape == (1, 2)


# ---------------------------------------------------------------------------
# 锁2：features.json schema（15 键 + 两个子 schema）
# ---------------------------------------------------------------------------

def test_features_json_schema_contract(project_workdir):
    from risk_mining import cli
    rc = cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号', '--target-col', 'is_bad',
        '--project', 'fx_schema', '--quiet', '--confirmed-new-dataset',
    ])
    assert rc == 0

    fpath = (project_workdir['root'] / 'data' / 'processed' / 'fx_schema'
             / 'features.json')
    with open(fpath, 'r', encoding='utf-8') as f:
        info = json.load(f)

    assert set(info.keys()) == set(FEATURES_JSON_KEYS), (
        f'features.json 键集合漂移：多 {set(info) - set(FEATURES_JSON_KEYS)}，'
        f'少 {set(FEATURES_JSON_KEYS) - set(info)}——写点/读点分属不同 skill，'
        f'改键必须先改 contracts.FEATURES_JSON_KEYS'
    )
    assert set(info['confirmation'].keys()) == set(FEATURES_CONFIRMATION_KEYS)
    audit = info['column_mapping_audit']
    for grp in FEATURES_AUDIT_GROUPS:
        assert grp in audit, f'column_mapping_audit 缺 {grp} 组'
        assert set(FEATURES_AUDIT_GROUP_KEYS) <= set(audit[grp].keys()), (
            f'{grp} 组缺键：{set(FEATURES_AUDIT_GROUP_KEYS) - set(audit[grp])}'
        )
    # trigger/analyze 硬读的两键必须真有值
    assert info['id_col'] == '客户编号' and info['target_col'] == 'is_bad'


# ---------------------------------------------------------------------------
# 锁3：前导零端到端（prepare→analyze→export→trigger）
# ---------------------------------------------------------------------------

@pytest.fixture
def leading_zero_workdir(tmp_path, monkeypatch):
    """构造纯数字带前导零主键的项目根（'00001' 这种最易被推断成 int 的形态）。"""
    np.random.seed(7)
    n = 200
    df = pd.DataFrame({
        '客户编号': [f'{i:05d}' for i in range(n)],  # 00000..00199
        '企业规模': np.random.choice(
            ['小型企业', '中型企业', '大型企业', '微型企业'],
            size=n, p=[0.4, 0.3, 0.1, 0.2],
        ),
    })
    for i in range(1, 9):
        df[f'feat_{i}'] = np.random.normal(loc=10 + i, scale=2, size=n)
    score = 0.5 * df['feat_1'] - 0.3 * df['feat_3'] + np.random.normal(scale=2, size=n)
    df['is_bad'] = (score > np.percentile(score, 85)).astype(int)

    raw = tmp_path / 'data' / 'raw'
    raw.mkdir(parents=True)
    df.to_csv(raw / 'wide.csv', index=False, encoding='utf-8-sig')
    df.loc[df['is_bad'] == 1, ['客户编号']].to_csv(
        raw / 'bad.csv', index=False, encoding='utf-8-sig')
    monkeypatch.chdir(tmp_path)
    return {'root': tmp_path, 'ids': set(df['客户编号'])}


def test_trigger_e2e_preserves_leading_zero_ids(leading_zero_workdir, tmp_path):
    from risk_mining import cli
    rc = cli.main([
        'run', '--pipeline', 'generic',
        '--wide', 'data/raw/wide.csv', '--bad-customer', 'data/raw/bad.csv',
        '--id-col', '客户编号', '--target-col', 'is_bad',
        '--project', 'lz', '--quiet', '--confirmed-new-dataset',
    ])
    assert rc == 0

    features = [
        {'report_name': 'feat_1', 'source_col': 'feat_1',
         'risk_direction': 'positive', 'iv': 0.8, 'category': '测试', 'scope': 'full'},
        {'report_name': 'feat_3', 'source_col': 'feat_3',
         'risk_direction': 'negative', 'iv': 0.6, 'category': '测试', 'scope': 'full'},
    ]
    feat_file = tmp_path / 'features_lz.json'
    with open(feat_file, 'w', encoding='utf-8') as f:
        json.dump(features, f, ensure_ascii=False)

    rc = cli.main([
        'trigger', '--project', 'lz',
        '--features-file', str(feat_file), '--quiet', '--confirmed',
    ])
    assert rc == 0

    out = (leading_zero_workdir['root'] / 'output' / 'lz'
           / 'lz_风险触碰明细_宽表.csv')
    assert out.exists()
    # 以文本读客户编号列：修复前盘上是 '0'/'1'/...（int 序列化），修复后是 '00000'/...
    got = set(pd.read_csv(out, encoding='utf-8-sig', dtype={'客户编号': str})['客户编号'])
    assert got == leading_zero_workdir['ids'], (
        f'trigger 宽表客户编号未保住前导零（§5.1 回归）：'
        f'样例 {sorted(got)[:3]} vs 期望 {sorted(leading_zero_workdir["ids"])[:3]}'
    )


# ---------------------------------------------------------------------------
# 锁4：credit 链路源头读（阶段6 对抗审查确认的同族残留，data_prep.py 读点）
# ---------------------------------------------------------------------------

def test_credit_load_preserves_leading_zero_ids(tmp_path):
    """credit 链路 load_credit_data 必须锁主键 str（与 gsfc load_data 对称）。

    审查复现的静默漏标场景：客户信息主键全数字（'00123' → int 推断 → '123'），
    坏客户标记混入一个字母数字 ID（→ object 推断 → '00123' 原样保留）——
    两表 _clean_id 后互不命中，is_bad 全 0 且无任何报错。
    """
    raw = tmp_path / 'data' / 'raw'
    raw.mkdir(parents=True)
    (raw / '客户信息.csv').write_text(
        '客户编号,企业规模,授信总金额\n00123,小型企业,100\n00456,中型企业,200\n00789,大型企业,300\n',
        encoding='utf-8-sig')
    (raw / '坏客户标记.csv').write_text(
        '客户编号\n00123\nA9999\n', encoding='utf-8-sig')

    from risk_data_prep.scripts.data_prep import (
        load_credit_data, prepare_credit_wide_table,
    )
    data = load_credit_data(project_root=str(tmp_path))
    df, _summary = prepare_credit_wide_table(
        {k: v for k, v in data.items() if v is not None})

    assert int(df['is_bad'].sum()) == 1, (
        'credit 前导零主键静默漏标（data_prep 源头读丢 dtype 锁？）')
    assert '00123' in set(df['客户编号'].astype(str)), (
        f"credit 宽表主键丢前导零：{sorted(set(df['客户编号'].astype(str)))[:3]}")


# ---------------------------------------------------------------------------
# 锁5：merge 补充表路径（阶段6 对抗审查实测的变异逃逸补锁）
# ---------------------------------------------------------------------------

def test_merge_table_preserves_leading_zero_keys(tmp_path):
    """prepare_df 三处源头读中 merge 补充表曾是唯一无承重锁的一处：
    删其 dtype 后 233 用例仍全绿（实测逃逸）。本锁：宽表+补充表主键均为
    带前导零纯数字 → left-join 后分群维度不得有 NaN。变异下补充表键失去
    前导零 → 0 匹配撞 prepare_df 的响亮 ValueError（红）。"""
    from risk_data_prep.scripts.prepare_df import prepare_df

    n = 8
    ids = [f'{i:05d}' for i in range(1, n + 1)]
    wide = pd.DataFrame({
        '客户编号': ids,
        'feat_1': range(n),
        'feat_2': [x * 1.5 for x in range(n)],
        'is_bad': [1, 0, 1, 0, 0, 0, 1, 0],
    })
    dims = pd.DataFrame({
        '客户编号': ids,
        '企业规模': ['小型企业', '中型企业'] * (n // 2),
    })
    wide_path = tmp_path / 'wide.csv'
    dims_path = tmp_path / 'dims.csv'
    wide.to_csv(wide_path, index=False, encoding='utf-8-sig')
    dims.to_csv(dims_path, index=False, encoding='utf-8-sig')

    df, _cols = prepare_df(
        str(wide_path), None, id_col='客户编号', target_col='is_bad',
        merge_table_path=str(dims_path),
    )
    assert df['企业规模'].notna().all(), (
        'merge 补充表主键前导零丢失 → left-join 部分/全部 NaN（§5.1 同族静默损坏）')
    assert set(df['客户编号']) == set(ids)
