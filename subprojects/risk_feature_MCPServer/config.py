import os
import sys
from pathlib import Path

# server.py 的绝对位置（无论从哪里启动都稳定）
_SERVER_DIR = Path(__file__).resolve().parent

# 候选路径：优先级从高到低
_CANDIDATES = [
    # 1. 显式环境变量（最优先）
    Path(os.environ["RISK_PIPELINE_ROOT"]) if "RISK_PIPELINE_ROOT" in os.environ else None,
    # 2. 与 risk_feature_MCPServer/ 同级的 risk-feature-pipeline/
    _SERVER_DIR.parent / "risk-feature-pipeline",
    # 3. server.py 所在目录的上两级（容器/虚拟环境内常见布局）
    _SERVER_DIR.parent.parent / "risk-feature-pipeline",
]

PIPELINE_ROOT: Path = next(
    (p for p in _CANDIDATES if p is not None and p.exists()), Path("NOT_FOUND")
)

# 结果扫描路径：只扫 PIPELINE_ROOT。
# setup() 已把 RISK_PROJECT_ROOT/RISK_OUTPUT_ROOT 钉到 PIPELINE_ROOT，链路读写都落在这里，
# 不再有"可能定位到父级"的歧义。曾经为兜底而附带扫描 PIPELINE_ROOT.parent（仓库根），
# 但那里堆着历史 scratch 项目（如 舆情*/征信/财务 等旧实验产物），会被 list_projects 误列出来，
# 让"我只分析了工商变更，却看到舆情"成为困惑来源——故移除父级扫描。
# 若确需访问仓库根下的旧项目，请把 RISK_PIPELINE_ROOT 指到对应根。
RESULT_SEARCH_ROOTS: list[Path] = [
    PIPELINE_ROOT,
]


def get_result_candidate_dirs(project_name: str) -> list[Path]:
    """返回某项目所有可能的结果目录（横跨两个根 × results/output × 可选子分类）。"""
    dirs: list[Path] = []
    for root in RESULT_SEARCH_ROOTS:
        for base in ("data/results", "output"):
            dirs.append(root / base / project_name)
            dirs.append(root / base / "征信" / project_name)
    return dirs


def setup() -> None:
    if PIPELINE_ROOT.name == "NOT_FOUND":
        tried = "\n  ".join(
            str(p) for p in _CANDIDATES if p is not None
        )
        raise RuntimeError(
            f"找不到 risk-feature-pipeline/ 目录，已尝试以下路径：\n  {tried}\n\n"
            f"解决方法：在 claude_desktop_config.json 的 env 中设置：\n"
            f'  "RISK_PIPELINE_ROOT": "/实际路径/risk-feature-pipeline"'
        )
    if str(PIPELINE_ROOT) not in sys.path:
        sys.path.insert(0, str(PIPELINE_ROOT))

    # 显式锁定项目根/输出根，避免 pipeline 退回"从 CWD 向上找 data/"的探测逻辑而漂移
    # （MCP server 的 CWD 往往不是 pipeline 根）。子进程会继承这两个 env，
    # 进程内的 query/list 也据此定位，确保读写落在同一处。
    # 用 setdefault：外部 claude_desktop_config.json 已显式指定时不覆盖。
    os.environ.setdefault("RISK_PROJECT_ROOT", str(PIPELINE_ROOT))
    os.environ.setdefault("RISK_OUTPUT_ROOT", str(PIPELINE_ROOT))
