"""CLI: python -m indicator_pipeline --step N --batch-id X."""

from __future__ import annotations

import argparse
import logging
import sys

from .config_loader import load
from .pipeline import run_step


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="risk-indicator-agent 流水线 CLI")
    p.add_argument("--step", type=int, required=True, choices=[1, 2, 3, 4, 5],
                   help="跑哪一步 (1=候选筛选, 2=LLM提案, 3=校验, 4=影子IV工单, 5=注册)")
    p.add_argument("--batch-id", required=True, help="批次 ID, 如 20260428_first")
    p.add_argument("--config", default=None, help="自定义 config yaml 路径")
    p.add_argument("--auto-approve", action="store_true",
                   help="自动跳过人审 (仅测试用)")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG","INFO","WARNING","ERROR"])
    args = p.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    cfg = load(args.config)
    try:
        run_step(args.step, args.batch_id, cfg=cfg, auto_approve=args.auto_approve)
    except Exception as e:
        logging.error("[CLI] step %s 失败: %s", args.step, e, exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
