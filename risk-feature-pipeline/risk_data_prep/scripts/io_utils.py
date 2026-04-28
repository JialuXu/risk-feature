# -*- coding: utf-8 -*-
import os

import pandas as pd

from .config import COL_CUSTOMER_ID


def get_project_root():
    """
    获取项目根目录。

    支持：脚本直接运行、从项目根 cwd 运行、Jupyter 下无 __file__ 时回退 cwd 或向上查找含 data 的目录。
    """
    project_root = None

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.normpath(os.path.dirname(current_dir))
    except NameError:
        project_root = None

    if project_root is None or not os.path.exists(os.path.join(project_root, 'data')):
        cwd = os.getcwd()
        if os.path.exists(os.path.join(cwd, 'data')):
            project_root = cwd
            print("[INFO] 使用当前工作目录作为项目根目录")
        else:
            search_dir = cwd
            for _ in range(5):
                parent = os.path.dirname(search_dir)
                if os.path.exists(os.path.join(parent, 'data')):
                    project_root = parent
                    print("[INFO] 自动检测到项目根目录")
                    break
                if parent == search_dir:
                    break
                search_dir = parent

            if project_root is None:
                project_root = cwd
                print(f"[WARN] 未找到data目录，使用当前工作目录: {cwd}")

    return os.path.normpath(project_root)


def ensure_dir(path):
    """确保目录存在。"""
    if not os.path.exists(path):
        os.makedirs(path)


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
