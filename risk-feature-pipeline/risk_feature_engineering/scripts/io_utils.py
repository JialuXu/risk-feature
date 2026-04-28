# -*- coding: utf-8 -*-
import os

import numpy as np
import pandas as pd

from .config import COL_CUSTOMER_ID


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
