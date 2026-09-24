# -*- coding: utf-8 -*-
"""子命令共享的 helper：路径派生、退出、确认校验、静默/verbose、状态目录、配置预检。

供 commands/ 下各子命令 import；路径统一经 `risk_core.paths` 解析。
"""
from __future__ import annotations

import os
import sys
from typing import Optional


# ===== 路径 helpers =====
#
# 所有 prepare/analyze 中间产物（prepared.csv / features.json / _intermediate/）
# 都通过 _project_processed_dir 派生；该函数走 paths.get_output_root()，让
# RISK_OUTPUT_ROOT 在 prepare/analyze/export 各阶段一致生效。未设 env 时
# get_output_root() 回退到 get_project_root()。

def _project_processed_dir(project: str) -> str:
    from risk_core.paths import get_output_root
    return os.path.join(get_output_root(), 'data', 'processed', project)


def _intermediate_dir(project: str) -> str:
    return os.path.join(_project_processed_dir(project), '_intermediate')


def _prepared_csv_path(project: str) -> str:
    return os.path.join(_project_processed_dir(project), 'prepared.csv')


def _features_json_path(project: str) -> str:
    return os.path.join(_project_processed_dir(project), 'features.json')


def _id_col_from_features(project: str) -> Optional[str]:
    """从 features.json 取主键列名（§5.1 读契约：read_prepared 需要它锁 str dtype）。

    features.json 缺失/损坏时返回 None → read_prepared 退化普通读，不阻断只读路径。
    """
    path = _features_json_path(project)
    if os.path.isfile(path):
        try:
            from risk_core.contracts import read_features_json
            return read_features_json(path).get('id_col')
        except Exception:  # noqa: BLE001
            return None
    return None


def _project_root() -> str:
    """读源数据用（data/raw/...）；遵循 RISK_PROJECT_ROOT。"""
    from risk_core.paths import get_project_root
    return get_project_root()


def _output_root() -> str:
    """写产物 / 读产物链路用（data/processed, data/results, output）；
    遵循 RISK_OUTPUT_ROOT，未设时回退到 get_project_root。"""
    from risk_core.paths import get_output_root
    return get_output_root()


def _err(msg: str, exit_code: int = 1):
    print(msg, file=sys.stderr)
    sys.exit(exit_code)


def _validate_split_confirmation(args) -> Optional[bool]:
    """C15: 校验拆分版确认 flag。

    Returns:
        True  — 三项全填且都与 args.id_col / args.target_col 一致 → 视为确认通过
        None  — 三项全空 → 未启用拆分版（调用方应回退到 --confirmed-new-dataset）
    Raises:
        SystemExit — 部分填或值不匹配
    """
    cid = getattr(args, 'confirmed_id_col', None)
    ctc = getattr(args, 'confirmed_target_col', None)
    ctp = getattr(args, 'confirmed_target_positive', None)
    provided = [v for v in (cid, ctc, ctp) if v is not None]
    if not provided:
        return None
    if len(provided) < 3:
        _err(
            '[阻断节点 1 / 拆分版] --confirmed-id-col / --confirmed-target-col / '
            '--confirmed-target-positive 必须三项一起传，部分填会让确认动作残缺。\n'
            '  当前已填: '
            f'id_col={cid!r}, target_col={ctc!r}, target_positive={ctp!r}'
        )
    mismatches = []
    if cid != args.id_col:
        mismatches.append(f"--confirmed-id-col={cid!r} 与 --id-col={args.id_col!r} 不一致")
    if ctc != args.target_col:
        mismatches.append(f"--confirmed-target-col={ctc!r} 与 --target-col={args.target_col!r} 不一致")
    if mismatches:
        _err(
            '[阻断节点 1 / 拆分版] 拆分确认值与主参数不匹配（怀疑手抖打错）：\n  - '
            + '\n  - '.join(mismatches)
        )
    return True


def _is_quiet(args) -> bool:
    return bool(getattr(args, 'quiet', False))


def _is_verbose(args) -> bool:
    return bool(getattr(args, 'verbose', False))


def _state_dir(args) -> Optional[str]:
    return getattr(args, 'state_dir', None)


def _print_stamp(stamp: str, args):
    if not _is_quiet(args):
        print(stamp)


# ===== 配置预检（Phase A） =====

def _preflight_column_mapping(df, mapper) -> dict:
    """检查 column_mapping.yaml 期望的列在实际宽表中存在多少。

    返回 audit dict（会被写入 features.json），含三组列的 expected/actual/missing/hit_rate：
      - segment_dims        通用 5 个分群维度（所属行业/客户性质/企业规模/控股类型/所属分行）
      - credit_category_dims 征信 8 个分群维度
      - amount_cols          金额清洗目标列（credit/gsfc 链路用）

    审计本身不阻断 — 阻断决策在 cmd_prepare 里根据 hit_rate 做。
    """
    df_cols = set(df.columns)
    groups = {
        'segment_dims': mapper.segment_dims,
        'credit_category_dims': mapper.credit_category_dims,
        'amount_cols': mapper.amount_cols,
    }
    audit = {}
    for name, expected in groups.items():
        expected = list(expected or [])
        actual = [c for c in expected if c in df_cols]
        audit[name] = {
            'expected': expected,
            'actual': actual,
            'missing': [c for c in expected if c not in df_cols],
            'hit_rate': (len(actual) / len(expected)) if expected else 1.0,
        }
    return audit
