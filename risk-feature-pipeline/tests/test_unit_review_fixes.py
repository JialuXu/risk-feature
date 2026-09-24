# -*- coding: utf-8 -*-
"""回归测试：设计检视第一批修复（IV 零膨胀分箱 / 全局 IV / 中间产物残留 / Level 绑定数据 / 状态并发）。"""
from __future__ import annotations

import json
import os
import threading

import numpy as np
import pandas as pd

from risk_mining import cli
from risk_mining.pipeline_state import load_state


# ===== IV：零膨胀特征不再塌成 1 箱 =====

def test_calc_iv_zero_inflated_keeps_tail_signal():
    from risk_mining.analysis.iv_core import calc_iv

    rng = np.random.default_rng(0)
    x = np.r_[np.zeros(920), rng.uniform(1, 10, 80)]
    y = np.r_[rng.random(920) < 0.05, rng.random(80) < 0.5].astype(int)
    df = pd.DataFrame({'逾期次数': x, 'is_bad': y})

    iv, meta = calc_iv(df, '逾期次数', 'is_bad')
    assert meta['n_bins_actual'] >= 2
    # 同信息的 0/1 标记 IV 约 1.5；修复前连续版本为 0
    assert iv > 1.0


def test_calc_iv_regular_continuous_unchanged():
    """普通连续特征仍走等频分箱，分箱数 = 自适应分箱数。"""
    from risk_mining.analysis.iv_core import calc_iv

    rng = np.random.default_rng(1)
    x = rng.normal(size=2000)
    y = (rng.random(2000) < 1 / (1 + np.exp(-(x - 2)))).astype(int)
    iv, meta = calc_iv(pd.DataFrame({'f': x, 'is_bad': y}), 'f', 'is_bad')
    assert meta['n_bins_actual'] == 10
    assert iv > 0


# ===== analyze：重跑核心分析时清理上一轮中间产物 =====

def _prepare(project_workdir, project, extra=()):
    return cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号', '--target-col', 'is_bad',
        '--project', project, '--quiet', '--confirmed-new-dataset',
        *extra,
    ])


def _write_large_wide(project_workdir, n=1200):
    """默认合成数据每个分群坏客户不足 15，单变量会全部跳过；这里换成足量样本。"""
    rng = np.random.default_rng(7)
    df = pd.DataFrame({
        '客户编号': [f'C{i:05d}' for i in range(n)],
        '企业规模': rng.choice(['小型企业', '中型企业'], size=n),
    })
    for i in range(1, 5):
        df[f'feat_{i}'] = rng.normal(size=n)
    df['is_bad'] = (rng.random(n) < 1 / (1 + np.exp(-(df['feat_1'] * 1.5 - 1.8)))).astype(int)
    wide = project_workdir['root'] / project_workdir['wide']
    df.to_csv(wide, index=False, encoding='utf-8-sig')
    bad = project_workdir['root'] / project_workdir['bad']
    df.loc[df['is_bad'] == 1, ['客户编号']].to_csv(bad, index=False, encoding='utf-8-sig')


def test_analyze_rerun_clears_stale_intermediate(project_workdir):
    from risk_mining.commands._common import _intermediate_dir

    _write_large_wide(project_workdir)
    _prepare(project_workdir, 'stale')
    cli.main(['analyze', '--project', 'stale', '--quiet',
              '--steps', 'univariate,iv,lr', '--category-dims', '企业规模'])
    inter = _intermediate_dir('stale')
    assert os.path.isfile(os.path.join(inter, 'corr_long.csv'))

    cli.main(['analyze', '--project', 'stale', '--quiet',
              '--steps', 'iv', '--category-dims', '企业规模'])
    assert os.path.isfile(os.path.join(inter, 'iv_full.csv'))
    assert not os.path.isfile(os.path.join(inter, 'corr_long.csv'))
    assert not any(n.startswith('corr_wide_') for n in os.listdir(inter))


def test_clear_intermediate_only_touches_pipeline_files(tmp_path):
    from risk_core.contracts import clear_intermediate

    for name in ('iv_full.csv', 'rules.pkl', 'manifest.json', '备注.txt'):
        (tmp_path / name).write_text('x', encoding='utf-8')
    assert clear_intermediate(str(tmp_path)) == 3
    assert sorted(os.listdir(tmp_path)) == ['备注.txt']


# ===== prepare：输入变化时 Level 重置为前置 =====

def test_prepare_same_input_keeps_level(project_workdir):
    _prepare(project_workdir, 'lv')
    state = load_state('lv')
    state.append_history({'cmd': 'export'}, new_level='Level 1')
    state.save()

    _prepare(project_workdir, 'lv')
    assert load_state('lv').current_level == 'Level 1'


def test_prepare_changed_input_resets_level(project_workdir, capsys):
    _prepare(project_workdir, 'lv2')
    state = load_state('lv2')
    state.append_history({'cmd': 'report'}, new_level='Level 3')
    state.save()

    filt = project_workdir['root'] / 'filter.json'
    filt.write_text(json.dumps({'企业规模': {'exclude': ['微型企业']}}, ensure_ascii=False),
                    encoding='utf-8')
    capsys.readouterr()
    _prepare(project_workdir, 'lv2', extra=('--filter-file', str(filt)))
    _, err = capsys.readouterr()
    assert load_state('lv2').current_level == '前置'
    assert 'Level 由 Level 3 重置为 前置' in err


# ===== pipeline_state：并发写合并 + 损坏备份 =====

def test_concurrent_saves_keep_both_histories_and_max_level(tmp_path):
    a = load_state('p', state_dir=str(tmp_path))
    b = load_state('p', state_dir=str(tmp_path))
    a.append_history({'cmd': 'A'}, new_level='Level 2')
    a.save()
    b.append_history({'cmd': 'B'})
    b.save()

    final = load_state('p', state_dir=str(tmp_path))
    assert [h['cmd'] for h in final.history] == ['A', 'B']
    assert final.current_level == 'Level 2'


def test_threaded_saves_lose_no_history(tmp_path):
    def worker(tag):
        st = load_state('p', state_dir=str(tmp_path))
        for i in range(5):
            st.append_history({'cmd': f'{tag}-{i}'})
        st.save()

    threads = [threading.Thread(target=worker, args=(t,)) for t in 'ABCD']
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(load_state('p', state_dir=str(tmp_path)).history) == 20


def test_corrupt_state_is_backed_up_not_silently_dropped(tmp_path, capsys):
    path = tmp_path / '.pipeline_state.json'
    path.write_text('{"project_name": "p", "current_level": "Lev', encoding='utf-8')

    state = load_state('p', state_dir=str(tmp_path))
    _, err = capsys.readouterr()
    assert state.current_level == '前置'
    assert '状态文件损坏' in err
    backups = [n for n in os.listdir(tmp_path) if '.corrupt-' in n]
    assert len(backups) == 1
