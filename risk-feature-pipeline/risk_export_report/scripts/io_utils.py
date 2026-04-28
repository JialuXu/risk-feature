# -*- coding: utf-8 -*-
import os
import sys

import pandas as pd


def get_project_root():
    """
    获取项目根目录

    支持多种运行方式：
    1. 直接运行脚本：从脚本所在目录向上一级
    2. 从项目根目录运行：使用当前工作目录
    3. Jupyter/IPython环境：使用当前工作目录
    """
    project_root = None

    # 方式1：尝试从 __file__ 获取（标准Python脚本运行）
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        project_root = os.path.normpath(project_root)
    except NameError:
        # __file__ 不存在（Jupyter/IPython环境）
        project_root = None

    # 方式2：验证项目结构，如果不正确则使用当前工作目录
    if project_root is None or not os.path.exists(os.path.join(project_root, 'data')):
        cwd = os.getcwd()
        if os.path.exists(os.path.join(cwd, 'data')):
            project_root = cwd
            print("[INFO] 使用当前工作目录作为项目根目录")
        else:
            # 尝试向上查找包含data目录的父目录
            search_dir = cwd
            for _ in range(5):  # 最多向上查找5级
                parent = os.path.dirname(search_dir)
                if os.path.exists(os.path.join(parent, 'data')):
                    project_root = parent
                    print("[INFO] 自动检测到项目根目录")
                    break
                if parent == search_dir:  # 已到根目录
                    break
                search_dir = parent

            # 如果仍未找到，使用当前工作目录
            if project_root is None:
                project_root = cwd
                print(f"[WARN] 未找到data目录，使用当前工作目录: {cwd}")

    return os.path.normpath(project_root)


def ensure_dir(path):
    """确保目录存在"""
    if not os.path.exists(path):
        os.makedirs(path)


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


def _clean_id(series):
    """清洗主键：转字符串、去 .0、去前后空格"""
    return series.astype(str).str.replace('.0', '', regex=False).str.strip()

def safe_divide(numerator, denominator, fill_value=0.0):
    """安全除法，处理分母为0或NaN的情况"""
    import numpy as np
    import pandas as pd
    return np.where(
        (denominator == 0) | pd.isna(denominator),
        fill_value,
        numerator / denominator
    )
