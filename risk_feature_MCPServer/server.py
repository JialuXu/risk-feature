"""
风险特征分析 MCP Server（stdio transport）

启动方式：
    RISK_PIPELINE_ROOT=/path/to/risk-feature-pipeline python server.py

环境变量：
    RISK_PIPELINE_ROOT  链路根目录，默认为同级 ../risk-feature-pipeline/
"""
import config

config.setup()

from mcp.server.fastmcp import FastMCP
from typing import Optional

from tools.pipeline import execute_pipeline
from tools.query import execute_query
from tools.triggers import execute_triggers
from tools.projects import execute_list_projects
from tools.jobs import execute_get_job_status, execute_list_jobs

mcp = FastMCP("risk-feature-pipeline")


@mcp.tool()
def run_pipeline(
    wide_path: str,
    project_name: str,
    bad_customer_path: str = "",
    id_col: str = "客户编号",
    target_col: str = "is_bad",
    category_dims: Optional[list[str]] = None,
    steps: Optional[list[str]] = None,
    exclude_features: Optional[list[str]] = None,
    filter_json: str = "",
) -> str:
    """异步运行风险特征分析链路，立即返回 job_id，后台跑完后产出标准 CSV + LLM JSON。

    链路耗时通常 5-10 分钟，因此采用异步模式避免 MCP 调用超时。
    调用后立即返回 job_id，用 get_job_status(job_id) 查询进度和结果。

    必填参数：
      wide_path      宽表 CSV 的绝对路径
      project_name   项目名，用于输出文件前缀（如"征信特征分析"）

    选填参数：
      bad_customer_path  坏客户清单路径；宽表已含 is_bad 列时可省略
      id_col             主键列名（默认"客户编号"）
      target_col         目标列名（默认"is_bad"）
      category_dims      分群维度列名列表（如 ["企业规模", "所属行业"]）
      steps              分析步骤列表，必须含 "export"；
                         可选值：univariate / iv / lr / export（默认全选）
      exclude_features   需排除的特征列名列表
      filter_json        过滤条件 JSON 字符串，例如：
                         '{"企业规模": {"exclude": ["0"]}}'

    返回：{"status": "submitted", "job_id": "...", "message": "..."}

    注意：首次运行新数据集前请确认 id_col / target_col / 坏客户定义正确（阻断节点 1）。
    """
    return execute_pipeline(
        wide_path=wide_path,
        project_name=project_name,
        bad_customer_path=bad_customer_path or None,
        id_col=id_col,
        target_col=target_col,
        category_dims=category_dims or [],
        steps=steps or ["univariate", "iv", "lr", "export"],
        exclude_features=exclude_features or [],
        filter_json=filter_json,
    )


@mcp.tool()
def query_results(
    project_name: str,
    kind: str,
    n: int = 15,
    dim: str = "",
    group: str = "",
    sign: str = "",
) -> str:
    """查询已有分析结果（不重跑链路），返回 top-N 特征。

    必填参数：
      project_name  项目名（与 run_pipeline 时一致）
      kind          结果类型：iv / lr / corr

    选填参数：
      n      返回条数（默认 15）
      dim    分群维度名（如"企业规模"），不填则返回全量结果
      group  分群值（如"小型企业"），与 dim 配合使用
      sign   LR 系数方向过滤：positive / negative（仅 kind=lr 有效）

    若结果文件不存在会提示先运行 run_pipeline。
    """
    return execute_query(
        project_name=project_name,
        kind=kind,
        n=n,
        dim=dim or None,
        group=group or None,
        sign=sign or None,
    )


@mcp.tool()
def extract_triggers(
    wide_path: str,
    project_name: str,
    bad_customer_path: str = "",
    id_col: str = "客户编号",
    target_col: str = "is_bad",
) -> str:
    """异步把风险结论落到每个客户，立即返回 job_id。

    必填参数：
      wide_path     宽表 CSV 路径（需已完成特征工程）
      project_name  项目名，用于输出文件前缀

    选填参数：
      bad_customer_path  坏客户清单路径；宽表已含 is_bad 列时可省略
      id_col             主键列名（默认"客户编号"）
      target_col         目标列名（默认"is_bad"）

    返回：{"status": "submitted", "job_id": "...", "message": "..."}

    注意：本工具使用 RISK_FEATURES 默认特征配置；
    如需自定义特征集，请直接调用 Python API 并传入 features= 参数（阻断节点 2）。
    """
    return execute_triggers(
        wide_path=wide_path,
        project_name=project_name,
        bad_customer_path=bad_customer_path or None,
        id_col=id_col,
        target_col=target_col,
    )


@mcp.tool()
def list_projects() -> str:
    """列出当前结果目录下所有已有分析项目，便于确认项目名后再调用 query_results。"""
    return execute_list_projects()


@mcp.tool()
def get_job_status(job_id: str) -> str:
    """查询异步 job 的运行状态和结果。

    参数：
      job_id  由 run_pipeline / extract_triggers 返回的 job_id

    返回：{"status": "running|success|error", "result": {...}, "error": "..."}
    """
    return execute_get_job_status(job_id=job_id)


@mcp.tool()
def list_jobs(limit: int = 20) -> str:
    """列出最近提交的 job（按启动时间倒序），便于找回忘记记录的 job_id。"""
    return execute_list_jobs(limit=limit)


if __name__ == "__main__":
    mcp.run()  # 默认 stdio transport
