# -*- coding: utf-8 -*-
"""CLI 辅助 I/O：features.json 读写、_intermediate/ 落盘与重建、数据集指纹。

`analyze` 子命令把内存中的 results dict 拆成多张 CSV + manifest.json 落到
`data/processed/{project}/_intermediate/`；`export` 子命令再读回来重建 results dict。
之所以不用 pickle：跨 pandas 版本鲁棒、可被 cat/head 调试、避免不可序列化对象隐患。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd


def utc_now_iso() -> str:
    """返回当前时间的本地时区 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).astimezone().isoformat()


def write_features_json(path, info: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False, indent=2, default=str)


def read_features_json(path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def dataset_fingerprint(path: str) -> dict:
    """返回 {path, sha256_first_1mb, size_bytes}。

    只摘前 1MB 是为了避免大文件阻塞；前 1MB + 文件大小作为指纹足以区分典型变更。
    """
    with open(path, 'rb') as f:
        chunk = f.read(1024 * 1024)
    return {
        'path': str(path),
        'sha256_first_1mb': hashlib.sha256(chunk).hexdigest(),
        'size_bytes': os.path.getsize(path),
    }


def _safe_filename(s: str) -> str:
    """把分群维度名转成可作为文件名的 token（中文保留）。"""
    return re.sub(r'[\\/:\s]+', '_', str(s))


# 简单 DataFrame（长格式或元信息）
_SIMPLE_KEYS = (
    'iv_full',
    'iv_group_all',
    'reliability_summary',
    'feature_set_comparison',
    'corr_long',
    'lr_coef_long',
    'lr_auc_long',
    'comprehensive',
)

# 宽矩阵 dict[dim → DataFrame]
_WIDE_DICT_KEYS = (
    ('corr_wide', 'corr_results'),
    ('lr_coef_wide', 'lr_coef_results'),
    ('lr_auc', 'lr_auc_results'),
    ('meta', 'meta_results'),
)


def dump_intermediate(
    results: dict,
    intermediate_dir: str,
    *,
    project_name: str,
    target_col: str,
    category_dims,
    qual_dims,
    feature_cols,
    raw_features=None,
    derived_features=None,
) -> None:
    """把 run_generic_pipeline 返回的 results 拆成多 CSV + manifest.json。"""
    os.makedirs(intermediate_dir, exist_ok=True)

    # 简单 DataFrame
    for key in _SIMPLE_KEYS:
        df = results.get(key)
        if df is None or not hasattr(df, 'to_csv') or df.empty:
            continue
        df.to_csv(
            os.path.join(intermediate_dir, f'{key}.csv'),
            index=False, encoding='utf-8-sig',
        )

    # 宽矩阵 dict
    for prefix, key in _WIDE_DICT_KEYS:
        wide_dict = results.get(key) or {}
        for dim, wide in wide_dict.items():
            if wide is None or not hasattr(wide, 'to_csv') or wide.empty:
                continue
            wide.to_csv(
                os.path.join(intermediate_dir, f'{prefix}_{_safe_filename(dim)}.csv'),
                encoding='utf-8-sig', index=True,
            )

    manifest = {
        'schema_version': 1,
        'project_name': project_name,
        'target_col': target_col,
        'category_dims': list(category_dims or []),
        'qual_dims': list(qual_dims or []),
        'feature_cols': list(feature_cols or []),
        'raw_features': list(raw_features or []),
        'derived_features': list(derived_features or []),
        'wide_dim_keys': sorted(set([
            d
            for _, k in _WIDE_DICT_KEYS
            for d in (results.get(k) or {}).keys()
        ])),
        'created_at': utc_now_iso(),
    }
    with open(os.path.join(intermediate_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def load_intermediate(intermediate_dir: str) -> Tuple[dict, dict]:
    """从 _intermediate/ 重建 minimal results dict + manifest。"""
    if not os.path.isdir(intermediate_dir):
        raise FileNotFoundError(f'_intermediate/ 目录不存在: {intermediate_dir}')

    manifest_path = os.path.join(intermediate_dir, 'manifest.json')
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(f'manifest.json 不存在: {manifest_path}')

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    results: dict = {
        'project_name': manifest['project_name'],
        'feature_cols': manifest.get('feature_cols', []),
        'raw_features': manifest.get('raw_features', []),
        'derived_features': manifest.get('derived_features', []),
        'category_dims': manifest.get('category_dims', []),
        'qual_dims': manifest.get('qual_dims', []),
    }

    for key in _SIMPLE_KEYS:
        path = os.path.join(intermediate_dir, f'{key}.csv')
        if os.path.exists(path):
            results[key] = pd.read_csv(path, encoding='utf-8-sig')

    wide_dim_keys = manifest.get('wide_dim_keys') or list(manifest.get('category_dims', []))
    if manifest.get('qual_dims') and '资质标签' not in wide_dim_keys:
        wide_dim_keys = wide_dim_keys + ['资质标签']

    for prefix, key in _WIDE_DICT_KEYS:
        wide_dict = {}
        for dim in wide_dim_keys:
            path = os.path.join(intermediate_dir, f'{prefix}_{_safe_filename(dim)}.csv')
            if os.path.exists(path):
                wide_dict[dim] = pd.read_csv(path, encoding='utf-8-sig', index_col=0)
        if wide_dict:
            results[key] = wide_dict

    return results, manifest
