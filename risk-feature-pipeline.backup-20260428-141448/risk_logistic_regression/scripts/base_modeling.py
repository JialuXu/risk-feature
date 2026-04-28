# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler

from .config import MIN_SAMPLES, MIN_BAD_SAMPLES, SAMPLE_THRESHOLDS, COL_TARGET


def eval_lr_roc_auc(model, X_scaled, y, n_samples, n_bad, thresholds=None):
    """
    按 SAMPLE_THRESHOLDS 中 MIN_SAMPLES_CV / MIN_BAD_CV 决定 5 折分层 CV 或训练集 AUC。

    cross_val_score 会克隆 estimator 各折重训；与分群 LR 中 _fit_lr_single 规则一致。
    """
    t = thresholds if thresholds is not None else SAMPLE_THRESHOLDS
    use_cv = n_samples >= t['MIN_SAMPLES_CV'] and n_bad >= t['MIN_BAD_CV']
    if use_cv:
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        try:
            auc_val = float(
                cross_val_score(
                    model, X_scaled, y, cv=cv, scoring='roc_auc'
                ).mean()
            )
            return auc_val, '5折交叉验证'
        except Exception:
            pass
    try:
        y_prob = model.predict_proba(X_scaled)[:, 1]
        auc_val = float(roc_auc_score(y, y_prob))
    except Exception:
        return np.nan, '训练集(计算失败)'
    if use_cv:
        return auc_val, '训练集(CV失败)'
    return auc_val, '训练集(样本不足)'


def fit_logistic_regression(df, feature_cols, group_name='全量'):
    """
    拟合逻辑回归模型

    使用 L2 正则化避免过拟合
    输出标准化系数以便比较不同特征的相对重要性
    AUC 与 lr_by_group 一致：满足 CV 门槛时用 5 折分层 CV，否则训练集并标注 AUC类型
    """
    try:
        df_clean = df[feature_cols + [COL_TARGET]].dropna()

        if len(df_clean) < MIN_SAMPLES:
            return None, None

        if df_clean[COL_TARGET].sum() < MIN_BAD_SAMPLES:
            return None, None

        X = df_clean[feature_cols].values
        y = df_clean[COL_TARGET].values

        # 标准化
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # L2 正则化逻辑回归
        # C=1.0 为默认正则化强度，L2正则化可以处理特征间的多重共线性
        model = LogisticRegression(
            penalty='l2', C=1.0, solver='lbfgs', max_iter=1000, random_state=42
        )
        model.fit(X_scaled, y)

        n_samples = len(df_clean)
        n_bad = int(y.sum())
        auc, auc_type = eval_lr_roc_auc(
            model, X_scaled, y, n_samples, n_bad, SAMPLE_THRESHOLDS
        )

        # 构建系数结果
        coef_dict = {
            '分群': group_name,
            '样本数': n_samples,
            '坏样本数': n_bad,
            'AUC': auc,
            'AUC类型': auc_type,
        }
        for i, feat in enumerate(feature_cols):
            coef_dict[feat] = model.coef_[0][i]

        return coef_dict, auc
    except Exception as e:
        print(f"[WARN] 逻辑回归拟合失败 ({group_name}): {e}")
        return None, None
