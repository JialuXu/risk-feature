# -*- coding: utf-8 -*-
"""单元测试：prepare 列名预检 + analyze --category-dims 列存在性校验。

覆盖 Phase A/B 改动：
- A 硬错路径：column_mapping.yaml 期望分群维度在宽表中均 0% 命中 → CLI exit 1
- A 软警告路径：>0 但 <30% 命中 → stderr 警告但不阻断；features.json 写入 column_mapping_audit
- A 逃生口：--skip-preflight 时即便 0% 命中也放行
- B 列校验：analyze --category-dims 列名不存在时 exit 1 带可读错误
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from risk_mining import cli


def _run(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    out, err = capsys.readouterr()
    return exc.value.code, out, err


def _make_foreign_csv(tmp_path, n=80, bad_rate=0.15):
    """生成一份字段名完全不匹配 column_mapping.yaml 默认值的合成宽表。"""
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        'cust_no': [f'X{i:04d}' for i in range(n)],
        'industry_code': rng.choice(['A', 'B', 'C'], size=n),
        'enterprise_scale': rng.choice(['S', 'M', 'L'], size=n),
        'metric_1': rng.normal(10, 2, size=n),
        'metric_2': rng.normal(5, 1, size=n),
    })
    df['default_flag'] = (rng.random(n) < bad_rate).astype(int)
    wide = tmp_path / 'foreign.csv'
    df.to_csv(wide, index=False, encoding='utf-8-sig')
    return str(wide)


# ===== Phase A：硬错（双 segment 维度 0% 命中） =====

def test_preflight_blocks_when_all_dims_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    wide = _make_foreign_csv(tmp_path)

    code, _, err = _run([
        'prepare',
        '--wide', wide,
        '--id-col', 'cust_no',
        '--target-col', 'default_flag',
        '--project', 'foreign',
        '--confirmed-new-dataset',
    ], capsys)
    assert code == 1
    assert '配置预检' in err
    assert 'segment_dims' in err
    assert '--skip-preflight' in err


def test_preflight_skip_flag_bypasses_block(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wide = _make_foreign_csv(tmp_path)

    rc = cli.main([
        'prepare',
        '--wide', wide,
        '--id-col', 'cust_no',
        '--target-col', 'default_flag',
        '--project', 'foreign_skip',
        '--confirmed-new-dataset',
        '--skip-preflight',
    ])
    assert rc == 0

    info_path = tmp_path / 'data' / 'processed' / 'foreign_skip' / 'features.json'
    info = json.loads(info_path.read_text(encoding='utf-8'))
    assert info['preflight_skipped'] is True
    audit = info['column_mapping_audit']
    assert audit['segment_dims']['hit_rate'] == 0
    assert audit['credit_category_dims']['hit_rate'] == 0


# ===== Phase A：软警告 + audit 落盘 =====

def test_preflight_soft_warning_on_partial_match(project_workdir, capsys):
    """合成 fixture 里 segment_dims 只命中 企业规模（1/5 = 20%），应走软警告路径。"""
    rc = cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'partial',
        '--confirmed-new-dataset',
    ])
    assert rc == 0
    _, err = capsys.readouterr()
    assert '命中率' in err  # 软警告打在 stderr
    assert '20%' in err or '20 %' in err

    info_path = project_workdir['root'] / 'data' / 'processed' / 'partial' / 'features.json'
    info = json.loads(info_path.read_text(encoding='utf-8'))
    audit = info['column_mapping_audit']
    assert '企业规模' in audit['segment_dims']['actual']
    assert '所属行业' in audit['segment_dims']['missing']
    assert 0 < audit['segment_dims']['hit_rate'] < 0.3
    assert info['preflight_skipped'] is False


# ===== Phase B：analyze --category-dims 列存在性 =====

def test_analyze_rejects_unknown_category_dim(project_workdir, capsys):
    cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'panl',
        '--confirmed-new-dataset',
    ])
    code, _, err = _run([
        'analyze', '--project', 'panl',
        '--category-dims', '不存在的列',
    ], capsys)
    assert code == 1
    assert '不存在' in err
    assert '不存在的列' in err
    assert 'prepared.csv 前 30 列' in err


def test_analyze_accepts_existing_category_dim(project_workdir):
    """已存在的 --category-dims 不应被新校验误伤。"""
    cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'panl2',
        '--confirmed-new-dataset',
    ])
    rc = cli.main([
        'analyze', '--project', 'panl2',
        '--steps', 'univariate',
        '--category-dims', '企业规模',
        '--quiet',
    ])
    assert rc == 0
