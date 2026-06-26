"""把 MCP server 根注入 sys.path，并锁定 RISK_PIPELINE_ROOT，供测试 import config / tools.*。"""
import os
import sys
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[1]          # risk_feature_MCPServer/
_PIPELINE_ROOT = _SERVER_ROOT.parent.parent / "risk-feature-pipeline"

if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

# 显式指定链路根，避免不同测试机的 CWD 探测差异（config 模块 import 时即据此定位）
if _PIPELINE_ROOT.exists():
    os.environ.setdefault("RISK_PIPELINE_ROOT", str(_PIPELINE_ROOT))
