"""Step 5 评审包: 注册前给人审看一遍最终列表."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def render_review_md(
    batch_id: str,
    proposals: list[dict[str, Any]],
    shadow_response_present: bool,
) -> str:
    """渲染 step5_review.md."""
    L = []
    W = L.append
    W(f"# Step 5 注册评审包 · batch={batch_id}")
    W("")
    W(f"生成时间: {datetime.now().isoformat(timespec='seconds')}")
    W(f"shadow IV 数仓回填: {'✓ 已就绪' if shadow_response_present else '✗ 未就绪 (将以 PENDING 状态注册)'}")
    W("")

    # 概览
    by_domain: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_shadow_status: dict[str, int] = {}
    for p in proposals:
        by_domain[p.get("domain", "?")] = by_domain.get(p.get("domain", "?"), 0) + 1
        by_priority[p.get("priority", "?")] = by_priority.get(p.get("priority", "?"), 0) + 1
        s = p.get("shadow_iv_status", "NOT_PROCESSED")
        by_shadow_status[s] = by_shadow_status.get(s, 0) + 1

    W(f"## 注册总数: **{len(proposals)}**")
    W("")
    W("### 按 domain")
    W("")
    for k, v in by_domain.items():
        W(f"- {k}: {v}")
    W("")
    W("### 按 priority (注册后)")
    W("")
    for k, v in by_priority.items():
        W(f"- {k}: {v}")
    W("")
    W("### 按 shadow IV 状态")
    W("")
    for k, v in by_shadow_status.items():
        W(f"- {k}: {v}")
    W("")

    # 逐条简表
    W("## 逐条提案 (即将写入元表)")
    W("")
    W("| ind_code | 中文名 | domain | priority | current_iv | shadow_status |")
    W("|---|---|---|---|---|---|")
    for p in proposals:
        W(f"| `{p.get('ind_code', '')}` | {p.get('ind_name_cn', '')} | "
          f"{p.get('domain', '')} | {p.get('priority', '')} | "
          f"{p.get('current_iv', '-')} | {p.get('shadow_iv_status', '-')} |")
    W("")

    # 审批操作
    W("## 审批操作")
    W("")
    W("```bash")
    W(f"# 通过 (写入元表):")
    W(f"touch data/processed/{batch_id}/STEP5_APPROVED")
    W("")
    W(f"# 拒绝 (流水线退出):")
    W(f"touch data/processed/{batch_id}/STEP5_REJECTED")
    W("```")
    W("")
    W("如需修改注册集,直接编辑 `validated_with_shadow.json` 后再 STEP5_APPROVED.")

    return "\n".join(L)
