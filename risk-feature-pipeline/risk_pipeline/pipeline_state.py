# -*- coding: utf-8 -*-
""".pipeline_state.json：项目级执行历史 + Level 推进 + 已知数据集指纹。

文件位置：data/results/{project}/.pipeline_state.json（可被 --state-dir 覆盖）。
不入 git（append-only 多人协作必然冲突）；用 fcntl.flock 做 advisory lock。

Level 推进规则：
  prepare  → 不改 level（保持当前）
  analyze  → 过渡态
  export   → Level 1
  trigger  → 需要 ≥ Level 1，推进到 Level 2
  report   → 需要 ≥ Level 1，推进到 Level 3
  query    → 不改 level
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Optional

from .cli_io import dataset_fingerprint, utc_now_iso


_LEVEL_ORDER = ['前置', '过渡态', 'Level 1', 'Level 2', 'Level 3']


class PipelineLevelError(Exception):
    """当前 Level 不满足子命令的最低前置要求。"""


def _level_idx(level: str) -> int:
    try:
        return _LEVEL_ORDER.index(level)
    except ValueError:
        return -1


def _ge(level_a: str, level_b: str) -> bool:
    return _level_idx(level_a) >= _level_idx(level_b)


class PipelineState:
    """项目状态：包装 state.json 的读写，提供 Level 推进和历史追加。"""

    def __init__(self, path: str, data: dict):
        self.path = path
        self._data = data

    # ---- 只读属性 ----
    @property
    def project_name(self) -> str:
        return self._data['project_name']

    @property
    def current_level(self) -> str:
        return self._data.get('current_level', '前置')

    @property
    def known_datasets(self) -> list:
        return self._data.get('known_datasets', [])

    @property
    def history(self) -> list:
        return self._data.get('history', [])

    # ---- 数据集指纹 ----
    def is_known_dataset(self, path: str) -> bool:
        fp = dataset_fingerprint(path)
        for ds in self.known_datasets:
            if (
                ds.get('sha256_first_1mb') == fp['sha256_first_1mb']
                and ds.get('size_bytes') == fp['size_bytes']
            ):
                return True
        return False

    def record_dataset(self, path: str) -> None:
        if self.is_known_dataset(path):
            return
        fp = dataset_fingerprint(path)
        fp['first_seen'] = utc_now_iso()
        self._data.setdefault('known_datasets', []).append(fp)

    # ---- Level 守护 ----
    def require_level(self, min_level: str) -> None:
        if not _ge(self.current_level, min_level):
            raise PipelineLevelError(
                f'当前 Level={self.current_level!r} 不足 {min_level!r}；'
                f'请先完成上游步骤（prepare→analyze→export 抵达 Level 1）'
            )

    def _maybe_promote(self, new_level: Optional[str]) -> None:
        if new_level is None:
            return
        if _level_idx(new_level) > _level_idx(self.current_level):
            self._data['current_level'] = new_level

    # ---- 历史追加 ----
    def append_history(self, entry: dict, *, new_level: Optional[str] = None) -> None:
        entry.setdefault('ts', utc_now_iso())
        self._data.setdefault('history', []).append(entry)
        self._maybe_promote(new_level)
        # level_after 始终落真实的 post-promotion level；若调用方传了旧值，这里会覆盖。
        # 这样 partial 步骤（如 run --pipeline credit --steps data_prep）不会再把 level
        # 谎报为 Level 1。
        entry['level_after'] = self.current_level
        self._data['updated_at'] = utc_now_iso()

    # ---- 持久化 ----
    def save(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # 用 PID + 纳秒时间戳避免并发场景下 tmp 文件名冲突（两个进程同时 save 时
        # 否则后到的会因前一个已 os.replace 而 FileNotFoundError）
        import time as _t
        tmp = f'{self.path}.{os.getpid()}.{_t.time_ns()}.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(self._data, f, ensure_ascii=False, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        os.replace(tmp, self.path)


# ===== 工厂：定位 + 加载 =====

def _project_root_from_cwd() -> str:
    from .paths import get_project_root
    return get_project_root()


def _resolve_state_dir(project: str, state_dir: Optional[str], project_root: str) -> str:
    if state_dir:
        return state_dir
    # state.json 跟随写盘根（RISK_OUTPUT_ROOT 设置时落到那里）
    from .paths import get_output_root
    if os.environ.get('RISK_OUTPUT_ROOT'):
        return os.path.join(get_output_root(), 'data', 'results', project)
    return os.path.join(project_root, 'data', 'results', project)


def load_state(
    project: str,
    *,
    state_dir: Optional[str] = None,
    project_root: Optional[str] = None,
) -> PipelineState:
    """读取（或新建）项目状态文件。"""
    if project_root is None:
        project_root = _project_root_from_cwd()

    sd = _resolve_state_dir(project, state_dir, project_root)
    Path(sd).mkdir(parents=True, exist_ok=True)
    state_path = os.path.join(sd, '.pipeline_state.json')

    data = None
    if os.path.isfile(state_path):
        with open(state_path, 'r', encoding='utf-8') as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                data = json.load(f)
            except (json.JSONDecodeError, OSError):
                data = None
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    if not data or not data.get('project_name'):
        data = {
            'schema_version': 1,
            'project_name': project,
            'current_level': '前置',
            'known_datasets': [],
            'history': [],
            'created_at': utc_now_iso(),
        }

    return PipelineState(state_path, data)


# ===== 状态印章 =====

def format_status_stamp(
    cmd: str,
    project: str,
    level_after: str,
    *,
    inputs=None,
    outputs=None,
    extras=None,
) -> str:
    """格式化每个子命令完成时打印的回执；agent 会原样转给用户。"""
    head = f'[{cmd}] OK | project={project} | level={level_after}'
    lines = [head]
    if extras:
        for line in extras:
            lines.append(f'  {line}')
    if inputs:
        first, *rest = inputs
        lines.append(f'  inputs:  {first}')
        for r in rest:
            lines.append(f'           {r}')
    if outputs:
        first, *rest = outputs
        lines.append(f'  outputs: {first}')
        for r in rest:
            lines.append(f'           {r}')
    return '\n'.join(lines)
