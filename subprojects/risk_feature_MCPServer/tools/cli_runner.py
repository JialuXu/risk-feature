"""统一 CLI 子进程执行：MCP 工具薄壳 → `python -m risk_pipeline <argv>`（异步 job）。

为什么走子进程而非直调 Python API：
  CLI 层（risk_pipeline.cli_commands）承载了 pipeline 的状态机、三个阻断节点、
  _audit.json、Level 推进，以及 generic 的 prepare→analyze→export（含 rules）真实流程。
  - 直调 run_generic_pipeline 会绕过全部守门，且跑的是老的单体路径（与当前 CLI 行为不一致）；
  - cli_commands._err() 走 sys.exit()，在进程内直调会打穿 MCP server 进程 / 让 job 线程静默退出。
  子进程让 MCP 自动继承上述全部保证，并与 pipeline 内部实现解耦（CLI 才是稳定契约）。

CLI 把状态印章打到 stdout、把阻断节点/校验错误打到 stderr。本模块在子进程失败时
原样抛出 stderr，使 get_job_status 能看到完整的阻断提示。
"""
import contextlib
import json
import os
import subprocess
import sys
import tempfile

from config import PIPELINE_ROOT, get_result_candidate_dirs
from tools import job_manager

_MAX_CAPTURE = 8000  # 截断巨量日志，避免塞爆 job 状态文件


def _module_cmd(argv: list) -> list:
    # 用 sys.executable 保证子进程与 server 同一 Python 环境（pipeline 依赖已装于此）
    return [sys.executable, "-m", "risk_pipeline", *argv]


def run_cli(argv: list, timeout: int = 1800) -> dict:
    """同步执行 CLI 子命令；cwd 锁到 PIPELINE_ROOT 以让 `-m risk_pipeline` 可解析。"""
    proc = subprocess.run(
        _module_cmd(argv),
        cwd=str(PIPELINE_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "argv": argv,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-_MAX_CAPTURE:],
        "stderr": proc.stderr[-_MAX_CAPTURE:],
    }


def scan_outputs(project_name: str) -> list:
    """扫描某项目所有可能落盘目录里的产物（CSV/JSON/PNG/DOCX，含 charts 子目录）。"""
    files: list = []
    for d in get_result_candidate_dirs(project_name):
        if not d.exists():
            continue
        for pat in ("*.csv", "*.json", "*.png", "*.docx"):
            # 跳过 .pipeline_state.json 等内部点文件，只报真正的交付产物
            files += [str(f) for f in sorted(d.glob(pat)) if not f.name.startswith(".")]
        charts = d / "charts"
        if charts.exists():
            files += [str(f) for f in sorted(charts.glob("*.png"))]
    return sorted(set(files))


def write_temp_json(obj, suffix: str = ".json") -> str:
    """把 dict/list 写到临时 JSON 文件，返回路径（供 --filter-file / --exclude-features-file 等）。"""
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="mcp_risk_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return path


def _cli_job_blocking(argv: list, project_name: str, timeout: int, tmp_paths: list) -> dict:
    """job 线程内执行：跑子进程 → 清理临时文件 → 失败抛 stderr / 成功扫产物。"""
    try:
        res = run_cli(argv, timeout=timeout)
    finally:
        for p in tmp_paths:
            with contextlib.suppress(OSError):
                os.unlink(p)

    if res["returncode"] != 0:
        # 阻断节点 / 入参校验错误都在 stderr；原样抛出让用户看到完整提示
        raise RuntimeError(
            f"CLI 退出码 {res['returncode']}\n"
            f"--- stderr ---\n{res['stderr'] or '(空)'}\n"
            f"--- stdout ---\n{res['stdout'] or '(空)'}"
        )

    output_files = scan_outputs(project_name)
    return {
        "project_name": project_name,
        "returncode": 0,
        "cli_argv": argv,
        "output_files": output_files,
        "file_count": len(output_files),
        "cli_stdout_tail": res["stdout"][-2000:],
    }


def submit_cli_job(
    name: str, argv: list, project_name: str, timeout: int, tmp_paths: list = None
) -> str:
    """提交一个跑 CLI 子命令的异步 job，立即返回 job_id。"""
    return job_manager.submit(
        name=name,
        func=_cli_job_blocking,
        argv=argv,
        project_name=project_name,
        timeout=timeout,
        tmp_paths=tmp_paths or [],
    )


# ── 统一响应封装 ────────────────────────────────────────────────────────────

def err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)


def submitted(job_id: str, project_name: str, message: str) -> str:
    return json.dumps(
        {
            "status": "submitted",
            "job_id": job_id,
            "project_name": project_name,
            "message": message,
        },
        ensure_ascii=False,
        indent=2,
    )
