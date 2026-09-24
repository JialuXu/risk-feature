# -*- coding: utf-8 -*-
"""单元测试：PipelineState 行为（Level 推进、known_datasets、并发锁）。"""
from __future__ import annotations

import threading

import pytest

from risk_mining.pipeline_state import PipelineLevelError, load_state


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


def test_fingerprint_detects_append(tmp_path):
    """追加新行后 is_known_dataset 应返回 False。

    覆盖之前 dataset_fingerprint 只摘前 1MB 时的漏判场景：
    宽表追加新客户但表头不变，旧实现只看前 1MB 会误判为"已知数据集"，
    悄悄绕过 prepare 阶段的阻断节点 1。
    """
    import time as _t
    f = tmp_path / 'wide.csv'
    f.write_bytes(b'col1,col2\n' + b'1,2\n' * 100)
    state = load_state('p_append', state_dir=str(tmp_path))
    state.record_dataset(str(f))
    assert state.is_known_dataset(str(f))

    # 等一下让 mtime 必然变化，然后追加
    _t.sleep(0.05)
    with open(f, 'ab') as fp:
        fp.write(b'9,9\n' * 50)
    assert not state.is_known_dataset(str(f))


def test_fingerprint_legacy_format_compat(tmp_path):
    """老格式 .pipeline_state.json（只含 sha256_first_1mb + size_bytes）应能继续匹配同一份文件。

    保证用户现有的 state.json 不会因为指纹升级被全部失效——首次升级时
    is_known_dataset 仍能识别老条目，避免"所有已知数据集都要重新确认一遍"。
    """
    import hashlib as _h
    import json as _j

    f = tmp_path / 'wide.csv'
    f.write_bytes(b'col1,col2\n1,2\n3,4\n')
    legacy_chunk = f.read_bytes()[:1024 * 1024]
    legacy_fp = {
        'path': str(f),
        'sha256_first_1mb': _h.sha256(legacy_chunk).hexdigest(),
        'size_bytes': f.stat().st_size,
        'first_seen': '2024-01-01T00:00:00+08:00',
    }
    state_path = tmp_path / '.pipeline_state.json'
    state_path.write_text(_j.dumps({
        'schema_version': 1,
        'project_name': 'p_legacy',
        'current_level': '前置',
        'known_datasets': [legacy_fp],
        'history': [],
        'created_at': '2024-01-01T00:00:00+08:00',
    }, ensure_ascii=False))

    state = load_state('p_legacy', state_dir=str(tmp_path))
    assert state.is_known_dataset(str(f))


def test_fingerprint_small_file(tmp_path):
    """size < HEAD+TAIL 的小文件指纹仍应稳定（同一份文件两次记录去重）。"""
    f = tmp_path / 'tiny.csv'
    f.write_bytes(b'a,b\n1,2\n')
    state = load_state('p_small', state_dir=str(tmp_path))
    state.record_dataset(str(f))
    state.record_dataset(str(f))
    assert len(state.known_datasets) == 1
    assert state.is_known_dataset(str(f))


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
    # save() 在固定锁文件下重读磁盘并合并增量：两个线程的历史都应保留
    assert data['project_name'] == 'p1'
    assert len(data['history']) == 10
