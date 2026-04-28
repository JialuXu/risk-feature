"""组装 LLM 调用的上下文 (system + user)."""

from __future__ import annotations

import json
from typing import Any

from indicator_pipeline.config import AgentConfig
from indicator_pipeline.field_dict import FieldDict
from indicator_pipeline.prompt_loader import load_prompt, render_prompt

# 各域关心的基础表 (传给 LLM 时只列相关的,避免上下文爆炸)
_DOMAIN_TABLES = {
    "FIN": [
        "DEMO_CORP_FINANCIAL",
        "DEMO_CORP_LOAN_LIMIT",
        "DEMO_CORP_BASIC_INFO",
    ],
    "CRDTC": [
        "DEMO_CORP_CREDIT_REPORT",
        "DEMO_CORP_CREDIT_REPORT_EXT",
        "DEMO_CORP_CREDIT_TAG",
    ],
    "OPN": [
        "DEMO_CORP_BASIC_INFO",
        "DEMO_CORP_REG_CHANGE",
        "DEMO_CORP_REG_TAG",
    ],
    "PUB": [
        "DEMO_CORP_PUBLIC_OPINION",
    ],
    "JUDI": [
        "DEMO_CORP_EXECUTION",
        "DEMO_CORP_LAWSUIT",
        "DEMO_CORP_JUDICIAL_AUCTION",
        "DEMO_CORP_BANKRUPTCY",
    ],
}


def render_base_tables_section(domain: str, fd: FieldDict, max_fields_per_table: int = 80) -> str:
    """构造给 LLM 看的基础表字段清单 (按域过滤)."""
    relevant = _DOMAIN_TABLES.get(domain, [])
    blocks: list[str] = []
    for table_en in relevant:
        fields = fd.find_in_table(table_en)
        marker = ""
        if not fields:
            blocks.append(f"### {table_en} ⚠️ 【数仓待补建,本表当前不存在】\n(无字段, 提案时若依赖此表,priority 设为 P0-阻塞)\n")
            continue
        table_cn = fields[0].table_cn if fields else ""
        head = f"### {table_en} ({table_cn})"
        rows = [f"- `{f.field_en}` ({f.field_cn}) [{f.field_type}]"
                for f in fields[:max_fields_per_table]]
        if len(fields) > max_fields_per_table:
            rows.append(f"- ... (略, 共 {len(fields)} 字段)")
        blocks.append(head + "\n" + "\n".join(rows))
    return "\n\n".join(blocks) if blocks else "(无该域基础表)"


def render_existing_indicators_section(
    existing: list[dict[str, Any]],
    domain: str,
    top_n: int = 30,
) -> str:
    """构造已注册指标摘要 (给 LLM 去重参考)."""
    same = [r for r in existing if r.get("domain") == domain]
    if not same:
        return f"(元表 {domain} 域暂无已注册指标)"
    # 按 IV 降序取 top_n
    same.sort(key=lambda r: float(r.get("current_iv") or 0.0), reverse=True)
    rows = []
    for r in same[:top_n]:
        rows.append(
            f"- `{r['ind_code']}` ({r.get('ind_name_cn','')})"
            f" [IV={r.get('current_iv','-')}, priority={r.get('priority','-')}]"
        )
    return "\n".join(rows)


def build_system_prompt(cfg: AgentConfig) -> str:
    """加载 system prompt + 注入 schema 摘要."""
    schema_excerpt = load_prompt("shared_meta_schema_excerpt.md", cfg.project_root)
    template = load_prompt("step2_proposer_system.md", cfg.project_root)
    return render_prompt(template, {"schema_excerpt": schema_excerpt})


def build_user_prompt(
    cfg: AgentConfig,
    domain: str,
    seeds: list[dict[str, Any]],
    fd: FieldDict,
    existing_indicators: list[dict[str, Any]],
    max_per_batch: int,
) -> str:
    """加载 user 模板 + 注入域上下文 / seeds / 表字段 / 已有指标."""
    domain_ctx_filename = cfg.step2["domain_context_files"].get(domain)
    if not domain_ctx_filename:
        domain_ctx = f"(未为域 {domain} 配置专属上下文,使用默认风控建模知识)"
    else:
        domain_ctx = load_prompt(domain_ctx_filename, cfg.project_root)

    seeds_json = json.dumps(seeds, ensure_ascii=False, indent=2)
    base_tables = render_base_tables_section(domain, fd)
    existing_section = render_existing_indicators_section(existing_indicators, domain)

    template = load_prompt("step2_proposer_user_template.md", cfg.project_root)
    return render_prompt(template, {
        "domain_context": domain_ctx,
        "seeds_json": seeds_json,
        "base_tables_section": base_tables,
        "existing_indicators_section": existing_section,
        "max_per_batch": max_per_batch,
    })


__all__ = [
    "build_system_prompt",
    "build_user_prompt",
    "render_base_tables_section",
    "render_existing_indicators_section",
]
