---
name: risk_docx_report
description: 基于 risk_export_report 的 LLM JSON、`report-prompt.md` 与 docx 生成能力产出正式 Word 报告。用户要把最终分析结果整理成 `.docx` 交付件时使用。
---

# Risk DOCX Report

## Overview

`risk_docx_report` 是 `risk-feature-pipeline` 的报告交付型子 Skill。

它位于整个分析链路的最后一跳，专门处理以下任务：

- 接收 `risk_export_report` 已导出的 LLM 三层结构化产物
- 复用仓库根目录的 `report-prompt.md` 作为正式报告写作约束
- 把最终 LLM 正文与结构化分析结果一起整理为 `.docx`

## 何时使用

在以下场景优先使用本 Skill：

- 已经拿到 `*_LLM报告数据.json`，准备生成正式 Word 报告
- 用户要求把风险特征分析结果转成银行可交付的 `.docx`
- 用户希望将 LLM 正文、核心发现、特征有效性汇总、分群画像一起沉淀为报告
- 用户要将 `report-prompt.md` 与结构化 JSON 打包，喂给大模型继续撰写正式报告

不适合直接使用本 Skill 的场景：

- 还没有完成 `risk_export_report` 的 JSON/CSV 导出
- 只想看 CSV 或 JSON，不需要 Word 报告
- 只改 IV/LR/分群分析逻辑，不涉及交付件生成

## 输入契约

本 Skill 默认围绕以下三类输入工作：

1. `risk_export_report` 导出的 LLM 结果
   - 征信/通用管线常见为 `*_LLM报告数据.json`
   - 工商财务管线常见为 `*_LLM报告数据.json`
   - 结构上至少包含：
     - `分析概览`
     - `特征有效性汇总`
     - `分群画像` 或 `分群画像_重点` / `分群画像_简略`

2. 报告写作模板
   - 默认使用仓库根目录 `report-prompt.md`
   - 该提示词定义了报告章节、写作风格、数据引用要求和业务建议口径

3. 最终正文
   - 推荐由大模型先输出为 Markdown
   - 该 Markdown 再由本 Skill 渲染为 `.docx`

## 输出契约

本 Skill 产出以下内容：

- 报告提示词打包文件：便于将 `report-prompt.md` 与 JSON 一起提交给大模型
- `.docx` 正式报告：包含封面、目录、正文、附录表
- 可选校验结果：调用 `skills/skills/docx/scripts/office/validate.py`

默认建议输出到：

- `output/docx-report/`

## 核心脚本

> **路径约定**：`<pipeline_root>` = 上级 `risk-feature-pipeline/` 目录（`SKILL.md` 所在位置）。数据文件路径为相对于该目录的建议位置。

### 1. 打包写作输入

将 `report-prompt.md` 与 LLM JSON 组合为一个可直接投喂大模型的 Markdown 文件：

```bash
cd “<pipeline_root>/risk_docx_report”
python3 scripts/build_prompt_bundle.py \
  --llm-json ../output/<项目名>/<某项目>_LLM报告数据.json
```

用途：

- 固化”提示词 + 数据”的组合输入
- 降低后续每次手工拼提示词的成本
- 让报告撰写链路可复现

### 2. 生成 Word 报告

先准备一份由大模型输出的 Markdown 正文，再调用以下脚本：

```bash
cd “<pipeline_root>/risk_docx_report”
python3 scripts/build_docx_report.py \
  --llm-json ../output/<项目名>/<某项目>_LLM报告数据.json \
  --report-markdown ../output/<项目名>/<某项目>_正式报告.md \
  --output ../output/docx-report/<某项目>_正式报告.docx
```

该脚本内部会：

- 调用本 Skill 的 Node 渲染器生成 `.docx`
- 优先保留 Markdown 正文的标题、列表、表格结构
- 追加结构化附录（分析概览、特征有效性、分群画像）

## 推荐工作流（三步）

1. **确认 JSON 已导出**：`risk_export_report` 已产出 `*_LLM报告数据.json` + `*_LLM_分群画像.csv`
2. **打包写作上下文**：运行 `build_prompt_bundle.py`，合并 `report-prompt.md` + LLM JSON，喂给大模型输出 Markdown 正文
3. **渲染**：运行 `build_docx_report.py`，自动生成封面/目录/正文/附录

## 职责边界

| 负责 | 不负责 |
|------|--------|
| 提示词打包、Markdown 转 docx、附录生成、docx 校验串联 | 重新计算 IV/LR/相关系数 |
| 复用 `report-prompt.md` 与 `risk_export_report` 的 LLM JSON | 替代上游导出逻辑 |
| 生成正式 Word 交付件 | 替代用户决定最终报告措辞 |

## 操作规则

- 输入 JSON 优先使用 `risk_export_report` 导出的正式文件，不要手工拼字段名。
- 正文优先使用 Markdown，而不是纯文本，避免标题和表格结构丢失。
- `.docx` 渲染完成后，优先执行校验脚本；若校验失败，再回看 Markdown 表格或节点结构。
- 附录中的结构化表仅作为“解释性增强”，不替代正文中的业务分析。
- 若 JSON 为征信导出精简版，优先拼接 `分群画像_重点` 与 `分群画像_简略` 作为附录来源。

## 关键文件

- `report-prompt.md`
- `risk_export_report/SKILL.md`
- `risk_docx_report/scripts/build_prompt_bundle.py`
- `risk_docx_report/scripts/build_docx_report.py`
- `risk_docx_report/scripts/render_docx_report.js`

## Success Criteria

如果本 Skill 被正确使用，最终应满足：

- 有一份可复用的报告任务包
- 有一份结构清晰、适合银行交付的 `.docx`
- Word 报告正文与 LLM 结构化结果保持一致
- 报告附录能增强风险特征挖掘结果的可解释性
