"""字段字典单测."""

from indicator_pipeline.field_dict import load_default_field_dict


def test_load(project_root, demo_references_dir):
    fd = load_default_field_dict(project_root, demo_references_dir)
    assert len(fd.fields) > 0
    assert len(fd.list_tables()) > 0


def test_field_exists(project_root, demo_references_dir):
    fd = load_default_field_dict(project_root, demo_references_dir)
    # 已知存在的字段
    assert fd.field_exists("DEMO_CORP_PUBLIC_OPINION", "TAG_NAME")
    # 不存在的
    assert not fd.field_exists("DEMO_CORP_PUBLIC_OPINION", "FAKE_COLUMN")


def test_fuzzy_search_cn(project_root, demo_references_dir):
    fd = load_default_field_dict(project_root, demo_references_dir)
    matches = fd.fuzzy_search_by_cn("担保人征信查询")
    names = [m.field_cn for m, _ in matches]
    assert "担保人征信查询次数" in names


def test_find_in_table(project_root, demo_references_dir):
    fd = load_default_field_dict(project_root, demo_references_dir)
    fields = fd.find_in_table("DEMO_CORP_PUBLIC_OPINION")
    assert len(fields) > 5
    cn_names = {f.field_cn for f in fields}
    assert "风险标签" in cn_names
    assert "舆情信号等级" in cn_names
