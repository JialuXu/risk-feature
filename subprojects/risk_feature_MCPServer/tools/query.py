"""query_results 工具的执行逻辑"""
import json
from typing import Optional

# 与 results_loader.top_features 支持的四类对齐；iv_group = 带可信度的分群 IV
_VALID_KINDS = {"iv", "iv_group", "lr", "corr"}


def execute_query(
    project_name: str,
    kind: str,
    n: int,
    dim: Optional[str],
    group: Optional[str],
    sign: Optional[str],
) -> str:
    if kind not in _VALID_KINDS:
        return _err(f"kind 必须是 {_VALID_KINDS} 之一，收到: '{kind}'")

    try:
        from risk_result_query.scripts.results_loader import load_results, top_features
    except ImportError as e:
        return _err(f"无法导入查询模块: {e}")

    try:
        r = load_results(project_name)
    except FileNotFoundError:
        return _err(
            f"项目 '{project_name}' 的结果文件不存在，请先调用 run_pipeline 生成结果"
        )

    kwargs: dict = {"kind": kind, "n": n}
    if dim:
        kwargs["dim"] = dim
    if group:
        kwargs["group"] = group
    if sign:
        kwargs["sign"] = sign

    try:
        result_df = top_features(r, **kwargs)
        records = result_df.head(n).to_dict(orient="records")
    except Exception as e:
        return _err(str(e))

    return json.dumps(
        {
            "status": "success",
            "project_name": project_name,
            "kind": kind,
            "dim": dim or "全量",
            "group": group or "全量",
            "results": records,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)
