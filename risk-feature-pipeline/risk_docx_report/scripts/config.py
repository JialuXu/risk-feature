# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = SKILL_ROOT.parent  # 用于定位代码同伴文件（report-prompt.md），不是输出根
WORKSPACE_ROOT = PROJECT_ROOT.parent

DEFAULT_PROMPT_TEMPLATE = PROJECT_ROOT / "report-prompt.md"

# docx 校验脚本：兄弟目录 skills/ 是本机开发布局，沙盒/skill 安装模式下不存在，
# 此时用 RISK_DOCX_VALIDATE_SCRIPT 环境变量指定（不存在则跳过校验，只打 WARN）。
DOCX_SKILL_ROOT = WORKSPACE_ROOT / "skills" / "skills" / "docx"
_env_validate = os.environ.get("RISK_DOCX_VALIDATE_SCRIPT")
DOCX_VALIDATE_SCRIPT = (
    Path(_env_validate).expanduser()
    if _env_validate
    else DOCX_SKILL_ROOT / "scripts" / "office" / "validate.py"
)


def __getattr__(name: str) -> Path:
    """PEP 562 lazy 属性：DEFAULT_OUTPUT_DIR 延后到调用时计算，走 paths.get_output_root()。

    旧版直接 `PROJECT_ROOT / "output" / "docx-report"` 在 import 时绑死路径，
    无视 RISK_OUTPUT_ROOT 环境变量；lazy 求值后让 Python API 直调（绕过 CLI）
    时也能尊重 env。CLI 路径（cli_commands.py::cmd_report）显式传 --output
    覆盖该默认，不受影响。
    """
    if name == 'DEFAULT_OUTPUT_DIR':
        # risk_core.paths 需要 risk-feature-pipeline/（= PROJECT_ROOT）在
        # sys.path 上；CLI / pip 安装 / pytest 下天然满足。以裸模块方式直跑脚本时若
        # sys.path 未含该目录则在此兜底加一次。
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from risk_core.paths import get_output_root
        return Path(get_output_root()) / "output" / "docx-report"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

DEFAULT_FEATURE_ROWS = 50
DEFAULT_SEGMENT_ROWS = 30

A4_PAGE_WIDTH = 11906
A4_PAGE_HEIGHT = 16838
DEFAULT_PAGE_MARGIN = 1440
