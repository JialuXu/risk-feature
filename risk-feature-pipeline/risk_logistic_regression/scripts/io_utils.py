# -*- coding: utf-8 -*-
import sys
import platform

# read_csv_auto_encoding / load_data 的真实实现已收敛到 risk_pipeline.io_utils，
# 此处再导出以保留 `from .io_utils import ...` 惯用导入路径。
from risk_pipeline.io_utils import read_csv_auto_encoding, load_data  # noqa: F401


# Windows 环境下设置控制台编码为 UTF-8，避免中文输出乱码
# 仅在标准Python环境（非Jupyter/IPython）下执行
def _setup_windows_encoding():
    """设置Windows控制台编码，兼容Jupyter/IPython环境"""
    if platform.system() != 'Windows':
        return

    # 检查是否在Jupyter/IPython环境中
    # IPython的stdout是OutStream对象，没有reconfigure和buffer属性
    try:
        # 检查是否有reconfigure方法（Python 3.7+ 标准流）
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        elif hasattr(sys.stdout, 'buffer'):
            # 低版本Python的兼容处理
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        # 如果都没有（如Jupyter环境），跳过设置，Jupyter本身支持UTF-8
    except Exception:
        # 任何错误都静默忽略，不影响主程序运行
        pass


def get_project_root():
    """获取项目根目录（薄壳；真实实现见 risk_pipeline.paths.get_project_root）。"""
    from risk_pipeline.paths import get_project_root as _impl
    return _impl()


def ensure_dir(path):
    """确保目录存在（薄壳；PermissionError 时给出 RISK_OUTPUT_ROOT 提示）。"""
    from risk_pipeline.paths import ensure_writable_dir
    ensure_writable_dir(path)
