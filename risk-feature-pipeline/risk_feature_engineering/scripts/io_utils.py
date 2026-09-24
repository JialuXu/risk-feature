# -*- coding: utf-8 -*-
import numpy as np

# read_csv_auto_encoding / load_data 的真实实现已收敛到 risk_core.io_utils，
# 此处再导出以保留 `from .io_utils import ...` 惯用导入路径。
from risk_core.io_utils import read_csv_auto_encoding, load_data  # noqa: F401


def get_project_root():
    """获取项目根目录（薄壳；真实实现见 risk_core.paths.get_project_root）。"""
    from risk_core.paths import get_project_root as _impl
    return _impl()


def ensure_dir(path):
    """确保目录存在（薄壳；PermissionError 时给出 RISK_OUTPUT_ROOT 提示）。"""
    from risk_core.paths import ensure_writable_dir
    ensure_writable_dir(path)


def safe_divide(numerator, denominator, fill_value=np.nan):
    """
    安全除法：将分母中的 0 视为缺失再除，避免 inf/除零；
    比率为核心特征时与 Winsorize 配合可抑制极端值对 IV 的干扰。
    """
    denom = denominator.replace(0, np.nan)
    result = numerator / denom
    return result.fillna(fill_value) if fill_value is not np.nan else result
