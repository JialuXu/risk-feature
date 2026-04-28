"""后台 job 管理：避免 Claude Desktop 的 MCP 调用超时（默认 60s）"""
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()

# job 状态目录：持久化到磁盘，server 重启后仍可查
_STATE_DIR = Path.home() / ".risk_feature_mcp_jobs"
_STATE_DIR.mkdir(exist_ok=True)


def _persist(job_id: str, state: dict) -> None:
    path = _STATE_DIR / f"{job_id}.json"
    path.write_text(json.dumps(state, ensure_ascii=False, default=str), encoding="utf-8")


def _load(job_id: str) -> Optional[dict]:
    path = _STATE_DIR / f"{job_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def submit(name: str, func: Callable, **kwargs) -> str:
    job_id = uuid.uuid4().hex[:12]
    state = {
        "job_id": job_id,
        "name": name,
        "status": "running",
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": None,
        "result": None,
        "error": None,
    }
    with _LOCK:
        _JOBS[job_id] = state
    _persist(job_id, state)

    def _worker():
        try:
            result = func(**kwargs)
            state["status"] = "success"
            state["result"] = result
        except Exception as e:
            state["status"] = "error"
            state["error"] = str(e)
        finally:
            state["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            _persist(job_id, state)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return job_id


def get(job_id: str) -> Optional[dict]:
    with _LOCK:
        state = _JOBS.get(job_id)
    if state is None:
        state = _load(job_id)
    return state


def list_recent(limit: int = 20) -> list[dict]:
    jobs = []
    for path in sorted(_STATE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            jobs.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return jobs
