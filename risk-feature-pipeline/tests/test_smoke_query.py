# -*- coding: utf-8 -*-
"""端到端 smoke：query 子命令读取已导出结果。"""
from __future__ import annotations

from risk_pipeline import cli


def test_query_iv_top(project_workdir, capsys):
    # 先跑 full 再 query
    cli.main([
        'run', '--pipeline', 'generic',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'smoke_q',
        '--quiet', '--confirmed-new-dataset',
    ])
    capsys.readouterr()  # 清空 buffer

    rc = cli.main([
        'query', '--project', 'smoke_q', '--kind', 'iv', '--top', '3',
    ])
    assert rc == 0
    out, _ = capsys.readouterr()
    # 输出至少 3 行特征 + 表头
    lines = [l for l in out.strip().split('\n') if l.strip()]
    assert len(lines) >= 4


def test_query_csv_format(project_workdir, capsys):
    cli.main([
        'run', '--pipeline', 'generic',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'smoke_q2',
        '--quiet', '--confirmed-new-dataset',
    ])
    capsys.readouterr()

    rc = cli.main([
        'query', '--project', 'smoke_q2', '--kind', 'iv', '--top', '5',
        '--output-format', 'csv',
    ])
    assert rc == 0
    out, _ = capsys.readouterr()
    assert 'IV值' in out
    # CSV 至少 5 行数据 + 表头
    lines = [l for l in out.strip().split('\n') if l.strip()]
    assert len(lines) >= 6
