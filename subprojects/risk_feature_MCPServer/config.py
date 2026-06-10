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

# 结果扫描路径：链路的 get_project_root() 可能定位到 PIPELINE_ROOT 或其父级
# 两处都扫描，避免漏检
RESULT_SEARCH_ROOTS: list[Path] = [
    PIPELINE_ROOT,
    PIPELINE_ROOT.parent,
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
