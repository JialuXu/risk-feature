---
name: risk_docx_report
description: 基于 risk_export_report 的 LLM JSON、`report-prompt.md` 与 docx 生成能力产出正式 Word 报告。当用户说"生成 Word 报告"、"出正式报告/交付件"、"导出 .docx"时触发（需已到 Level 1，CLI `report`）。
---

> **何时读我**：只有需要渲染器/docx 校验脚本配置细节时才读本文件；常规出报告走 `python -m risk_pipeline report`（见 `references/cli/report.md`，对外交付先过阻断节点 3）。

# Risk DOCX Report（→ Level 3）

> **这是分析链路的最后一跳（正式交付），agent 走 CLI：**
> `python -m risk_pipeline report --project X --report-markdown 正文.md --purpose internal`
> ⚠️ `--purpose external`（对外交付）**必须加 `--confirmed-final-version`**（阻断节点 3，见 `AGENTS.md` 五）：
> `.docx` 一旦交付，报告与底层数据一致性承诺即成立，此后改 CSV 须同步重出报告。

## 三步工作流

1. **确认 JSON 已导出**：`export` 已产出 `*_LLM报告数据.json` + `*_LLM_分群画像.csv`（Level 1）
2. **写正文**：把 `report-prompt.md` + LLM JSON 喂给大模型，输出 **Markdown 正文**
   - 可选用 `build_prompt_bundle.py` 把"提示词 + 数据"打成一个可直接投喂的 md，免去每次手拼：
     ```bash
     cd risk_docx_report
     python3 scripts/build_prompt_bundle.py --llm-json ../output/<项目>/<项目>_LLM报告数据.json
     ```
3. **渲染**：
   ```bash
   python -m risk_pipeline report --project <项目> \
     --report-markdown <项目>_正式报告.md --purpose internal
   ```
   `report` 内部调 `build_docx_report` → Node 渲染器，保留正文标题/列表/表格，并追加结构化附录（分析概览、特征有效性、分群画像）。默认输出到 `output/docx-report/`。

## 输入契约

- **LLM JSON**：`risk_export_report` 导出的 `*_LLM报告数据.json`（征信/通用/工商财务链路同名），至少含 `分析概览` / `特征有效性汇总` / `分群画像_重点` / `分群画像_简略`
- **模板**：仓库根 `report-prompt.md`（定义章节、写作风格、数据引用与业务建议口径）
- **正文**：推荐由大模型先输出为 Markdown（纯文本会丢标题/表格结构）

## 运行依赖

- 需要 `node` 可执行文件（建议 >= 16）+ `docx` npm 包：`risk_docx_report/node_modules/` 随包分发；缺失时在 `risk_docx_report/` 目录执行 `npm install`。缺 node 会在渲染前抛带提示的 RuntimeError。

## 关于 docx 校验

`build_docx_report` 默认找本机开发布局的兄弟目录 `skills/skills/docx/scripts/office/validate.py` 校验；找不到时**自动跳过并打 `[WARN] 未找到校验脚本`**——属预期行为，不是报错。需要校验时用环境变量 `RISK_DOCX_VALIDATE_SCRIPT=<validate.py 路径>` 指定脚本，或用 `--skip-validate` 显式跳过。

## 操作规则

- 输入 JSON 用 `risk_export_report` 的正式文件，不手拼字段名。
- 正文用 Markdown，避免标题/表格丢失。
- 附录的结构化表仅作"解释性增强"，不替代正文业务分析。
- 征信精简版 JSON：拼 `分群画像_重点` + `分群画像_简略` 作附录来源。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| 提示词打包、Markdown 转 docx、附录生成 | 重算 IV/LR/相关系数（上游） |
| 复用 `report-prompt.md` 与 LLM JSON | 替代用户决定最终报告措辞 |

## 关键文件

`report-prompt.md` · `risk_export_report/SKILL.md` · `scripts/build_prompt_bundle.py` · `scripts/build_docx_report.py` · `scripts/render_docx_report.js`
