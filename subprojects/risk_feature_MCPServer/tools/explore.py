"""explore_thresholds 工具：薄壳 → `python -m risk_pipeline explore_thresholds`（异步 job）。

候选规则阈值探索（optbinning 最优切点 + 五道门槛业务有效性判定）。
Level 1 后只读；不推进 level。输出候选阈值表 + 分箱明细 + audit 追加节点。
"""
from pathlib import Path

from tools import cli_runner

_EXPLORE_TIMEOUT = 900  # 15 min


def execute_explore_thresholds(
    project_name: str,
    pairs_file: str,
    target_col: str,
    min_risk_ratio,
    max_p,
    min_bad_high,
    alert_rate_min,
    alert_rate_max,
    min_iv,
    min_bin_size,
) -> str:
    if not pairs_file:
        return cli_runner.err("必须提供 pairs_file（pair-list .csv/.json：列 分群维度,分群名称,特征）")
    if not Path(pairs_file).exists():
        return cli_runner.err(f"pairs_file 不存在: {pairs_file}")

    argv = ["explore_thresholds", "--project", project_name, "--pairs-file", pairs_file]
    if target_col:
        argv += ["--target-col", target_col]
    for flag, val in (
        ("--min-risk-ratio", min_risk_ratio),
        ("--max-p", max_p),
        ("--min-bad-high", min_bad_high),
        ("--alert-rate-min", alert_rate_min),
        ("--alert-rate-max", alert_rate_max),
        ("--min-iv", min_iv),
        ("--min-bin-size", min_bin_size),
    ):
        if val is not None:
            argv += [flag, str(val)]

    job_id = cli_runner.submit_cli_job(
        name=f"explore_thresholds:{project_name}",
        argv=argv,
        project_name=project_name,
        timeout=_EXPLORE_TIMEOUT,
    )
    return cli_runner.submitted(
        job_id, project_name,
        f"候选阈值探索已在后台启动。用 get_job_status(job_id='{job_id}') 查询。\n"
        f"前置要求：该 project 需已到 Level 1（先 run_pipeline）。"
        f"门槛参数留空则用默认值（风险倍数≥2.0 / 卡方p≤0.05 / 高风险侧坏客户≥10 / "
        f"触警率 1%-30% / IV≥0.02）。",
    )
