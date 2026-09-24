"""配置加载单测: config/local.yaml 叠加 + domain_tables 走配置."""

from pathlib import Path

from indicator_pipeline.config_loader import load
from indicator_pipeline.field_dict import load_default_field_dict
from step2_llm_proposal.scripts.context_builder import render_base_tables_section


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_local_yaml_overlays_default(tmp_path):
    _write(tmp_path / "config" / "default.yaml",
           "upstream:\n  pipeline_root: a\n  results_dirs: []\n"
           "step2:\n  batch_size: 5\n  domain_tables:\n    PUB: [DEMO_X]\n")
    _write(tmp_path / "config" / "local.yaml",
           "upstream:\n  results_dirs: [/r1]\n"
           "step2:\n  domain_tables:\n    PUB: [REAL_Y]\n")
    cfg = load(project_root=tmp_path)
    assert cfg.upstream == {"pipeline_root": "a", "results_dirs": ["/r1"]}
    assert cfg.step2["batch_size"] == 5
    assert cfg.step2["domain_tables"] == {"PUB": ["REAL_Y"]}


def test_no_local_yaml(tmp_path):
    _write(tmp_path / "config" / "default.yaml", "upstream:\n  results_dirs: []\n")
    assert load(project_root=tmp_path).upstream == {"results_dirs": []}


def test_explicit_config_path_ignores_local(tmp_path):
    _write(tmp_path / "config" / "default.yaml", "upstream:\n  results_dirs: []\n")
    _write(tmp_path / "config" / "local.yaml", "upstream:\n  results_dirs: [/r1]\n")
    cfg = load(config_path=tmp_path / "config" / "default.yaml", project_root=tmp_path)
    assert cfg.upstream == {"results_dirs": []}


def test_base_tables_section_uses_configured_tables(project_root, demo_references_dir):
    fd = load_default_field_dict(project_root, demo_references_dir)
    tables = {"PUB": ["DEMO_CORP_PUBLIC_OPINION"], "OPN": ["DEMO_CORP_REG_CHANGE"]}
    pub = render_base_tables_section("PUB", fd, tables)
    assert "DEMO_CORP_PUBLIC_OPINION" in pub and "TAG_NAME" in pub
    # 不在字段清单里的表 → 标缺口
    assert "数仓待补建" in render_base_tables_section("OPN", fd, tables)
    assert render_base_tables_section("FIN", fd, tables) == "(无该域基础表)"
