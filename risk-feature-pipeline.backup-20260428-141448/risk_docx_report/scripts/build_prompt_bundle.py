# -*- coding: utf-8 -*-
import argparse
import json
from pathlib import Path
from typing import List, Optional

from config import DEFAULT_OUTPUT_DIR, DEFAULT_PROMPT_TEMPLATE


def _infer_report_title(llm_json_path: Path) -> str:
    stem = llm_json_path.stem
    for suffix in ("_LLM报告数据", "_llm_report_data", "_report_data"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)] or stem
    return stem


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _build_overview_summary(payload: dict) -> List[str]:
    overview = payload.get("分析概览") or payload.get("overview") or {}
    data_overview = overview.get("数据概况", {})
    segment_overview = overview.get("分群维度", {})
    scope_overview = overview.get("分析范围", {})

    lines = []
    if data_overview:
        total = data_overview.get("总样本数")
        bad = data_overview.get("坏客户数")
        bad_rate = data_overview.get("坏客户率")
        lines.append(f"- 数据概况：总样本数={total}，坏客户数={bad}，坏客户率={bad_rate}")
    if segment_overview:
        dims = segment_overview.get("分群维度列表") or segment_overview.get("类别型维度")
        dim_count = segment_overview.get("分群维度数量") or segment_overview.get("类别型维度数量")
        lines.append(f"- 分群信息：维度数量={dim_count}，维度列表={dims}")
    if scope_overview:
        lines.append(
            "- 分析范围：参与分析分群总数={0}，IV可信率>=50%的分群数={1}".format(
                scope_overview.get("参与分析的分群总数"),
                scope_overview.get("IV可信率>=50%的分群数"),
            )
        )
    return lines


def build_prompt_bundle(
    llm_json_path: Path,
    output_path: Path,
    prompt_template_path: Path,
    report_title: Optional[str] = None,
) -> Path:
    payload = _load_json(llm_json_path)
    prompt_text = prompt_template_path.read_text(encoding="utf-8")
    title = report_title or _infer_report_title(llm_json_path)
    summary_lines = _build_overview_summary(payload)

    bundle = [
        f"# {title} 报告生成任务包",
        "",
        "## 使用说明",
        "",
        "- 请将本文件整体提供给大模型。",
        "- 请让模型直接输出 Markdown 正文，便于后续转换为 `.docx`。",
        "- 正文需严格遵循下方“报告撰写要求”，并以“结构化输入数据”为事实依据。",
        "- 正文内出现的图表编号可保留为占位，如“详见表1”“详见图2”。",
        "",
        "## 结构化输入摘要",
        "",
    ]

    if summary_lines:
        bundle.extend(summary_lines)
    else:
        bundle.append("- 未从 JSON 中解析出标准化概览字段，请直接以完整 JSON 为准。")

    bundle.extend(
        [
            "",
            "## 报告撰写要求",
            "",
            prompt_text.strip(),
            "",
            "## 输出格式要求",
            "",
            "- 仅输出 Markdown 正文，不要输出额外解释。",
            "- 一级、二级、三级标题层级尽量稳定。",
            "- 表格尽量使用标准 Markdown 表格语法。",
            "- 业务建议使用正式公文语体。",
            "",
            "## 结构化输入数据(JSON)",
            "",
            "```json",
            json.dumps(payload, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(bundle), encoding="utf-8")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="将报告提示词与 LLM JSON 打包为报告写作任务文件")
    parser.add_argument("--llm-json", required=True, help="risk_export_report 导出的 LLM JSON 路径")
    parser.add_argument("--output", default=None, help="输出 Markdown 任务包路径")
    parser.add_argument("--prompt-template", default=str(DEFAULT_PROMPT_TEMPLATE), help="报告提示词模板路径")
    parser.add_argument("--title", default=None, help="报告标题，默认从 JSON 文件名推断")
    args = parser.parse_args()

    llm_json_path = Path(args.llm_json).expanduser().resolve()
    prompt_template_path = Path(args.prompt_template).expanduser().resolve()
    title = args.title or _infer_report_title(llm_json_path)

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = DEFAULT_OUTPUT_DIR / f"{title}_报告任务包.md"

    built = build_prompt_bundle(
        llm_json_path=llm_json_path,
        output_path=output_path,
        prompt_template_path=prompt_template_path,
        report_title=title,
    )
    print(f"[OK] 已生成报告任务包: {built}")


if __name__ == "__main__":
    main()
