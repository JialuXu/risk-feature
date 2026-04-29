# -*- coding: utf-8 -*-
import os

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
    按多种编码尝试读取 CSV（优先 utf-8-sig / utf-8，其次中文环境常用编码）。
    """
    encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'gb18030', 'latin1']

    for encoding in encodings:
        try:
            df = pd.read_csv(file_path, encoding=encoding, **kwargs)
            return df
        except UnicodeDecodeError:
            continue
        except Exception as e:
            if 'codec' not in str(e).lower() and 'decode' not in str(e).lower():
                raise e
            continue

    return pd.read_csv(file_path, encoding='utf-8', errors='replace', **kwargs)


def load_data(config, project_root):
    """按配置字典加载多张表；缺失路径时对应键值为 None。"""
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
