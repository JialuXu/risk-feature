"""report 工具：薄壳 → `python -m risk_pipeline report`（异步 job）。

LLM JSON + 人工 Markdown 正文 → 正式 .docx（→ Level 3）。
走 CLI 子进程以继承阻断节点 3（purpose=external 必须 confirmed_final_version=true）。
"""
from pathlib import Path

from tools import cli_runner

_REPORT_TIMEOUT = 600  # 10 min
_VALID_PURPOSE = {"internal", "external"}
_VALID_APPENDIX = {"both", "feature", "segment", "none", "compact"}


def execute_report(
    project_name: str,
    report_markdown: str,
    purpose: str,
    llm_json: str,
    output: str,
    appendix_mode: str,
    confirmed_final_version: bool,
) -> str:
    if purpose not in _VALID_PURPOSE:
        return cli_runner.err(f"purpose 必须是 {_VALID_PURPOSE} 之一，收到: {purpose!r}")
    if not report_markdown:
        return cli_runner.err("必须提供 report_markdown（LLM 生成的 Markdown 正文路径）")
    if not Path(report_markdown).exists():
        return cli_runner.err(f"report_markdown 不存在: {report_markdown}")
    if llm_json and not Path(llm_json).exists():
        return cli_runner.err(f"llm_json 不存在: {llm_json}")
    if appendix_mode and appendix_mode not in _VALID_APPENDIX:
        return cli_runner.err(
            f"appendix_mode 必须是 {_VALID_APPENDIX} 之一，收到: {appendix_mode!r}"
        )

    argv = [
        "report", "--project", project_name,
        "--report-markdown", report_markdown,
        "--purpose", purpose,
    ]
    if llm_json:
        argv += ["--llm-json", llm_json]
    if output:
        argv += ["--output", output]
    if appendix_mode:
        argv += ["--appendix-mode", appendix_mode]
    if confirmed_final_version:
        argv += ["--confirmed-final-version"]

    job_id = cli_runner.submit_cli_job(
        name=f"report:{project_name}",
        argv=argv,
        project_name=project_name,
        timeout=_REPORT_TIMEOUT,
    )
    return cli_runner.submitted(
        job_id, project_name,
        f"报告生成已在后台启动（输出 .docx）。用 get_job_status(job_id='{job_id}') 查询。\n"
        f"前置要求：该 project 需已到 Level 1（LLM JSON 由 run_pipeline 的 export 产出）。"
        f"purpose='external' 且未传 confirmed_final_version=true 时，"
        f"CLI 会在【阻断节点 3】停下（防止终版报告与数据脱钩）。",
    )
