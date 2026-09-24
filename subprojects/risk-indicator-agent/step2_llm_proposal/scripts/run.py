"""Step 2 入口."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from indicator_pipeline.config import AgentConfig
from indicator_pipeline.field_dict import load_default_field_dict
from indicator_pipeline.io_utils import read_json, write_json
from indicator_pipeline.llm_client import BaseLLMClient, build_client
from indicator_pipeline.meta_store import MetaStore
from indicator_pipeline.pipeline import get_step_input_path, get_step_output_path

from .context_builder import build_system_prompt, build_user_prompt
from .llm_call import call_llm_for_proposals
from .post_process import normalize_proposals

logger = logging.getLogger(__name__)


def run(
    batch_id: str,
    cfg: AgentConfig,
    llm_client: BaseLLMClient | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """跑 Step 2.

    llm_client 参数允许测试时注入 MockLLM (避免真实 API 调用).
    """
    seeds_path = get_step_input_path(cfg, batch_id, 2)
    payload = read_json(seeds_path)
    seeds: list[dict[str, Any]] = payload.get("seeds", [])
    logger.info("[step2] 读 seeds: %d 条 from %s", len(seeds), seeds_path)

    if not seeds:
        logger.warning("[step2] seeds 为空, 直接退出")
        result_payload = _make_payload(batch_id, [], 0, {})
        out_path = get_step_output_path(cfg, batch_id, 2)
        write_json(out_path, result_payload)
        return {"step": 2, "batch_id": batch_id, "output": str(out_path),
                "stats": result_payload["stats"]}

    # LLM 客户端
    if llm_client is None:
        llm_client = build_client(cfg.llm)

    # 元表 (用于注入 LLM 上下文)
    meta_store = MetaStore(
        sqlite_path=cfg.abs_path(cfg.paths.meta_sqlite),
        snapshots_dir=cfg.abs_path(cfg.paths.meta_snapshots_dir),
        audit_log=cfg.abs_path(cfg.paths.audit_log),
    )
    existing_active = meta_store.list_active()

    # 字段字典
    fd = load_default_field_dict(cfg.project_root, cfg.abs_path(cfg.paths.references_dir))

    # 按 domain 分桶
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in seeds:
        if s.get("already_registered"):
            continue
        d = s.get("domain", "UNKNOWN")
        if d == "UNKNOWN":
            logger.warning("[step2] seed %s 无明确 domain, 跳过", s.get("feature_name_cn"))
            continue
        by_domain[d].append(s)
    logger.info("[step2] seeds 按 domain 分桶: %s",
                {k: len(v) for k, v in by_domain.items()})

    seed_index = {s["feature_name_cn"]: s for s in seeds if s.get("feature_name_cn")}

    # 准备 system prompt (与 domain 无关,所有调用共享)
    system_prompt = build_system_prompt(cfg)

    batch_size = int(cfg.step2.get("batch_size", 5))
    max_per_batch = int(cfg.step2.get("max_proposals_per_batch", 10))

    proposals_all: list[dict[str, Any]] = []
    failed_batches: list[dict[str, Any]] = []
    llm_call_count = 0
    by_domain_count: dict[str, int] = defaultdict(int)

    for domain, dseeds in by_domain.items():
        for i in range(0, len(dseeds), batch_size):
            batch = dseeds[i:i + batch_size]
            user_prompt = build_user_prompt(
                cfg=cfg,
                domain=domain,
                seeds=batch,
                fd=fd,
                existing_indicators=existing_active,
                max_per_batch=max_per_batch,
            )
            logger.info("[step2] 调 LLM domain=%s 批 %d (size=%d)",
                        domain, i // batch_size + 1, len(batch))
            llm_call_count += 1
            raw_props, err = call_llm_for_proposals(llm_client, system_prompt, user_prompt)
            if err is not None:
                logger.error("[step2] 批失败 domain=%s i=%s: %s", domain, i, err)
                failed_batches.append({
                    "domain": domain,
                    "batch_offset": i,
                    "seed_names": [s.get("feature_name_cn") for s in batch],
                    "error": err,
                })
                continue
            normalized = normalize_proposals(raw_props, cfg, seed_index=seed_index)
            proposals_all.extend(normalized)
            by_domain_count[domain] += len(normalized)

    # 写失败明细 (如有)
    if failed_batches:
        batch_dir = cfg.batch_dir(batch_id)
        write_json(batch_dir / "step2_failed_batches.json", failed_batches)
        logger.warning("[step2] 失败批次 %d 个, 详见 step2_failed_batches.json",
                       len(failed_batches))

    result_payload = _make_payload(batch_id, proposals_all, llm_call_count, dict(by_domain_count))
    out_path = get_step_output_path(cfg, batch_id, 2)
    write_json(out_path, result_payload)
    logger.info("[step2] 输出 proposals_draft.json: %s (proposals=%d, calls=%d, failed_batches=%d)",
                out_path, len(proposals_all), llm_call_count, len(failed_batches))

    return {"step": 2, "batch_id": batch_id, "output": str(out_path),
            "stats": result_payload["stats"], "failed_batches": len(failed_batches)}


def _make_payload(batch_id: str, proposals: list[dict[str, Any]],
                  llm_calls: int, by_domain: dict[str, int]) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "stats": {
            "input_seeds": -1,  # 由 step1 stats 决定,不在这里重算
            "output_proposals": len(proposals),
            "by_domain": by_domain,
            "llm_calls": llm_calls,
        },
        "proposals": proposals,
    }
