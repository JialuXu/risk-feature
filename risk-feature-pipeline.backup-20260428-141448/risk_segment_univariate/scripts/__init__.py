"""Skill-local Python modules：分群与单变量分析公开接口。"""
from .segment_univariate import (
    cross_group_variance,
    detect_dims,
    qualification_stats,
    segment_stats,
    univariate_by_group,
    univariate_by_qualification,
)

__all__ = [
    'cross_group_variance',
    'detect_dims',
    'qualification_stats',
    'segment_stats',
    'univariate_by_group',
    'univariate_by_qualification',
]
