"""get_job_status / list_jobs 工具"""
import json

from tools import job_manager


def execute_get_job_status(job_id: str) -> str:
    state = job_manager.get(job_id)
    if state is None:
        return json.dumps(
            {"status": "error", "error": f"未找到 job: {job_id}"},
            ensure_ascii=False,
        )
    return json.dumps(state, ensure_ascii=False, indent=2, default=str)


def execute_list_jobs(limit: int = 20) -> str:
    jobs = job_manager.list_recent(limit=limit)
    return json.dumps(
        {"status": "success", "count": len(jobs), "jobs": jobs},
        ensure_ascii=False,
        indent=2,
        default=str,
    )
