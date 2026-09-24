# -*- coding: utf-8 -*-
""".pipeline_state.json：项目级执行历史 + Level 推进 + 已知数据集指纹。

文件位置：data/results/{project}/.pipeline_state.json（可被 --state-dir 覆盖）。
不入 git（append-only 多人协作必然冲突）。并发：save() 在同目录 `.pipeline_state.lock`
上持排他锁，重读磁盘最新版本后合并本进程的增量（历史追加 / Level 变化 / 数据集登记），
再原子替换——两个命令同时写不会互相覆盖。文件损坏时先备份为 `.corrupt-<时间戳>` 再重建。

Level 推进规则：
  prepare  → 输入与上次相同则不改 level；输入变了（换数据/主键/目标列/过滤）→ 重置为前置
  analyze  → 过渡态
  export   → Level 1
  trigger  → 需要 ≥ Level 1，推进到 Level 2
  report   → 需要 ≥ Level 1，推进到 Level 3
  query    → 不改 level
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import fcntl
except ImportError:  # Windows：无 advisory lock，退化为无锁（单机单用户场景）
    fcntl = None

from risk_core.contracts import LEVEL_ORDER as _LEVEL_ORDER  # 单一真源

from risk_core.contracts import dataset_fingerprint, now_iso


def _fingerprint_matches(stored: dict, current: dict, path: str) -> bool:
    """比对一条已存指纹与当前文件指纹是否相同；兼容新/老两种格式。

    - 新格式（schema_version=2，sha256_head + sha256_tail + size + mtime）：4 字段全等
    - 老格式（仅 sha256_first_1mb + size_bytes）：临时重算前 1MB 哈希做兼容比对，
      让既有 .pipeline_state.json 升级无痛迁移
    """
    if stored.get('schema_version') == 2 or 'sha256_head' in stored:
        return (
            stored.get('sha256_head') == current.get('sha256_head')
            and stored.get('sha256_tail') == current.get('sha256_tail')
            and stored.get('size_bytes') == current.get('size_bytes')
            and stored.get('mtime') == current.get('mtime')
        )
    if 'sha256_first_1mb' in stored:
        import hashlib as _h
        with open(path, 'rb') as f:
            chunk = f.read(1024 * 1024)
        legacy_head = _h.sha256(chunk).hexdigest()
        return (
            stored.get('sha256_first_1mb') == legacy_head
            and stored.get('size_bytes') == current.get('size_bytes')
        )
    return False


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
        # 本进程内的增量，save() 时合并到磁盘最新版本上
        self._new_history: list = []
        self._new_datasets: list = []
        self._level_reset = False

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
            if _fingerprint_matches(ds, fp, path):
                return True
        return False

    def record_dataset(self, path: str) -> None:
        if self.is_known_dataset(path):
            return
        fp = dataset_fingerprint(path)
        fp['first_seen'] = now_iso()
        self._data.setdefault('known_datasets', []).append(fp)
        self._new_datasets.append(fp)

    # ---- Level 守护 ----
    def require_level(self, min_level: str) -> None:
        if not _ge(self.current_level, min_level):
            raise PipelineLevelError(
                f'当前 Level={self.current_level!r} 不足 {min_level!r}；'
                f'请先完成上游步骤（prepare→analyze→export 抵达 Level 1）'
            )

    # ---- 输入签名（Level 与数据绑定）----
    @property
    def prepared_signature(self) -> Optional[str]:
        return self._data.get('prepared_signature')

    def bind_prepared_input(self, signature: str) -> Optional[str]:
        """登记本次 prepare 的输入签名；与上次不同且已越过前置态时，Level 重置为「前置」。

        Level 只升不降是对「同一份数据」而言的：换了宽表/坏客户清单/主键/目标列/过滤
        规则后，旧的 Level 1~3 产物已不对应当前 prepared.csv，不能继续放行下游。
        返回被重置前的 Level（未重置返回 None）。
        """
        old_sig = self._data.get('prepared_signature')
        self._data['prepared_signature'] = signature
        if old_sig is None or old_sig == signature:
            return None
        if self.current_level == _LEVEL_ORDER[0]:
            return None
        before = self.current_level
        self._data['current_level'] = _LEVEL_ORDER[0]
        self._level_reset = True
        return before

    def _maybe_promote(self, new_level: Optional[str]) -> None:
        if new_level is None:
            return
        if _level_idx(new_level) > _level_idx(self.current_level):
            self._data['current_level'] = new_level

    # ---- 历史追加 ----
    def append_history(self, entry: dict, *, new_level: Optional[str] = None) -> None:
        entry.setdefault('ts', now_iso())
        self._data.setdefault('history', []).append(entry)
        self._new_history.append(entry)
        self._maybe_promote(new_level)
        # level_after 始终落真实的 post-promotion level；若调用方传了旧值，这里会覆盖。
        # 这样 partial 步骤（如 run --pipeline credit --steps data_prep）记录的 level_after
        # 是真实 level，而非调用方预填的 Level 1。
        entry['level_after'] = self.current_level
        self._data['updated_at'] = now_iso()

    # ---- 持久化 ----
    def _merge_onto(self, disk: dict) -> dict:
        """把本进程增量合并到磁盘最新版本上（其它进程在此期间的写入得以保留）。"""
        merged = dict(disk)
        merged.setdefault('history', [])
        merged['history'] = list(merged['history']) + self._new_history
        known = list(merged.get('known_datasets', []))
        for fp in self._new_datasets:
            if not any(_fingerprint_matches(k, fp, fp.get('path', '')) for k in known
                       if k.get('schema_version') == 2 or 'sha256_head' in k):
                known.append(fp)
        merged['known_datasets'] = known
        if 'prepared_signature' in self._data:
            merged['prepared_signature'] = self._data['prepared_signature']
        disk_level = merged.get('current_level', _LEVEL_ORDER[0])
        if self._level_reset:
            # 本进程判定输入已变：以本进程结果为准（重置后又推进的也一并带上）
            merged['current_level'] = self.current_level
        elif _level_idx(self.current_level) > _level_idx(disk_level):
            merged['current_level'] = self.current_level
        for key in ('updated_at', 'created_at', 'schema_version', 'project_name'):
            if key in self._data and (key == 'updated_at' or key not in merged):
                merged[key] = self._data[key]
        return merged

    def save(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with _exclusive_lock(self.path + '.lock'):
            disk = _read_state_file(self.path)
            data = self._merge_onto(disk) if disk else self._data
            # 用 PID + 纳秒时间戳避免 tmp 文件名冲突
            tmp = f'{self.path}.{os.getpid()}.{time.time_ns()}.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        self._data = data
        self._new_history = []
        self._new_datasets = []
        self._level_reset = False


@contextlib.contextmanager
def _exclusive_lock(lock_path: str):
    """固定锁文件上的排他 advisory lock（所有进程争同一把锁）。"""
    if fcntl is None:
        yield
        return
    with open(lock_path, 'a+') as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def _read_state_file(state_path: str) -> Optional[dict]:
    """读取状态文件；不存在返回 None；损坏则备份并告警后返回 None（绝不静默丢历史）。"""
    if not os.path.isfile(state_path):
        return None
    try:
        with open(state_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        backup = f'{state_path}.corrupt-{time.strftime("%Y%m%d-%H%M%S")}'
        try:
            os.replace(state_path, backup)
        except OSError:
            backup = '(备份失败)'
        print(
            f'⚠️ [pipeline_state] 状态文件损坏无法解析（{e}）；已备份到 {backup}，'
            f'将以「前置」重建。历史记录与 Level 需人工核对备份文件恢复。',
            file=sys.stderr,
        )
        return None
    return data if isinstance(data, dict) else None


# ===== 工厂：定位 + 加载 =====

def _project_root_from_cwd() -> str:
    from risk_core.paths import get_project_root
    return get_project_root()


def _resolve_state_dir(project: str, state_dir: Optional[str], project_root: str) -> str:
    if state_dir:
        return state_dir
    # 目录派生走契约单一真源（state.json 跟随写盘根，RISK_OUTPUT_ROOT 设置时落到那里）
    from risk_core.contracts import state_results_dir
    return state_results_dir(project, project_root=project_root)


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

    with _exclusive_lock(state_path + '.lock'):
        data = _read_state_file(state_path)

    if not data or not data.get('project_name'):
        data = {
            'schema_version': 1,
            'project_name': project,
            'current_level': '前置',
            'known_datasets': [],
            'history': [],
            'created_at': now_iso(),
        }

    return PipelineState(state_path, data)


def peek_state(
    project: str,
    *,
    state_dir: Optional[str] = None,
    project_root: Optional[str] = None,
) -> Optional[dict]:
    """只读窥视状态文件（供 query 等无副作用命令）：不加锁、不备份；
    文件不存在或无法解析时返回 None。"""
    if project_root is None:
        project_root = _project_root_from_cwd()
    path = os.path.join(_resolve_state_dir(project, state_dir, project_root),
                        '.pipeline_state.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def last_export_subdir(project: str, history: Optional[list]) -> str:
    """最近一次 export 实际写入的结果子目录（``export --output-subdir``）；无记录回退 project。

    export 按 ``data/results/<subdir>`` / ``output/<subdir>`` 落盘，而 state 固定在
    ``data/results/<project>/``——读产物的命令（query/visualize/explore/report）靠它
    找到 export 实际写入的目录（subdir 可与 project 不同）。
    """
    for entry in reversed(history or []):
        if entry.get('cmd') == 'export':
            return (entry.get('args_summary') or {}).get('output_subdir') or project
    return project


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
