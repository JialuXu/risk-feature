"""
风险特征分析 MCP Server（stdio transport）

设计：除只读查询外，所有重活/有状态的工具都薄壳转发到 `python -m risk_pipeline`
子进程（见 tools/cli_runner.py）。这样自动继承 pipeline CLI 的状态机、三个阻断节点、
_audit.json 与 Level 推进——MCP 与 pipeline 内部实现解耦，CLI 才是稳定契约。

启动方式：
    RISK_PIPELINE_ROOT=/path/to/risk-feature-pipeline python server.py

环境变量：
    RISK_PIPELINE_ROOT  链路根目录，默认为同级 ../risk-feature-pipeline/
                        （setup() 会据此锁定 RISK_PROJECT_ROOT / RISK_OUTPUT_ROOT）
"""
import config

config.setup()

from mcp.server.fastmcp import FastMCP
from typing import Optional

from tools.pipeline import execute_pipeline
from tools.query import execute_query
from tools.triggers import execute_triggers
from tools.visualize import execute_visualize
from tools.explore import execute_explore_thresholds
from tools.report import execute_report
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
    confirmed_new_dataset: bool = False,
) -> str:
    """异步运行风险特征分析链路（prepare→analyze→export，默认含规则挖掘），立即返回 job_id。

    内部转发到 `python -m risk_pipeline run --pipeline generic`，产出标准 CSV +
    LLM JSON + _audit.json，并把项目推进到 Level 1。链路耗时通常 5-10 分钟，故走异步：
    调用后立即返回 job_id，用 get_job_status(job_id) 查询进度和结果。

    必填参数：
      wide_path      宽表 CSV 的绝对路径
      project_name   项目名，用于输出文件前缀（如"征信特征分析"）

    选填参数：
      bad_customer_path  坏客户清单路径；宽表已含 target 列时可省略
      id_col             主键列名（默认"客户编号"）
      target_col         目标列名（默认"is_bad"，1=坏客户）
      category_dims      分群维度列名列表（如 ["企业规模", "所属行业"]）
      steps              analyze 阶段步骤子集，可选值：univariate / iv / lr / rules
                         （默认全跑，含 rules）。无需指定 export——run 自动完成。
      exclude_features   不参与分析的特征列名列表
      filter_json        过滤条件 JSON 字符串，如 '{"企业规模": {"exclude": ["0"]}}'
      confirmed_new_dataset
                         [阻断节点 1] 首次使用新数据集时必须传 true。
                         未传且数据集陌生时，job 会以 error 返回并提示核对
                         id_col / target_col / 坏客户定义是否正确。

    返回：{"status": "submitted", "job_id": "...", "message": "..."}
    """
    return execute_pipeline(
        wide_path=wide_path,
        project_name=project_name,
        bad_customer_path=bad_customer_path or None,
        id_col=id_col,
        target_col=target_col,
        category_dims=category_dims or [],
        steps=steps or [],
        exclude_features=exclude_features or [],
        filter_json=filter_json,
        confirmed_new_dataset=confirmed_new_dataset,
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
      kind          结果类型：iv（全样本 IV）/ iv_group（分群 IV + 可信度）/ lr / corr

    选填参数：
      n      返回条数（默认 15）
      dim    分群维度名（如"企业规模"），对 iv_group/corr/lr 生效；kind=iv 时忽略
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
    project_name: str,
    use_default_features: bool = False,
    features_file: str = "",
    id_col: str = "",
    target_col: str = "",
    keep_metadata_cols: Optional[list[str]] = None,
    confirmed: bool = False,
) -> str:
    """异步把风险结论落到每个客户（触碰名单 + IV 加权得分），立即返回 job_id。

    内部转发到 `python -m risk_pipeline trigger`，作用于该项目的 prepared.csv，
    因此**必须先用 run_pipeline 把同名 project 跑到 Level 1**。

    必填参数：
      project_name  项目名（与 run_pipeline 时一致）

    features 来源（二选一，必须显式指定其一）：
      use_default_features=true  使用 RISK_FEATURES_GSFC 默认特征；**仅适配工商财务(GSFC)主题**
      features_file=<路径>       项目专属特征列表 JSON；征信/舆情/generic 等非 GSFC 主题必须用这个
                                 （模板见 risk_trigger_extraction/examples/features_template_generic.json）

    选填参数：
      id_col / target_col  默认从项目 features.json 读取
      keep_metadata_cols   宽表中要保留的业务列（如 ["企业规模","所属行业"]）；默认全部剔除
      confirmed            [阻断节点 2] 必须传 true 才放行（features 配错会直接污染预警名单）

    返回：{"status": "submitted", "job_id": "...", "message": "..."}
    """
    return execute_triggers(
        project_name=project_name,
        use_default_features=use_default_features,
        features_file=features_file,
        id_col=id_col,
        target_col=target_col,
        keep_metadata_cols=keep_metadata_cols or [],
        confirmed=confirmed,
    )


@mcp.tool()
def visualize(
    project_name: str,
    kinds: Optional[list[str]] = None,
    dim: str = "",
    top: int = 15,
    dpi: int = 300,
) -> str:
    """异步生成图表（Level 1 后只读出图），立即返回 job_id。输出 output/<project>/charts/*.png。

    必填参数：
      project_name  项目名（需已到 Level 1）

    选填参数：
      kinds  图表类型列表，可选：iv / iv_heatmap / corr_heatmap / lr_heatmap /
             auc / segment / rules / combos / thresholds（默认全部；缺对应 CSV 的会自动跳过）
      dim    限定单一分群维度（对 corr_heatmap/lr_heatmap/auc 生效）
      top    top-N 条形图截断（默认 15）
      dpi    图片分辨率（默认 300）

    返回：{"status": "submitted", "job_id": "...", "message": "..."}
    """
    return execute_visualize(
        project_name=project_name,
        kinds=kinds or [],
        dim=dim or None,
        top=top,
        dpi=dpi,
    )


@mcp.tool()
def explore_thresholds(
    project_name: str,
    pairs_file: str,
    target_col: str = "",
    min_risk_ratio: Optional[float] = None,
    max_p: Optional[float] = None,
    min_bad_high: Optional[int] = None,
    alert_rate_min: Optional[float] = None,
    alert_rate_max: Optional[float] = None,
    min_iv: Optional[float] = None,
    min_bin_size: Optional[float] = None,
) -> str:
    """异步候选规则阈值探索（Level 1 后；optbinning 最优切点 + 五道门槛业务判定），立即返回 job_id。

    必填参数：
      project_name  项目名（需已到 Level 1）
      pairs_file    人工 pair-list 文件路径（.csv/.json：列 分群维度,分群名称,特征）

    选填参数（门槛，留空用默认值）：
      target_col       默认从项目 features.json 读取
      min_risk_ratio   风险倍数下限（默认 2.0）
      max_p            卡方 p 值上限（默认 0.05）
      min_bad_high     高风险侧坏客户数下限（默认 10）
      alert_rate_min   触警率下限（默认 0.01）
      alert_rate_max   触警率上限（默认 0.30）
      min_iv           参考 IV 下限（默认 0.02）
      min_bin_size     optbinning 最小箱占比（默认 0.05）

    返回：{"status": "submitted", "job_id": "...", "message": "..."}
    """
    return execute_explore_thresholds(
        project_name=project_name,
        pairs_file=pairs_file,
        target_col=target_col or None,
        min_risk_ratio=min_risk_ratio,
        max_p=max_p,
        min_bad_high=min_bad_high,
        alert_rate_min=alert_rate_min,
        alert_rate_max=alert_rate_max,
        min_iv=min_iv,
        min_bin_size=min_bin_size,
    )


@mcp.tool()
def report(
    project_name: str,
    report_markdown: str,
    purpose: str,
    llm_json: str = "",
    output: str = "",
    appendix_mode: str = "",
    confirmed_final_version: bool = False,
) -> str:
    """异步生成正式 Word 报告（LLM JSON + 人工 Markdown 正文 → .docx，→ Level 3），立即返回 job_id。

    必填参数：
      project_name     项目名（需已到 Level 1；LLM JSON 由 run_pipeline 的 export 产出）
      report_markdown  LLM 生成的 Markdown 正文文件路径
      purpose          internal（内部审阅）/ external（对外交付）

    选填参数：
      llm_json                 默认 output/{project}/{project}_LLM报告数据.json
      output                   默认 output/{project}/{project}.docx
      appendix_mode            both / feature / segment / none / compact（默认 both）
      confirmed_final_version  [阻断节点 3] purpose=external 时必须传 true，
                               否则 job 以 error 返回（防终版报告与数据脱钩）

    返回：{"status": "submitted", "job_id": "...", "message": "..."}
    """
    return execute_report(
        project_name=project_name,
        report_markdown=report_markdown,
        purpose=purpose,
        llm_json=llm_json or None,
        output=output or None,
        appendix_mode=appendix_mode or None,
        confirmed_final_version=confirmed_final_version,
    )


@mcp.tool()
def list_projects() -> str:
    """列出当前结果目录下所有已有分析项目，便于确认项目名后再调用 query_results。"""
    return execute_list_projects()


@mcp.tool()
def get_job_status(job_id: str) -> str:
    """查询异步 job 的运行状态和结果。

    参数：
      job_id  由 run_pipeline / extract_triggers / visualize / explore_thresholds / report 返回的 job_id

    返回：{"status": "running|success|error", "result": {...}, "error": "..."}
    error 时 error 字段含 CLI 的 stderr（如阻断节点提示）。
    """
    return execute_get_job_status(job_id=job_id)


@mcp.tool()
def list_jobs(limit: int = 20) -> str:
    """列出最近提交的 job（按启动时间倒序），便于找回忘记记录的 job_id。"""
    return execute_list_jobs(limit=limit)


if __name__ == "__main__":
    mcp.run()  # 默认 stdio transport
