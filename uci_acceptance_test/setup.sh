#!/usr/bin/env bash
# setup.sh — 一次性准备测试环境（venv + 环境变量）
# 用法：source ./setup.sh
#
# 跑完后当前 shell 会有 $PIPELINE_ROOT 和 $PY 两个变量，
# 后续所有命令都用 `PYTHONPATH=$PIPELINE_ROOT $PY -m risk_pipeline ...`

set -e

VENV_DIR="${VENV_DIR:-/tmp/risk_venv}"

# 1) 建 venv（如果不存在）
if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "[setup] 建 venv: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -q pandas numpy scikit-learn statsmodels pyyaml
    echo "[setup] 依赖安装完成"
else
    echo "[setup] venv 已存在: $VENV_DIR"
fi

# 2) 导出环境变量到当前 shell（必须 source 此脚本才生效）
export PIPELINE_ROOT="${PIPELINE_ROOT:-<仓库根>/risk-feature-pipeline}"
export PY="$VENV_DIR/bin/python"

if [ ! -d "$PIPELINE_ROOT/risk_pipeline" ]; then
    echo "[setup] 警告：$PIPELINE_ROOT/risk_pipeline 不存在，请确认 PIPELINE_ROOT 路径"
fi

echo "[setup] PIPELINE_ROOT=$PIPELINE_ROOT"
echo "[setup] PY=$PY"
echo ""
echo "下一步：cd $(pwd) && 按 README.md 顺序跑命令"
