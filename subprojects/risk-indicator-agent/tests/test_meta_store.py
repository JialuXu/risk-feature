"""元表 SCD2 写入单测."""

from indicator_pipeline.meta_store import MetaStore


def _make(code: str, name: str, ver: int = 1, **kw):
    base = {
        "ind_code": code,
        "ind_version": ver,
        "ind_name_cn": name,
        "domain": "CRDTC",
        "granularity": "M",
        "window": "SNAP",
        "value_type": "RATIO",
        "biz_definition": "test biz",
        "calc_logic": "test calc",
        "source_tables": ["DT_FAKE"],
        "source_fields": ["DT_FAKE.X"],
        "priority": "P0",
        "lifecycle_status": "ACTIVE",
        "proposer": "LLM_AGENT",
        "owner": "RISK_TEAM",
        "is_dynamic_expansion": 0,
        "ref_date_logic": "SNAP_DT",
        "post_processing_rule": "KEEP_NULL_ON_LEFT_JOIN",
    }
    base.update(kw)
    return base


def test_insert_new(tmp_meta_store):
    rec = _make("CRDTC_M_T1_SNAP_RATIO", "测试1")
    action = tmp_meta_store.write_scd2(rec, batch_id="b1")
    assert action == "inserted"
    assert tmp_meta_store.find("CRDTC_M_T1_SNAP_RATIO") is not None


def test_soft_update_no_business_change(tmp_meta_store):
    """业务字段不变,IV 变化 → 软更新."""
    rec = _make("CRDTC_M_T2_SNAP_RATIO", "测试2", current_iv=0.5)
    tmp_meta_store.write_scd2(rec, batch_id="b1")
    rec2 = _make("CRDTC_M_T2_SNAP_RATIO", "测试2", current_iv=0.6)
    action = tmp_meta_store.write_scd2(rec2, batch_id="b2")
    assert action == "soft_update"
    found = tmp_meta_store.find("CRDTC_M_T2_SNAP_RATIO")
    assert found["ind_version"] == 1
    assert float(found["current_iv"]) == 0.6


def test_new_version_on_business_change(tmp_meta_store):
    """业务字段变 → 新 SCD2 版本."""
    rec = _make("CRDTC_M_T3_SNAP_RATIO", "测试3", calc_logic="A/B")
    tmp_meta_store.write_scd2(rec, batch_id="b1")
    rec2 = _make("CRDTC_M_T3_SNAP_RATIO", "测试3", calc_logic="A/(B+C)")
    action = tmp_meta_store.write_scd2(rec2, batch_id="b2")
    assert action == "new_version"
    # 当前态查询应是新版本
    current = tmp_meta_store.find("CRDTC_M_T3_SNAP_RATIO")
    assert current["ind_version"] == 2
    # 旧版本仍可查
    old = tmp_meta_store.find("CRDTC_M_T3_SNAP_RATIO", version=1)
    assert old is not None
    assert old["ind_version"] == 1


def test_list_active(tmp_meta_store):
    tmp_meta_store.write_scd2(_make("CRDTC_M_A_SNAP_RATIO", "A"), batch_id="b1")
    tmp_meta_store.write_scd2(_make("FIN_M_B_SNAP_RATIO", "B", domain="FIN"),
                             batch_id="b1")
    all_rows = tmp_meta_store.list_active()
    assert len(all_rows) == 2
    crdtc = tmp_meta_store.list_active(domain="CRDTC")
    assert len(crdtc) == 1


def test_deprecate(tmp_meta_store):
    tmp_meta_store.write_scd2(_make("CRDTC_M_D_SNAP_RATIO", "D"), batch_id="b1")
    ok = tmp_meta_store.deprecate("CRDTC_M_D_SNAP_RATIO")
    assert ok
    # 当前态查询返回 None
    assert tmp_meta_store.find("CRDTC_M_D_SNAP_RATIO") is None
    # 列表也不含
    assert not tmp_meta_store.list_active()
