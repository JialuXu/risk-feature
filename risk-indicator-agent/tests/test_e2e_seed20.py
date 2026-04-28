"""端到端测试: 5 步走 + MockLLM + 模拟数仓回填.

验证 20 条新种子全部走完进入元表.
"""

from __future__ import annotations

import json
from pathlib import Path

from indicator_pipeline.io_utils import write_json
from indicator_pipeline.pipeline import run_step


def _seed_payload(domain_seeds: dict[str, list[str]]) -> dict:
    """构造一份小型 seeds.json 模拟 step1 输出."""
    seeds = []
    for domain, names in domain_seeds.items():
        for name in names:
            seeds.append({
                "feature_name_cn": name,
                "source_project": "测试项目",
                "domain": domain,
                "iv": 0.30,
                "iv_credibility": "可信",
                "coverage_rate": 0.95,
                "signal_strength": "强",
                "risk_direction": "正向",
                "sample_size_total": 5000,
                "bad_size": 500,
                "already_registered": False,
                "candidate_source": "mining_supplement",
            })
    return {
        "batch_id": "e2e_test",
        "generated_at": "2026-04-28T00:00:00",
        "stats": {"total": len(seeds), "by_domain": {k: len(v) for k, v in domain_seeds.items()}},
        "seeds": seeds,
    }


def _shadow_response(ind_codes: list[str]) -> dict:
    return {
        "batch_id": "e2e_test",
        "responded_at": "2026-04-28T01:00:00",
        "responder": "test_warehouse",
        "data_warehouse_run_id": "run_001",
        "results": [
            {
                "ind_code": code,
                "ind_version": 1,
                "shadow_iv_status": "SUCCESS",
                "shadow_iv": 0.32,
                "shadow_coverage_rate": 0.93,
                "shadow_credibility": "可信",
                "shadow_sample_size": 5000,
                "shadow_risk_direction": "正向",
                "snap_dt": "2026-04-30",
            }
            for code in ind_codes
        ],
    }


def test_e2e_steps_2_through_5(tmp_cfg, mock_llm_with_proposals, tmp_path,
                                 monkeypatch):
    """跳过 step1 (依赖外部 results/), 直接喂 seeds → step 2-5."""
    batch_id = "e2e_test"
    batch_dir = tmp_cfg.batch_dir(batch_id)
    batch_dir.mkdir(parents=True, exist_ok=True)

    # 1) 写 seeds.json (模拟 step 1 输出)
    seeds_payload = _seed_payload({
        "CRDTC": ["担保查询未结清比"],
        "PUB": ["风险标签_信贷逾期_数量"],
    })
    write_json(batch_dir / "seeds.json", seeds_payload)

    # 2) Step 2 - 注入 MockLLM
    r2 = run_step(2, batch_id=batch_id, cfg=tmp_cfg, llm_client=mock_llm_with_proposals)
    assert r2["stats"]["output_proposals"] == 2, f"got {r2}"
    assert (batch_dir / "proposals_draft.json").exists()

    # 3) Step 3 — 6 道关 (LLM 语义关默认关闭, 见 tmp_cfg)
    r3 = run_step(3, batch_id=batch_id, cfg=tmp_cfg, auto_approve=True,
                  skip_semantic_llm=True)
    assert r3["stats"]["validated"] == 2, f"validation report: {r3}"
    assert (batch_dir / "validated.json").exists()

    # 4) Step 4 — 出工单
    r4 = run_step(4, batch_id=batch_id, cfg=tmp_cfg)
    assert r4["indicators"] == 2
    assert (batch_dir / "shadow_iv_request.json").exists()
    assert (batch_dir / "sql_skeletons").is_dir()

    # 5) 模拟数仓回填
    response = _shadow_response([
        "CRDTC_M_GUARQRY_UNPAYOFF_SNAP_RATIO",
        "PUB_M_TAG_OVDUE_M12_CNT",
    ])
    write_json(batch_dir / "shadow_iv_response.json", response)

    # 6) Step 5 — 注册
    r5 = run_step(5, batch_id=batch_id, cfg=tmp_cfg, auto_approve=True)
    assert r5["registration"]["inserted"] == 2, f"reg: {r5}"
    assert r5["registration_errors"] == 0
    assert r5["delivery_files"]["md"]
    assert r5["delivery_files"]["csv"]

    # 7) 验证元表
    from indicator_pipeline.meta_store import MetaStore
    store = MetaStore(
        sqlite_path=tmp_cfg.abs_path(tmp_cfg.paths.meta_sqlite),
        snapshots_dir=tmp_cfg.abs_path(tmp_cfg.paths.meta_snapshots_dir),
        audit_log=tmp_cfg.abs_path(tmp_cfg.paths.audit_log),
    )
    active = store.list_active()
    assert len(active) == 2
    codes = {r["ind_code"] for r in active}
    assert codes == {"CRDTC_M_GUARQRY_UNPAYOFF_SNAP_RATIO", "PUB_M_TAG_OVDUE_M12_CNT"}

    # 8) 验证交付文件
    out_dir = tmp_cfg.abs_path(tmp_cfg.paths.output_dir) / batch_id
    assert (out_dir / "衍生指标设计稿.md").exists()
    assert (out_dir / "衍生指标设计稿.csv").exists()
