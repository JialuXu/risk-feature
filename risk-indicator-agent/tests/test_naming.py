"""命名规范单测."""

from indicator_pipeline.naming import parse_ind_code, suggest_ind_code, validate_ind_code


def test_valid_codes():
    cases = [
        "CRDTC_M_GUARQRY_UNPAYOFF_SNAP_RATIO",
        "OPN_M_CHG_LIFE_LEGALREP_CNT",
        "PUB_M_TAG_OVDUE_M12_CNT",
        "FIN_M_CGB_CRDT_USAGE_SNAP_RATIO",
    ]
    for c in cases:
        ok, errs = validate_ind_code(c)
        assert ok, f"{c} should be valid, errs={errs}"


def test_invalid_codes():
    cases = [
        ("crdtc_m_xxx_cnt", "全小写"),
        ("INVALID_M_X_CNT", "域不在白名单"),
        ("CRDTC_X_GUARQRY_CNT", "粒度不在白名单"),
        ("担保查询未结清比", "中文"),
        ("CRDTC_M_" + "X" * 100, "过长"),
    ]
    for code, desc in cases:
        ok, errs = validate_ind_code(code)
        assert not ok, f"{code} ({desc}) should be invalid"
        assert errs


def test_parse():
    p = parse_ind_code("CRDTC_M_GUARQRY_UNPAYOFF_SNAP_RATIO")
    assert p["domain"] == "CRDTC"
    assert p["granularity"] == "M"
    assert p["stat"] == "RATIO"
    assert p["window"] == "SNAP"


def test_suggest():
    code = suggest_ind_code("FIN", "短期 偿债 压力", "M3", "RATIO")
    assert code.startswith("FIN_M_")
    assert "短期" not in code  # 中文应被剥
    ok, errs = validate_ind_code(code)
    assert ok, errs
