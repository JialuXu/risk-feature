"""visualize 工具：薄壳 → `python -m risk_pipeline visualize`（异步 job）。

Level 1 后只读已落盘 CSV → 出 PNG 图表；不推进 level。
"""
from tools import cli_runner

_VISUALIZE_TIMEOUT = 600  # 10 min
_VALID_KINDS = {
    "iv", "iv_heatmap", "corr_heatmap", "lr_heatmap",
    "auc", "segment", "rules", "combos", "thresholds",
}


def execute_visualize(
    project_name: str,
    kinds: list,
    dim: str,
    top: int,
    dpi: int,
) -> str:
    if kinds:
        invalid = set(kinds) - _VALID_KINDS
        if invalid:
            return cli_runner.err(
                f"无效 kinds: {sorted(invalid)}；可选: {sorted(_VALID_KINDS)}"
            )

    argv = ["visualize", "--project", project_name]
    if kinds:
        argv += ["--kinds", ",".join(kinds)]
    if dim:
        argv += ["--dim", dim]
    if top:
        argv += ["--top", str(top)]
    if dpi:
        argv += ["--dpi", str(dpi)]

    job_id = cli_runner.submit_cli_job(
        name=f"visualize:{project_name}",
        argv=argv,
        project_name=project_name,
        timeout=_VISUALIZE_TIMEOUT,
    )
    return cli_runner.submitted(
        job_id, project_name,
        f"出图已在后台启动（输出 output/{project_name}/charts/*.png）。"
        f"用 get_job_status(job_id='{job_id}') 查询。\n"
        f"前置要求：该 project 需已到 Level 1（先 run_pipeline）。"
        f"rules/combos/thresholds 类图需对应步骤已跑过（analyze 含 rules / explore_thresholds），"
        f"缺对应 CSV 的图会被自动跳过。",
    )
