# -*- coding: utf-8 -*-
"""共享 IO 工具：CSV 自动编码读取 + 按配置批量加载。

各 Skill 的 ``scripts/io_utils.py`` 是从本模块再导出的兼容 shim。
新代码请直接 ``from risk_core.io_utils import read_csv_auto_encoding``。
"""
import os

import pandas as pd

# 编码尝试顺序：优先带 BOM 的 UTF-8，其次中文环境常见编码，最后 latin1 兜底
_ENCODINGS = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'gb18030', 'latin1']


def read_csv_auto_encoding(file_path, **kwargs):
    """自动检测编码读取 CSV 文件。

    Windows 环境下 CSV 可能是 GBK/GB2312 编码，需要自动检测：依次尝试
    ``_ENCODINGS``；非编码类错误（如文件格式问题）直接抛出；全部编码失败时
    用 ``errors='replace'`` 强制读取，保证不抛异常。
    """
    for encoding in _ENCODINGS:
        try:
            return pd.read_csv(file_path, encoding=encoding, **kwargs)
        except UnicodeDecodeError:
            continue
        except Exception as e:
            if 'codec' not in str(e).lower() and 'decode' not in str(e).lower():
                raise e
            continue

    return pd.read_csv(file_path, encoding='utf-8', errors='replace', **kwargs)


def load_data(config, project_root):
    """按配置字典批量加载多张表；缺失路径时对应键值为 ``None``。

    主键列按 ``COL_CUSTOMER_ID`` 以字符串读入，避免被推断成数值丢精度。
    """
    from .config import COL_CUSTOMER_ID

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
