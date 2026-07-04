# -*- coding: utf-8 -*-
"""CLI 辅助 I/O 的再导出 shim。

解耦重构（DECOUPLING-DESIGN §5 / §7 file map，阶段 1）：features.json 读写、
_intermediate/ wire 落盘与重建、数据集指纹等磁盘契约的实现已升入
``risk_core.contracts`` 作为单一真源。本模块保留原导入路径
（``from risk_pipeline.cli_io import ...`` / ``cli_io.X``）向后兼容，
逐字转发到 contracts；下个版本随挖掘内核迁移一并收敛。
"""
from risk_core.contracts import (  # noqa: F401  再导出：契约单一真源在 risk_core.contracts
    now_iso,
    write_features_json,
    read_features_json,
    dataset_fingerprint,
    dump_intermediate,
    load_intermediate,
    _safe_filename,
    _SIMPLE_KEYS,
    _WIDE_DICT_KEYS,
    _FP_HEAD_BYTES,
    _FP_TAIL_BYTES,
)
