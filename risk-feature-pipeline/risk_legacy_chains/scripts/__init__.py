# -*- coding: utf-8 -*-
"""risk_legacy_chains 对外 API：run_credit_pipeline / run_gsfc_pipeline。"""
from .credit_chain import run_credit_pipeline  # noqa: F401
from .gsfc_chain import run_gsfc_pipeline  # noqa: F401

__all__ = ['run_credit_pipeline', 'run_gsfc_pipeline']
