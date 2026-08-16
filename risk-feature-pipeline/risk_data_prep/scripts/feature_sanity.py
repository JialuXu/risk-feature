# -*- coding: utf-8 -*-
"""特征入池前的通用卫生闸（feature sanity gate）。

背景：上游宽表偶发 one-hot 展开事故——用字段「取值」而非「字段名+取值」拼列名，
产生形如「<资质前缀><纯是否词>」的语义残缺哑变量（如前缀 `是_` + 取值 `非`），
且往往与正名列完全互补：二元特征取反后 IV 完全相同、相关系数正负镜像，
进 LR 后完全共线导致系数符号失真。

设计约束（防对单一事故过拟合）：
- 不硬编码任何具体业务列名黑名单；
- 列名闸只依赖 column_mapping.yaml 的资质前缀约定 + 通用「纯是/否词」判定，
  换行方（如前缀改 `标签_`）自动跟随；
- 取值闸只看数学关系（二值特征完全相同/互补），且刻意**只作用于二值特征**：
  连续特征的完全相关（如单位换算列）不自动剔除，避免小样本误伤；
- 两道闸都只清理 feature_cols（特征入池清单），不动 df 本身；
  每条剔除显式记原因（编码规范：跳过必须显式记原因）。
"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd

# 资质前缀之后若仅剩这些「不含资质语义」的词，则列名残缺（含 one-hot 展开 NaN 的产物）
_SEMANTIC_FREE_SUFFIXES = {'是', '否', '非', '无', '', 'nan', 'none', 'null'}


def find_degenerate_qual_names(feature_cols, qual_prefix=None) -> Dict[str, str]:
    """列名闸：资质前缀之后不含任何资质语义（仅剩纯是/否词或为空）的列。

    参数:
        feature_cols: 候选特征列名列表
        qual_prefix: 资质标签列前缀；默认读 column_mapping.yaml 的
                     qualification.prefix（即 ColumnMapper().qual_prefix）

    返回:
        {列名: 剔除原因}
    """
    if qual_prefix is None:
        from risk_core.column_mapper import ColumnMapper
        qual_prefix = ColumnMapper().qual_prefix
    out = {}
    for c in feature_cols:
        if not c.startswith(qual_prefix):
            continue
        suffix = c[len(qual_prefix):].strip()
        if suffix.lower() in _SEMANTIC_FREE_SUFFIXES:
            out[c] = (
                f"资质前缀 {qual_prefix!r} 之后仅剩 {suffix!r}，列名不含资质语义"
                f"（疑似上游 one-hot 用取值而非字段名拼列名）"
            )
    return out


def find_redundant_binary_features(df: pd.DataFrame, feature_cols) -> Dict[str, str]:
    """取值闸：与列序更靠前的二值特征完全相同或完全互补（x = 1 - y）的列。

    互补哑变量对的 IV 完全相同、相关系数正负镜像，同入 LR 会完全共线、
    系数符号不可靠，因此只保留列序靠前的一个。仅比较二值(0/1)特征。

    返回:
        {列名: 剔除原因}
    """
    # 二值列判定：非空取值 ⊆ {0, 1} 且至少有一个非空值
    binary: List[str] = [
        c for c in feature_cols
        if df[c].notna().any() and df[c].dropna().isin([0, 1]).all()
    ]
    # 统一成 float 比较，规避 int/float dtype 差异（Series.equals 对 dtype 敏感）
    as_float = {c: df[c].astype('float64') for c in binary}
    out: Dict[str, str] = {}
    kept: List[str] = []
    for c in binary:
        s = as_float[c]
        dup_of, how = None, None
        for k in kept:
            if s.equals(as_float[k]):
                dup_of, how = k, '完全相同'
                break
            if s.equals(1.0 - as_float[k]):
                dup_of, how = k, '完全互补（x = 1 - y）'
                break
        if dup_of is None:
            kept.append(c)
        else:
            out[c] = (
                f"与二值特征 {dup_of!r} {how}，信息完全重复"
                f"（互补哑变量 IV 相同、同入 LR 完全共线）"
            )
    return out
