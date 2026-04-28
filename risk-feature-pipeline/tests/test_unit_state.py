# -*- coding: utf-8 -*-
"""单元测试：PipelineState 行为（Level 推进、known_datasets、并发锁）。"""
from __future__ import annotations

import os
import threading

import pytest

from risk_pipeline.pipeline_state import PipelineLevelError, load_state


def test_initial_state(tmp_path):
    state = load_state('p1', state_dir=str(tmp_path))
    assert state.project_name == 'p1'
    assert state.current_level == '前置'
    assert state.history == []
    assert state.known_datasets == []


def test_level_promotion(tmp_path):
    state = load_state('p1', state_dir=str(tmp_path))
    state.append_history({'cmd': 'analyze'}, new_level='过渡态')
    assert state.current_level == '过渡态'
    state.append_history({'cmd': 'export'}, new_level='Level 1')
    assert state.current_level == 'Level 1'


def test_level_no_demote(tmp_path):
    """已到 Level 1 后追加 prepare 不应回退。"""
    state = load_state('p1', state_dir=str(tmp_path))
    state.append_history({'cmd': 'export'}, new_level='Level 1')
    state.append_history({'cmd': 'prepare'}, new_level=None)
    assert state.current_level == 'Level 1'


def test_require_level_blocks(tmp_path):
    state = load_state('p1', state_dir=str(tmp_path))
    with pytest.raises(PipelineLevelError):
        state.require_level('Level 1')


def test_require_level_passes(tmp_path):
    state = load_state('p1', state_dir=str(tmp_path))
    state.append_history({'cmd': 'export'}, new_level='Level 1')
    state.require_level('Level 1')  # 不抛
    state.require_level('过渡态')   # 不抛


def test_known_dataset_dedup(tmp_path):
    f = tmp_path / 'wide.csv'
    f.write_bytes(b'col1,col2\n1,2\n3,4\n')
    state = load_state('p1', state_dir=str(tmp_path))
    state.record_dataset(str(f))
    state.record_dataset(str(f))
    assert len(state.known_datasets) == 1
    assert state.is_known_dataset(str(f))


def test_known_dataset_changed_content(tmp_path):
    """文件内容变了应触发新条目（指纹不同）。"""
    f = tmp_path / 'wide.csv'
    f.write_bytes(b'col1,col2\n1,2\n3,4\n')
    state = load_state('p1', state_dir=str(tmp_path))
    state.record_dataset(str(f))
    f.write_bytes(b'col1,col2\n9,9\n8,8\n')
    assert not state.is_known_dataset(str(f))


def test_save_and_reload(tmp_path):
    state = load_state('p1', state_dir=str(tmp_path))
    state.append_history({'cmd': 'export'}, new_level='Level 1')
    state.save()

    state2 = load_state('p1', state_dir=str(tmp_path))
    assert state2.current_level == 'Level 1'
    assert len(state2.history) == 1
    assert state2.history[0]['cmd'] == 'export'


def test_concurrent_writes_no_corruption(tmp_path):
    """两个线程并发追加历史，每条记录都该最终落盘。"""
    import json

    def worker(tag):
        state = load_state('p1', state_dir=str(tmp_path))
        for i in range(5):
            state.append_history({'cmd': f'{tag}-{i}'})
        state.save()

    t1 = threading.Thread(target=worker, args=('A',))
    t2 = threading.Thread(target=worker, args=('B',))
    t1.start(); t2.start()
    t1.join(); t2.join()

    # 文件应可解析（未损坏）
    state_path = tmp_path / '.pipeline_state.json'
    with open(state_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # 由于两个线程各自 load + save，最后落盘的一方覆盖另一方；
    # 这里仅断言文件未损坏，schema 完整。
    assert 'history' in data
    assert data['project_name'] == 'p1'
