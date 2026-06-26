"""MCP server 冒烟测试：前台校验 / 工具注册 / env 锁定 / scan 过滤 / 子进程端到端。

绝大多数用例为 hermetic（不依赖外部数据、不起子进程）。
端到端那条在无已有项目 / 无 pandas 时自动跳过。
"""
import json
import os

import pytest


def _status(s):
    return json.loads(s)["status"]


def _tmp_csv(tmp_path):
    p = tmp_path / "w.csv"
    p.write_text("id,is_bad\n1,0\n2,1\n", encoding="utf-8")
    return str(p)


# ── 前台参数校验：即时返回 error JSON，不进子进程 ─────────────────────────────

def test_run_pipeline_rejects_missing_wide():
    from tools.pipeline import execute_pipeline
    s = execute_pipeline("/no/such.csv", "P", None, "id", "is_bad", [], [], [], "", False)
    assert _status(s) == "error"


def test_run_pipeline_rejects_export_step_validation(tmp_path):
    from tools.pipeline import execute_pipeline
    wide = _tmp_csv(tmp_path)
    s = execute_pipeline(wide, "P", None, "id", "is_bad", [], ["export"], [], "", False)
    d = json.loads(s)
    assert d["status"] == "error" and "export" in d["error"]


def test_run_pipeline_rejects_legacy_steps(tmp_path):
    """data_prep/feature_engineering 不再是 generic 合法步骤（H2）。"""
    from tools.pipeline import execute_pipeline
    wide = _tmp_csv(tmp_path)
    s = execute_pipeline(wide, "P", None, "id", "is_bad", [], ["data_prep"], [], "", False)
    assert _status(s) == "error"


def test_run_pipeline_accepts_rules_step(tmp_path, monkeypatch):
    """rules 现在是合法 generic 步骤（H3）；合法入参应进 job（submitted），不报错。

    stub 掉 submit_cli_job，只验证前台校验放行 + 走到提交（不真的起子进程跑链路）。
    """
    from tools import cli_runner
    from tools import pipeline as pipeline_mod
    monkeypatch.setattr(cli_runner, "submit_cli_job", lambda **kw: "fake-job-id")
    wide = _tmp_csv(tmp_path)
    s = pipeline_mod.execute_pipeline(wide, "P", None, "id", "is_bad", [], ["iv", "rules"], [], "", False)
    assert _status(s) == "submitted"


def test_run_pipeline_rejects_bad_filter_json(tmp_path):
    from tools.pipeline import execute_pipeline
    wide = _tmp_csv(tmp_path)
    s = execute_pipeline(wide, "P", None, "id", "is_bad", [], [], [], "{not json", False)
    assert _status(s) == "error"


def test_triggers_requires_exactly_one_feature_source():
    from tools.triggers import execute_triggers
    assert _status(execute_triggers("P", False, "", "", "", [], True)) == "error"   # 都不给
    assert _status(execute_triggers("P", True, "/x.json", "", "", [], True)) == "error"  # 冲突


def test_triggers_missing_features_file():
    from tools.triggers import execute_triggers
    s = execute_triggers("P", False, "/no/such.json", "", "", [], True)
    assert _status(s) == "error"


def test_query_rejects_invalid_kind():
    from tools.query import execute_query
    d = json.loads(execute_query("P", "badkind", 5, None, None, None))
    assert d["status"] == "error" and "kind" in d["error"]


def test_query_accepts_iv_group(tmp_path):
    """H4：iv_group 必须通过 kind 门；项目不存在 → 报缺文件而非 kind 错。"""
    from tools.query import execute_query
    d = json.loads(execute_query("__definitely_nope__", "iv_group", 5, None, None, None))
    assert d["status"] == "error"
    assert "kind" not in d["error"]


def test_report_rejects_invalid_purpose(tmp_path):
    from tools.report import execute_report
    md = tmp_path / "r.md"
    md.write_text("# x", encoding="utf-8")
    s = execute_report("P", str(md), "wrong", "", "", "", False)
    assert _status(s) == "error"


def test_explore_requires_pairs_file():
    from tools.explore import execute_explore_thresholds
    s = execute_explore_thresholds("P", "", None, None, None, None, None, None, None, None)
    assert _status(s) == "error"


def test_visualize_rejects_invalid_kind():
    from tools.visualize import execute_visualize
    s = execute_visualize("P", ["nope"], None, 15, 300)
    assert _status(s) == "error"


# ── config 锁定 env（M4）─────────────────────────────────────────────────────

def test_setup_locks_env(monkeypatch):
    import config
    monkeypatch.delenv("RISK_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("RISK_OUTPUT_ROOT", raising=False)
    config.setup()
    assert os.environ.get("RISK_PROJECT_ROOT") == str(config.PIPELINE_ROOT)
    assert os.environ.get("RISK_OUTPUT_ROOT") == str(config.PIPELINE_ROOT)


# ── scan_outputs 过滤点文件 ──────────────────────────────────────────────────

def test_scan_outputs_filters_dotfiles(tmp_path, monkeypatch):
    from tools import cli_runner
    d = tmp_path / "proj"
    d.mkdir()
    (d / "real.csv").write_text("a\n", encoding="utf-8")
    (d / ".pipeline_state.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli_runner, "get_result_candidate_dirs", lambda p: [d])
    names = [os.path.basename(f) for f in cli_runner.scan_outputs("proj")]
    assert "real.csv" in names
    assert all(not n.startswith(".") for n in names)


# ── 工具注册（需 mcp）────────────────────────────────────────────────────────

def test_server_registers_nine_tools():
    pytest.importorskip("mcp")
    import asyncio
    import server
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == {
        "run_pipeline", "query_results", "extract_triggers", "visualize",
        "explore_thresholds", "report", "list_projects", "get_job_status", "list_jobs",
    }


# ── 子进程端到端（无项目 / 无 pandas 时跳过）─────────────────────────────────

def test_cli_runner_query_end_to_end():
    pytest.importorskip("pandas")
    import config
    config.setup()
    from tools.projects import execute_list_projects
    projects = json.loads(execute_list_projects())["projects"]
    if not projects:
        pytest.skip("无已有项目，跳过子进程端到端")
    from tools import cli_runner
    res = cli_runner.run_cli(
        ["query", "--project", projects[0]["name"], "--kind", "iv", "--top", "2"],
        timeout=120,
    )
    assert res["returncode"] == 0
