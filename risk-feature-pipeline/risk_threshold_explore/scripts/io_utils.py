# -*- coding: utf-8 -*-
"""pair-list 文件读 + 候选阈值 CSV 写 + _audit.json 节点追加。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, List, Tuple

import pandas as pd

from risk_core.contracts import RESULT_FILE_TEMPLATE


_REQUIRED_COLS = ('分群维度', '分群名称', '特征')


def read_pair_list(path: str) -> List[Tuple[str, str, str]]:
    """读取 pair-list 文件。

    支持：
      - .csv（UTF-8 / UTF-8-sig）：表头必须含 分群维度,分群名称,特征
      - .json：list[dict]，每个 dict 含 分群维度/分群名称/特征 键
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f'pair-list 文件不存在: {path}')

    ext = os.path.splitext(path)[1].lower()
    if ext == '.json':
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(f'pair-list JSON 必须是 list[dict]：{path}')
        pairs = []
        for i, row in enumerate(data):
            if not isinstance(row, dict):
                raise ValueError(f'pair-list JSON 第 {i} 项非 dict: {row!r}')
            missing = [c for c in _REQUIRED_COLS if c not in row]
            if missing:
                raise ValueError(f'pair-list JSON 第 {i} 项缺列 {missing}：{row!r}')
            pairs.append((str(row['分群维度']), str(row['分群名称']), str(row['特征'])))
        return pairs

    if ext != '.csv':
        raise ValueError(f'pair-list 必须是 .csv 或 .json，实际：{path}')

    for enc in ('utf-8-sig', 'utf-8', 'gbk'):
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise UnicodeDecodeError('utf-8/utf-8-sig/gbk', b'', 0, 1, f'无法识别编码：{path}')

    missing = [c for c in _REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f'pair-list CSV 缺列：{missing}；实际表头：{list(df.columns)}\n'
            f'  要求表头：{list(_REQUIRED_COLS)}'
        )
    pairs = [
        (str(r['分群维度']), str(r['分群名称']), str(r['特征']))
        for _, r in df[list(_REQUIRED_COLS)].dropna().iterrows()
    ]
    return pairs


def write_threshold_outputs(
    summary_df: pd.DataFrame,
    detail_df: pd.DataFrame,
    project: str,
    results_dir: str,
) -> dict:
    """写出两张 CSV，返回 {summary_path, detail_path}。空表也写表头占位。"""
    Path(results_dir).mkdir(parents=True, exist_ok=True)
    summary_path = os.path.join(
        results_dir, RESULT_FILE_TEMPLATE.format(project=project, type='候选阈值表'))
    detail_path = os.path.join(
        results_dir, RESULT_FILE_TEMPLATE.format(project=project, type='候选阈值_分箱明细'))

    if summary_df is None:
        summary_df = pd.DataFrame()
    if detail_df is None:
        detail_df = pd.DataFrame()

    summary_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
    detail_df.to_csv(detail_path, index=False, encoding='utf-8-sig')
    return {'summary_path': summary_path, 'detail_path': detail_path}


def append_audit_node(audit_path: str, key: str, payload: Any) -> None:
    """在 audit.json 中覆盖/插入指定 key；其它字段保留。

    若 audit.json 不存在则新建，仅含本 key（不重建 IV 过拟合 / 不稳定规则等节点，
    那些由 export 子命令的 _write_audit_json 负责）。
    """
    Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if os.path.isfile(audit_path):
        try:
            with open(audit_path, 'r', encoding='utf-8') as f:
                data = json.load(f) or {}
        except Exception:
            # audit 损坏时不要静默丢历史；备份后重建
            backup = audit_path + '.broken'
            try:
                os.replace(audit_path, backup)
            except OSError:
                pass
            data = {'_recovered_from_broken_audit': True}

    data[key] = payload
    tmp = audit_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, audit_path)


__all__ = ['read_pair_list', 'write_threshold_outputs', 'append_audit_node']
