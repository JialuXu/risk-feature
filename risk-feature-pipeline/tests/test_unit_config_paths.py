# -*- coding: utf-8 -*-
"""回归测试：设计检视第三批（输出路径不再 import 时冻结、读写路径一致、全局 flag 不丢）。"""
from __future__ import annotations

import os
import shutil

import pytest

from risk_core.paths import ENV_OUTPUT_ROOT
from risk_mining import cli


def _run_generic(project_workdir, project):
    cli.main([
        'run', '--pipeline', 'generic',
        '--wide', project_workdir['wide'], '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号', '--target-col', 'is_bad',
        '--project', project, '--quiet', '--confirmed-new-dataset',
    ])


# ===== 全局 flag：写在子命令前后都生效 =====

@pytest.mark.parametrize('argv', [
    ['-q', '--state-dir', 'S', '--verbose', 'query', '--project', 'p', '--kind', 'iv'],
    ['query', '--project', 'p', '--kind', 'iv', '-q', '--state-dir', 'S', '--verbose'],
])
def test_global_flags_survive_either_position(argv):
    args = cli._build_parser().parse_args(argv)
    assert args.quiet is True and args.verbose is True and args.state_dir == 'S'


def test_global_flags_default_when_absent():
    args = cli._build_parser().parse_args(['query', '--project', 'p', '--kind', 'iv'])
    assert args.quiet is False and args.verbose is False
    assert args.state_dir is None


# ===== 输出路径常量：随访问时的 RISK_OUTPUT_ROOT 解析 =====

def test_output_path_constants_follow_env_set_after_import(tmp_path, monkeypatch):
    import risk_core.config as cfg
    from risk_export_report.scripts import config as export_cfg

    monkeypatch.delenv(ENV_OUTPUT_ROOT, raising=False)
    assert cfg.RESULTS_DIR_CREDIT == 'data/results/征信'
    monkeypatch.setenv(ENV_OUTPUT_ROOT, str(tmp_path))
    assert cfg.RESULTS_DIR_CREDIT == os.path.join(str(tmp_path), 'data/results/征信')
    assert export_cfg.pipeline_paths('gsfc')['output_rel'] == cfg.OUTPUT_DIR_GSFC
    assert export_cfg.RESULTS_DIR_GSFC == cfg.RESULTS_DIR_GSFC        # gsfc 链路的读法


def test_python_api_export_honours_output_root(project_workdir, synthetic_dataframe, monkeypatch):
    from risk_mining.pipeline import run_generic_pipeline

    out_root = project_workdir['root'] / 'out'
    monkeypatch.setenv(ENV_OUTPUT_ROOT, str(out_root))
    feats = [c for c in synthetic_dataframe.columns if c.startswith('feat_')]
    run_generic_pipeline(synthetic_dataframe, feats, project_name='api_out',
                         category_dims=['企业规模'], qual_dims=[],
                         steps=['iv', 'export'], verbose=False)
    assert (out_root / 'data' / 'results' / 'api_out' / 'api_out_IV分析结果_全量.csv').is_file()
    assert not (project_workdir['root'] / 'data' / 'results' / 'api_out').exists()


# ===== 读产物的命令与 export 同一位置 =====

def test_query_reads_from_output_root(project_workdir, monkeypatch, capsys):
    monkeypatch.setenv(ENV_OUTPUT_ROOT, str(project_workdir['root'] / 'out'))
    _run_generic(project_workdir, 'q_root')
    capsys.readouterr()
    assert cli.main(['-q', 'query', '--project', 'q_root', '--kind', 'iv', '--top', '3',
                     '--output-format', 'csv']) == 0
    assert 'IV值' in capsys.readouterr().out


def test_query_and_report_follow_export_output_subdir(project_workdir, capsys, tmp_path):
    _run_generic(project_workdir, 'q_sub')
    assert cli.main(['-q', 'export', '--project', 'q_sub', '--output-subdir', 'custom']) == 0
    root = project_workdir['root']
    # 删掉默认子目录下的产物（保留 state），只剩 custom/ 一份
    for p in (root / 'data' / 'results' / 'q_sub').glob('*.csv'):
        p.unlink()
    shutil.rmtree(root / 'output' / 'q_sub')
    capsys.readouterr()

    assert cli.main(['-q', 'query', '--project', 'q_sub', '--kind', 'iv', '--top', '3',
                     '--output-format', 'csv']) == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert 'IV值' in lines[0] and len(lines) >= 4

    md = tmp_path / 'r.md'
    md.write_text('# 报告\n', encoding='utf-8')
    try:
        cli.main(['-q', 'report', '--project', 'q_sub', '--report-markdown', str(md),
                  '--purpose', 'internal'])
    except SystemExit:
        pass  # 本机缺 Node docx 依赖时在渲染阶段退出；这里只验证默认 LLM JSON 能找到
    assert 'LLM JSON 不存在' not in capsys.readouterr().err
