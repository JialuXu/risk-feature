"""run_pipeline 工具：薄壳 → `python -m risk_pipeline run --pipeline generic`（异步 job）。

走 CLI 子进程而非直调 run_generic_pipeline，以继承：
  - 阻断节点 1（首次新数据集需 confirmed_new_dataset，核对 id_col/target_col）
  - 状态机 Level 推进（export → Level 1）与 .pipeline_state.json 数据集指纹
  - prepare→analyze→export 真实流程（含 rules 决策树挖掘）
  - _audit.json 机器可读自检
详见 tools/cli_runner.py。
"""
import json
from pathlib import Path

from tools import cli_runner

# generic 链路 analyze 阶段合法步骤（与 CLI VALID_STEPS_GENERIC + rules 对齐）。
# 注意：data_prep/feature_engineering 不是 generic 步骤；export 由 run 自动完成，无需指定。
_VALID_STEPS = {"univariate", "iv", "lr", "rules"}
_PIPELINE_TIMEOUT = 1800  # 30 min


def execute_pipeline(
    wide_path: str,
    project_name: str,
    bad_customer_path,
    id_col: str,
    target_col: str,
    category_dims: list,
    steps: list,
    exclude_features: list,
    filter_json: str,
    confirmed_new_dataset: bool,
) -> str:
    # ── 前台快速校验（立即返回友好错误，不进 job）─────────────────────────────
    if not Path(wide_path).exists():
        return cli_runner.err(f"宽表文件不存在: {wide_path}")
    if bad_customer_path and not Path(bad_customer_path).exists():
        return cli_runner.err(f"坏客户文件不存在: {bad_customer_path}")

    steps = steps or []
    if "export" in steps:
        return cli_runner.err(
            "无需指定 'export'：run 一键完成 prepare→analyze→export。"
            f"generic 的 steps 仅用于 analyze 阶段，合法值: {sorted(_VALID_STEPS)}"
        )
    invalid = set(steps) - _VALID_STEPS
    if invalid:
        return cli_runner.err(
            f"无效的 steps: {sorted(invalid)}；generic 合法值: {sorted(_VALID_STEPS)}"
        )

    filter_config = None
    if filter_json:
        try:
            filter_config = json.loads(filter_json)
        except json.JSONDecodeError as e:
            return cli_runner.err(f"filter_json 格式无效: {e}")

    # ── 构造 CLI argv ────────────────────────────────────────────────────────
    argv = [
        "run", "--pipeline", "generic",
        "--wide", wide_path,
        "--project", project_name,
        "--id-col", id_col,
        "--target-col", target_col,
    ]
    tmp_paths: list = []
    if bad_customer_path:
        argv += ["--bad-customer", bad_customer_path]
    if category_dims:
        argv += ["--category-dims", ",".join(category_dims)]
    if steps:
        argv += ["--steps", ",".join(steps)]
    if filter_config is not None:
        p = cli_runner.write_temp_json(filter_config)
        tmp_paths.append(p)
        argv += ["--filter-file", p]
    if exclude_features:
        p = cli_runner.write_temp_json(list(exclude_features))
        tmp_paths.append(p)
        argv += ["--exclude-features-file", p]
    if confirmed_new_dataset:
        argv += ["--confirmed-new-dataset"]

    job_id = cli_runner.submit_cli_job(
        name=f"run_pipeline:{project_name}",
        argv=argv,
        project_name=project_name,
        timeout=_PIPELINE_TIMEOUT,
        tmp_paths=tmp_paths,
    )
    return cli_runner.submitted(
        job_id, project_name,
        f"链路已在后台启动（prepare→analyze→export，默认含 rules 规则挖掘）。"
        f"用 get_job_status(job_id='{job_id}') 查询进度；通常需 5-10 分钟。\n"
        f"注意：若为首次使用的新数据集且未传 confirmed_new_dataset=true，"
        f"CLI 会在【阻断节点 1】停下，job 状态为 error 并提示核对 "
        f"id_col={id_col!r} / target_col={target_col!r}；核对无误后重新调用并传 "
        f"confirmed_new_dataset=true。",
    )
