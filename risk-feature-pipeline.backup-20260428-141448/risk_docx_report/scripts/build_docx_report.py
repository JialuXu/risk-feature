# -*- coding: utf-8 -*-
import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from config import (
    DEFAULT_FEATURE_ROWS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SEGMENT_ROWS,
    DOCX_VALIDATE_SCRIPT,
)


def _infer_output_path(report_markdown: Path, output: Optional[str]) -> Path:
    if output:
        return Path(output).expanduser().resolve()
    return (DEFAULT_OUTPUT_DIR / f"{report_markdown.stem}.docx").resolve()


def _run_command(cmd: List[str], label: str):
    print(f"[INFO] {label}: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def build_docx_report(
    llm_json: Path,
    report_markdown: Path,
    output_path: Path,
    title: Optional[str] = None,
    appendix_mode: str = "both",
    max_feature_rows: int = DEFAULT_FEATURE_ROWS,
    max_segment_rows: int = DEFAULT_SEGMENT_ROWS,
    skip_validate: bool = False,
) -> Path:
    script_dir = Path(__file__).resolve().parent
    renderer_path = script_dir / "render_docx_report.js"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "node",
        str(renderer_path),
        "--llm-json",
        str(llm_json),
        "--report-markdown",
        str(report_markdown),
        "--output",
        str(output_path),
        "--appendix-mode",
        appendix_mode,
        "--max-feature-rows",
        str(max_feature_rows),
        "--max-segment-rows",
        str(max_segment_rows),
    ]
    if title:
        cmd.extend(["--title", title])

    _run_command(cmd, "开始渲染 docx")

    if not skip_validate and DOCX_VALIDATE_SCRIPT.exists():
        _run_command(
            [sys.executable, str(DOCX_VALIDATE_SCRIPT), str(output_path)],
            "执行 docx 校验",
        )
    elif not skip_validate:
        print(f"[WARN] 未找到校验脚本，跳过校验: {DOCX_VALIDATE_SCRIPT}")

    print(f"[OK] 报告已生成: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="将最终 Markdown 报告与 LLM JSON 渲染为 docx")
    parser.add_argument("--llm-json", required=True, help="risk_export_report 导出的 LLM JSON")
    parser.add_argument("--report-markdown", required=True, help="最终报告 Markdown 路径")
    parser.add_argument("--output", default=None, help="输出 docx 路径")
    parser.add_argument("--title", default=None, help="文档标题")
    parser.add_argument(
        "--appendix-mode",
        choices=["both", "feature", "segment", "none"],
        default="both",
        help="附录类型",
    )
    parser.add_argument("--max-feature-rows", type=int, default=DEFAULT_FEATURE_ROWS, help="附录中保留的特征行数")
    parser.add_argument("--max-segment-rows", type=int, default=DEFAULT_SEGMENT_ROWS, help="附录中保留的分群行数")
    parser.add_argument("--skip-validate", action="store_true", help="跳过 docx 校验")
    args = parser.parse_args()

    llm_json = Path(args.llm_json).expanduser().resolve()
    report_markdown = Path(args.report_markdown).expanduser().resolve()
    output_path = _infer_output_path(report_markdown, args.output)

    build_docx_report(
        llm_json=llm_json,
        report_markdown=report_markdown,
        output_path=output_path,
        title=args.title,
        appendix_mode=args.appendix_mode,
        max_feature_rows=args.max_feature_rows,
        max_segment_rows=args.max_segment_rows,
        skip_validate=args.skip_validate,
    )


if __name__ == "__main__":
    main()
