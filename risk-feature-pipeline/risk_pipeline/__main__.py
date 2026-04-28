# -*- coding: utf-8 -*-
"""支持 `python -m risk_pipeline <subcommand>` 调用统一 CLI。"""
import sys

from .cli import main

sys.exit(main())
