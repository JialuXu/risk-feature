# -*- coding: utf-8 -*-
import os

import numpy as np
import pandas as pd

from .config import COL_CUSTOMER_ID


def get_project_root():
    """获取项目根目录（薄壳；真实实现见 risk_pipeline.paths.get_project_root）。"""
    from risk_pipeline.paths import get_project_root as _impl
    return _impl()


def ensure_dir(path):
    """确保目录存在（薄壳；PermissionError 时给出 RISK_OUTPUT_ROOT 提示）。"""
    from risk_pipeline.paths import ensure_writable_dir
    ensure_writable_dir(path)


def read_csv_auto_encoding(file_path, **kwargs):
    """
    自动检测编码读取CSV文件

    Windows环境下CSV可能是GBK/GB2312编码，需要自动检测
    优先尝试 utf-8-sig（带BOM的UTF-8），然后是 utf-8，最后是 gbk
    """
    encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'gb18030', 'latin1']

    for encoding in encodings:
        try:
            df = pd.read_csv(file_path, encoding=encoding, **kwargs)
            return df
        except UnicodeDecodeError:
            continue
        except Exception as e:
            # 其他错误（如文件格式问题）直接抛出
            if 'codec' not in str(e).lower() and 'decode' not in str(e).lower():
                raise e
            continue

    # 所有编码都失败，使用errors='replace'强制读取
    return pd.read_csv(file_path, encoding='utf-8', errors='replace', **kwargs)


def load_data(config, project_root):
    """加载所有数据文件"""
    data = {}
    for name, rel_path in config.items():
        full_path = os.path.join(project_root, rel_path)
        if os.path.exists(full_path):
            print(f"[INFO] 加载 {name}: {full_path}")
            data[name] = read_csv_auto_encoding(full_path, dtype={COL_CUSTOMER_ID: str})
            print(f"       样本量: {len(data[name])}")
        else:
            print(f"[WARN] 文件不存在: {full_path}")
            data[name] = None
    return data

def clean_id(series):
    """
    统一的主键清洗函数
    去除 '.0' 后缀，去除前后空格，转为字符串
    """
    return series.astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

def safe_divide(numerator, denominator, fill_value=np.nan):
    """
    安全除法：将分母中的 0 视为缺失再除，避免 inf/除零；
    比率为核心特征时与 Winsorize 配合可抑制极端值对 IV 的干扰。
    """
    denom = denominator.replace(0, np.nan)
    result = numerator / denom
    return result.fillna(fill_value) if fill_value is not np.nan else result
