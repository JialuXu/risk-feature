# -*- coding: utf-8 -*-
"""验证 group_logistic_regression shim 在 gsfc 的 _load_module 取法下与引擎完全一致。

gsfc 链路没有合成测试数据（读真实文件），无法走 golden；这里用 pipeline.py 同款的
_switch_skill/_load_module 动态导入机制，把 shim 当作 `scripts.group_logistic_regression`
载入，再与直接从引擎调用对比，确保去重未改变 gsfc 的 LR 行为。
"""
import importlib
import sys
from pathlib import Path

import pandas.testing as pdt

ROOT = str(Path(__file__).resolve().parent.parent)


def _load_via_load_module(skill, module):
    """复刻旧 risk_pipeline/pipeline.py 的 _switch_skill + _load_module（现 risk_legacy_chains 仍用）。"""
    for k in [k for k in list(sys.modules) if k == 'scripts' or k.startswith('scripts.')]:
        del sys.modules[k]
    skill_dir = str(Path(ROOT) / skill)
    if skill_dir in sys.path:
        sys.path.remove(skill_dir)
    sys.path.insert(0, skill_dir)
    return importlib.import_module(f'scripts.{module}')


def test_gsfc_lr_path_shim_equals_engine(synthetic_dataframe):
    df = synthetic_dataframe
    feats = [c for c in df.columns if c.startswith('feat_')]

    saved_path = list(sys.path)
    saved_mods = {k: v for k, v in sys.modules.items()
                  if k == 'scripts' or k.startswith('scripts.')}
    try:
        # gsfc 链路真实取法：经 _load_module 拿到 shim 的 lr_by_group
        mod_lr = _load_via_load_module(
            'risk_logistic_regression', 'group_logistic_regression')
        coef_shim, auc_shim, skip_shim = mod_lr.lr_by_group(df, '企业规模', feats)
    finally:
        # 清理动态导入污染，避免影响其它用例
        for k in [k for k in list(sys.modules)
                  if k == 'scripts' or k.startswith('scripts.')]:
            del sys.modules[k]
        sys.modules.update(saved_mods)
        sys.path[:] = saved_path

    # 直接从引擎调用同一函数
    from risk_iv_diagnosis.scripts.iv_group_diagnosis import lr_by_group as engine_lr
    coef_eng, auc_eng, skip_eng = engine_lr(df, '企业规模', feats)

    pdt.assert_frame_equal(coef_shim, coef_eng)
    pdt.assert_frame_equal(auc_shim, auc_eng)
    assert skip_shim == skip_eng


def test_shim_reexports_lr_surface():
    import risk_logistic_regression.scripts.group_logistic_regression as m
    for name in ('lr_by_group', 'lr_by_qualification', '_fit_lr_single'):
        assert hasattr(m, name), f'shim 缺少再导出: {name}'
