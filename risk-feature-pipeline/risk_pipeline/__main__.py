# -*- coding: utf-8 -*-
"""支持 `python -m risk_pipeline <subcommand>`：转发组合根 risk_mining.cli:main。"""
import sys

from risk_mining.cli import main

sys.exit(main())
