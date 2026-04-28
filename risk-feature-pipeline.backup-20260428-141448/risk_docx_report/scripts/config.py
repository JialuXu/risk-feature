# -*- coding: utf-8 -*-
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = SKILL_ROOT.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent

DEFAULT_PROMPT_TEMPLATE = PROJECT_ROOT / "report-prompt.md"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "docx-report"

DOCX_SKILL_ROOT = WORKSPACE_ROOT / "skills" / "skills" / "docx"
DOCX_VALIDATE_SCRIPT = DOCX_SKILL_ROOT / "scripts" / "office" / "validate.py"

DEFAULT_FEATURE_ROWS = 50
DEFAULT_SEGMENT_ROWS = 30

A4_PAGE_WIDTH = 11906
A4_PAGE_HEIGHT = 16838
DEFAULT_PAGE_MARGIN = 1440
