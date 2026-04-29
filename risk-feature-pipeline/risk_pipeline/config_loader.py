# -*- coding: utf-8 -*-
"""
YAML 配置加载器

支持用户仅覆盖需要修改的部分，未覆盖的项自动回退到 default.yaml。
"""
import copy
import os
from pathlib import Path

import yaml


_CONFIG_DIR = Path(__file__).resolve().parent.parent / 'config'
_DEFAULT_CONFIG_PATH = _CONFIG_DIR / 'default.yaml'
_DEFAULT_MAPPING_PATH = _CONFIG_DIR / 'column_mapping.yaml'


def _expand(value):
    """递归对配置中的所有字符串做 ${VAR} 与 ~ 展开。"""
    if isinstance(value, str):
        return os.path.expandvars(os.path.expanduser(value))
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


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
    """读取单个 YAML 文件，并对所有字符串值做环境变量与 ~ 展开。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"配置文件不存在: {p}")
    with open(p, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    return _expand(data)


def load_config(user_config_path=None, *, print_attribution: bool = False):
    """
    加载配置：先读 default.yaml，再用用户配置覆盖。

    参数:
        user_config_path: 用户配置文件路径（可选）。
            如果提供，将与默认配置深度合并，用户值优先。
        print_attribution: 当用户未覆盖某顶层键、回退到 default.yaml 时，
            是否在 stdout 打印命中默认值的键。CLI 入口默认开启此项；
            底层 Python API 默认关闭以兼容历史行为。

    返回:
        config: 合并后的配置字典
    """
    default_config = load_yaml(_DEFAULT_CONFIG_PATH)
    config = default_config

    if user_config_path is not None:
        user_config = load_yaml(user_config_path)
        config = _deep_merge(default_config, user_config)
        if print_attribution:
            user_top_keys = set(user_config.keys()) if isinstance(user_config, dict) else set()
            default_only = sorted(set(default_config.keys()) - user_top_keys)
            if default_only:
                print(f'[配置] 使用 default.yaml 兜底的顶层键: {default_only}')
    elif print_attribution:
        print(f'[配置] 全部使用 default.yaml（路径: {_DEFAULT_CONFIG_PATH}）')

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
