# -*- coding: utf-8 -*-
"""
YAML 配置加载器

支持用户仅覆盖需要修改的部分，未覆盖的项自动回退到 default.yaml。
"""
import copy
from pathlib import Path

import yaml


_CONFIG_DIR = Path(__file__).resolve().parent.parent / 'config'
_DEFAULT_CONFIG_PATH = _CONFIG_DIR / 'default.yaml'
_DEFAULT_MAPPING_PATH = _CONFIG_DIR / 'column_mapping.yaml'


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并两个字典，override 优先"""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_yaml(path):
    """读取单个 YAML 文件"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"配置文件不存在: {p}")
    with open(p, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def load_config(user_config_path=None):
    """
    加载配置：先读 default.yaml，再用用户配置覆盖。

    参数:
        user_config_path: 用户配置文件路径（可选）。
            如果提供，将与默认配置深度合并，用户值优先。

    返回:
        config: 合并后的配置字典
    """
    config = load_yaml(_DEFAULT_CONFIG_PATH)

    if user_config_path is not None:
        user_config = load_yaml(user_config_path)
        config = _deep_merge(config, user_config)

    return config


def load_column_mapping(user_config_path=None):
    """
    加载字段映射配置：先读 column_mapping.yaml，再用用户配置覆盖。

    参数:
        user_config_path: 用户配置文件路径（可选）。
            可以是一个独立的字段映射 YAML，
            也可以是一个包含 column_mapping 键的完整配置文件。

    返回:
        mapping: 合并后的字段映射字典
    """
    mapping = load_yaml(_DEFAULT_MAPPING_PATH)

    if user_config_path is not None:
        user_data = load_yaml(user_config_path)
        # 支持两种格式：
        # 1. 独立映射文件（顶层就是 required/segment_dims 等）
        # 2. 完整配置文件中的 column_mapping 键
        if 'column_mapping' in user_data:
            user_data = user_data['column_mapping']
        mapping = _deep_merge(mapping, user_data)

    return mapping


def get_config_dir():
    """返回 config/ 目录的绝对路径"""
    return _CONFIG_DIR
