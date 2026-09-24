"""Step 1 入口."""

from __future__ import annotations

import logging
from typing import Any

from indicator_pipeline.config import AgentConfig
from indicator_pipeline.io_utils import write_json
from indicator_pipeline.meta_store import MetaStore
from indicator_pipeline.pipeline import get_step_output_path

from .apply_filters import add_coverage_rate, filter_iv, risk_direction_from_lr
from .load_iv_results import aggregate_iv, aggregate_lr
from .seed_builder import assemble_payload, build_seeds

logger = logging.getLogger(__name__)


def run(batch_id: str, cfg: AgentConfig, **_kwargs: Any) -> dict[str, Any]:
    """跑 Step 1.

    依据 cfg.upstream.results_dirs 加载 IV 结果, 过滤后输出 seeds.json.
    """
    results_dirs = [cfg.abs_path(d) for d in cfg.upstream.get("results_dirs") or []]
    if not results_dirs:
        raise RuntimeError("config 中 upstream.results_dirs 为空 (在 config/local.yaml 里填写)")
    pipeline_root = cfg.upstream.get("pipeline_root")
    pipeline_root = cfg.abs_path(pipeline_root) if pipeline_root else None

    logger.info("[step1] 加载 %d 个项目的 IV 结果", len(results_dirs))
    iv_df = aggregate_iv(results_dirs, pipeline_root)
    logger.info("[step1] 原始 IV 行数: %d", len(iv_df))
    if iv_df.empty:
        logger.warning("[step1] IV 结果为空,流水线无法继续")

    # 过滤
    iv_filter_cfg = cfg.step1.get("iv_filter", {})
    iv_filtered = filter_iv(
        iv_df,
        exclude_credibility=iv_filter_cfg.get("exclude_credibility"),
        iv_max=float(iv_filter_cfg.get("iv_max", 2.0)),
    )
    iv_filtered = add_coverage_rate(iv_filtered)
    logger.info("[step1] 过滤后行数: %d", len(iv_filtered))

    # LR 风险方向
    lr_df = aggregate_lr(results_dirs, pipeline_root)
    risk_dirs = risk_direction_from_lr(lr_df)
    logger.info("[step1] LR 风险方向覆盖: %d 个特征", len(risk_dirs))

    # 元表已注册
    meta_store = MetaStore(
        sqlite_path=cfg.abs_path(cfg.paths.meta_sqlite),
        snapshots_dir=cfg.abs_path(cfg.paths.meta_snapshots_dir),
        audit_log=cfg.abs_path(cfg.paths.audit_log),
    )
    existing_ind_names = {
        rec["ind_name_cn"] for rec in meta_store.list_active() if rec.get("ind_name_cn")
    }
    logger.info("[step1] 元表已注册指标: %d 条", len(existing_ind_names))

    # 拼装 seeds
    signal_thresholds = cfg.step1.get("signal_thresholds")
    seeds, stats = build_seeds(iv_filtered, risk_dirs, existing_ind_names,
                               signal_thresholds=signal_thresholds)

    payload = assemble_payload(batch_id, seeds, stats)
    out_path = get_step_output_path(cfg, batch_id, 1)
    write_json(out_path, payload)
    logger.info("[step1] 输出 seeds.json: %s (seeds=%d)", out_path, len(seeds))

    return {"step": 1, "batch_id": batch_id, "output": str(out_path),
            "stats": stats}
