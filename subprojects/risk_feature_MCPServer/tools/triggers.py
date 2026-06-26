"""extract_triggers 工具：薄壳 → `python -m risk_pipeline trigger`（异步 job）。

走 CLI 子进程以继承：
  - 阻断节点 2（confirmed=true 才放行；features 配置错会直接污染预警名单）
  - Level 1 守门（trigger 作用于项目的 prepared.csv，须先 run_pipeline 到 Level 1）
  - features 注入：默认 GSFC 特征仅适配工商财务主题；征信/舆情/generic 必须用
    features_file 注入项目专属特征，否则默认特征匹配率不足会被 pipeline 阻断。
"""
from pathlib import Path

from tools import cli_runner

_TRIGGER_TIMEOUT = 900  # 15 min


def execute_triggers(
    project_name: str,
    use_default_features: bool,
    features_file: str,
    id_col: str,
    target_col: str,
    keep_metadata_cols: list,
    confirmed: bool,
) -> str:
    # features 来源二选一（与 CLI 的 mutually-exclusive group 对齐）
    if bool(use_default_features) == bool(features_file):
        return cli_runner.err(
            "features 来源须二选一：use_default_features=true（仅 GSFC 工商财务主题）"
            " 或 features_file=<项目专属特征 JSON 路径>"
            "（征信/舆情/generic 等非 GSFC 主题必须用 features_file）。\n"
            "模板见 risk_trigger_extraction/examples/features_template_generic.json"
        )
    if features_file and not Path(features_file).exists():
        return cli_runner.err(f"features_file 不存在: {features_file}")

    argv = ["trigger", "--project", project_name]
    if use_default_features:
        argv += ["--use-default-features"]
    else:
        argv += ["--features-file", features_file]
    if id_col:
        argv += ["--id-col", id_col]
    if target_col:
        argv += ["--target-col", target_col]
    if keep_metadata_cols:
        argv += ["--keep-metadata-cols", ",".join(keep_metadata_cols)]
    if confirmed:
        argv += ["--confirmed"]

    job_id = cli_runner.submit_cli_job(
        name=f"extract_triggers:{project_name}",
        argv=argv,
        project_name=project_name,
        timeout=_TRIGGER_TIMEOUT,
    )
    return cli_runner.submitted(
        job_id, project_name,
        f"触碰提取已在后台启动。用 get_job_status(job_id='{job_id}') 查询。\n"
        f"前置要求：① 需先用 run_pipeline 把同名 project={project_name!r} 跑到 Level 1"
        f"（trigger 读其 prepared.csv）；② 未传 confirmed=true 会在【阻断节点 2】停下；"
        f"③ 非 GSFC 主题须用 features_file，否则默认 GSFC 特征匹配率 < 70% 会报错阻断。",
    )
