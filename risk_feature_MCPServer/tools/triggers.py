"""extract_triggers 工具的执行逻辑（异步 job 模式）"""
import contextlib
import json
import sys
from pathlib import Path
from typing import Optional

from tools import job_manager


def execute_triggers(
    wide_path: str,
    project_name: str,
    bad_customer_path: Optional[str],
    id_col: str,
    target_col: str,
) -> str:
    # ── 阻断节点 2：路径校验 ─────────────────────────────────────────────────
    if not Path(wide_path).exists():
        return _err(f"宽表文件不存在: {wide_path}")
    if bad_customer_path and not Path(bad_customer_path).exists():
        return _err(f"坏客户文件不存在: {bad_customer_path}")

    # ── 提交异步 job ─────────────────────────────────────────────────────────
    job_id = job_manager.submit(
        name=f"extract_triggers:{project_name}",
        func=_extract_triggers_blocking,
        wide_path=wide_path,
        project_name=project_name,
        bad_customer_path=bad_customer_path,
        id_col=id_col,
        target_col=target_col,
    )

    return json.dumps(
        {
            "status": "submitted",
            "job_id": job_id,
            "project_name": project_name,
            "message": (
                f"触碰提取已在后台启动。使用 get_job_status(job_id='{job_id}') 查询进度。"
            ),
        },
        ensure_ascii=False,
        indent=2,
    )


def _extract_triggers_blocking(
    wide_path: str,
    project_name: str,
    bad_customer_path: Optional[str],
    id_col: str,
    target_col: str,
) -> dict:
    from risk_data_prep.scripts.prepare_df import prepare_df
    from risk_trigger_extraction.scripts.trigger_extraction import extract_triggers

    with contextlib.redirect_stdout(sys.stderr):
        df, _ = prepare_df(
            wide_path=wide_path,
            bad_customer_path=bad_customer_path or None,
            id_col=id_col,
            target_col=target_col,
        )

        df_wide, df_long, df_threshold = extract_triggers(
            df=df,
            project_name=project_name,
            target_col=target_col,
            id_col=id_col,
        )

    return {
        "project_name": project_name,
        "customers_total": len(df_wide),
        "trigger_records": len(df_long),
        "features_with_threshold": len(df_threshold),
    }


def _err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)
