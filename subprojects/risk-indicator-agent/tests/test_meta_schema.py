"""schema 校验单测."""

import pytest

from indicator_pipeline.meta_schema import (
    get_field_enum,
    get_meta_schema,
    get_required_fields,
    validate_indicator,
)


@pytest.fixture
def valid_indicator():
    return {
        "ind_code": "CRDTC_M_GUARQRY_UNPAYOFF_SNAP_RATIO",
        "ind_version": 1,
        "ind_name_cn": "担保查询未结清比",
        "domain": "CRDTC",
        "granularity": "M",
        "window": "SNAP",
        "value_type": "RATIO",
        "biz_definition": "担保查询次数与未结清机构数之比",
        "calc_logic": "GUARTOR_CRDTC_QRY_CNT / NULLIF(...)",
        "source_tables": ["DT_SSDP_CORP_CUST_CRDTC_IND_W"],
        "source_fields": ["DT_SSDP_CORP_CUST_CRDTC_IND_W.GUARTOR_CRDTC_QRY_CNT(担保人征信查询次数)"],
        "priority": "P0",
        "lifecycle_status": "DRAFT",
        "proposer": "LLM_AGENT",
        "owner": "RISK_TEAM",
        "eff_dt": "2026-04-28",
        "exp_dt": "9999-12-31",
        "is_dynamic_expansion": 0,
        "ref_date_logic": "SNAP_DT",
        "post_processing_rule": "KEEP_NULL_ON_LEFT_JOIN",
    }


def test_valid(valid_indicator):
    errs = validate_indicator(valid_indicator)
    assert errs == [], f"unexpected errors: {errs}"


def test_missing_required(valid_indicator):
    bad = dict(valid_indicator)
    bad.pop("biz_definition")
    errs = validate_indicator(bad)
    assert errs and any("biz_definition" in e for e in errs)


def test_bad_enum(valid_indicator):
    bad = dict(valid_indicator)
    bad["domain"] = "FAKE_DOMAIN"
    errs = validate_indicator(bad)
    assert errs


def test_required_fields_count():
    fields = get_required_fields()
    assert len(fields) >= 18  # 至少 18 个必填


def test_domain_enum():
    enum = get_field_enum("domain")
    assert enum and "CRDTC" in enum and "FIN" in enum


def test_meta_schema_has_extras():
    s = get_meta_schema()
    assert "domain_prefixes" in s
    assert "default_post_processing" in s
    assert s["default_post_processing"]["FIN"] == "KEEP_NULL_ON_LEFT_JOIN"
    assert s["default_post_processing"]["OPN"] == "PAD_ZERO_ON_LEFT_JOIN"
