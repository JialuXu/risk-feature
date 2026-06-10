"""run_pipeline 工具的执行逻辑（异步 job 模式，避免 MCP 调用超时）"""
import contextlib
import json
import sys
from pathlib import Path
from typing import Optional

from config import get_result_candidate_dirs
from tools import job_manager

_VALID_STEPS = {"data_prep", "feature_engineering", "univariate", "iv", "lr", "export"}


def execute_pipeline(
    wide_path: str,
    project_name: str,
    bad_customer_path: Optional[str],
    id_col: str,
    target_col: str,
    category_dims: list,
    steps: list,
    exclude_features: list,
    filter_json: str,
) -> str:
    """前台校验参数 → 后台异步跑链路 → 立即返回 job_id"""
    # ── 阻断节点 1：路径与参数校验（立即返回）──────────────────────────────
    if not Path(wide_path).exists():
        return _err(f"宽表文件不存在: {wide_path}")
    if bad_customer_path and not Path(bad_customer_path).exists():
        return _err(f"坏客户文件不存在: {bad_customer_path}")

    invalid_steps = set(steps) - _VALID_STEPS
    if invalid_steps:
        return _err(f"无效的 steps: {invalid_steps}，合法值: {_VALID_STEPS}")
    if "export" not in steps:
        return _err("steps 必须包含 'export'，否则结果不落盘（达不到 Level 1）")

    filter_config = None
    if filter_json:
        try:
            filter_config = json.loads(filter_json)
        except json.JSONDecodeError as e:
            return _err(f"filter_json 格式无效: {e}")

    # ── 提交异步 job，立即返回 ────────────────────────────────────────────
    job_id = job_manager.submit(
        name=f"run_pipeline:{project_name}",
        func=_run_pipeline_blocking,
        wide_path=wide_path,
        project_name=project_name,
        bad_customer_path=bad_customer_path,
        id_col=id_col,
        target_col=target_col,
        category_dims=category_dims,
        steps=steps,
        exclude_features=exclude_features,
        filter_config=filter_config,
    )

    return json.dumps(
        {
            "status": "submitted",
            "job_id": job_id,
            "project_name": project_name,
            "message": (
                f"链路已在后台启动。使用 get_job_status(job_id='{job_id}') "
                f"查询进度；链路通常需 5-10 分钟完成。"
            ),
        },
        ensure_ascii=False,
        indent=2,
    )


def _run_pipeline_blocking(
    wide_path: str,
    project_name: str,
    bad_customer_path: Optional[str],
    id_col: str,
    target_col: str,
    category_dims: list,
    steps: list,
    exclude_features: list,
    filter_config: Optional[dict],
) -> dict:
    """实际跑链路的阻塞函数，在后台线程里执行"""
    from risk_data_prep.scripts.prepare_df import prepare_df
    from shared.pipeline import run_generic_pipeline

    with contextlib.redirect_stdout(sys.stderr):
        df, feature_cols = prepare_df(
            wide_path=wide_path,
            bad_customer_path=bad_customer_path or None,
            id_col=id_col,
            target_col=target_col,
            filter=filter_config,
            exclude_features=set(exclude_features) if exclude_features else None,
        )

        run_generic_pipeline(
            df=df,
            feature_cols=feature_cols,
            target_col=target_col,
            project_name=project_name,
            category_dims=category_dims,
            qual_dims=[],
            steps=steps,
            verbose=False,
        )

    # 扫描落盘文件
    output_files = []
    for d in get_result_candidate_dirs(project_name):
        if d.exists():
            output_files += [str(f) for f in sorted(d.glob("*.csv"))]
            output_files += [str(f) for f in sorted(d.glob("*.json"))]

    return {
        "project_name": project_name,
        "output_files": output_files,
        "file_count": len(output_files),
    }


def _err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)
