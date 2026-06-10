"""dedup + sql_static 单测."""

from indicator_pipeline.dedup import check_duplicate, find_top_similar, text_similarity
from indicator_pipeline.sql_static import analyze_calc_logic, has_partition_predicate


def test_text_similarity():
    s1 = text_similarity("担保查询未结清比", "担保查询未结清率")
    assert s1 >= 80
    s2 = text_similarity("担保查询未结清比", "营业利润率")
    assert s2 < 50


def test_find_top_similar():
    pairs = [
        ("CRDTC_M_GUARQRY_UNPAYOFF_SNAP_RATIO", "担保查询未结清比"),
        ("FIN_M_PROFIT_OP_SNAP_RATIO", "营业利润率"),
    ]
    res = find_top_similar("担保查询未结清率", pairs, top_k=2)
    assert res[0][1] == "担保查询未结清比"
    assert res[0][2] >= 80


def test_check_duplicate_hit():
    candidate = {"ind_code": "X", "ind_name_cn": "担保查询未结清率",
                 "biz_definition": "担保查询次数与未结清机构数比"}
    pairs = [("CRDTC_M_GUARQRY_UNPAYOFF_SNAP_RATIO", "担保查询未结清比")]
    r = check_duplicate(candidate, pairs, threshold=70)
    assert r.is_duplicate
    assert r.matched_code == "CRDTC_M_GUARQRY_UNPAYOFF_SNAP_RATIO"


def test_check_duplicate_miss():
    candidate = {"ind_code": "X", "ind_name_cn": "营业收入同比增长",
                 "biz_definition": "营业收入同比增幅"}
    pairs = [("CRDTC_M_GUARQRY_UNPAYOFF_SNAP_RATIO", "担保查询未结清比")]
    r = check_duplicate(candidate, pairs, threshold=85)
    assert not r.is_duplicate


def test_sql_static_parse():
    r = analyze_calc_logic("SUM(CASE WHEN tag_name = '信贷逾期' THEN 1 ELSE 0 END)")
    assert r.parseable
    assert "sum" in [f.lower() for f in r.referenced_functions]


def test_sql_static_forbidden():
    r = analyze_calc_logic("DATEDIFF(CURRENT_DATE(), CHG_DT)")
    assert "current_date" in r.forbidden_used


def test_partition_predicate():
    assert has_partition_predicate("WHERE part_ymd = '20260428'")
    assert not has_partition_predicate("WHERE name = 'foo'")
