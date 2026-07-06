# -*- coding: utf-8 -*-
"""兼容 shim：统一 CLI 已迁入组合根 ``risk_mining.cli``（解耦重构阶段 2）。

保留旧入口 ``from risk_pipeline import cli`` / ``cli.main(...)``，逐字转发到 risk_mining；
下个版本随 risk_pipeline shim 一并收敛。对 agent 而言命令 `python -m risk_pipeline` 不变。
"""
from risk_mining.cli import (  # noqa: F401  再导出：组合根在 risk_mining.cli
    main,
    _build_parser,
    _make_global_parent,
)


if __name__ == '__main__':
    import sys
    sys.exit(main())
