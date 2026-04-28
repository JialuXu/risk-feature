"""list_projects 工具的执行逻辑"""
import json

from config import RESULT_SEARCH_ROOTS


def _build_search_dirs() -> list:
    """横跨 PIPELINE_ROOT 和其父级，扫描 data/results 与 output。"""
    dirs = []
    for root in RESULT_SEARCH_ROOTS:
        for base in ("data/results", "output"):
            dirs.append(root / base)
            dirs.append(root / base / "征信")
    return dirs


def execute_list_projects() -> str:
    projects: dict[str, list[str]] = {}

    for search_dir in _build_search_dirs():
        if not search_dir.exists():
            continue
        for child in sorted(search_dir.iterdir()):
            if not child.is_dir():
                continue
            csv_files = sorted(child.glob("*.csv"))
            json_files = sorted(child.glob("*.json"))
            if not csv_files and not json_files:
                continue
            name = child.name
            if name not in projects:
                projects[name] = []
            projects[name].append(str(child))

    return json.dumps(
        {
            "status": "success",
            "count": len(projects),
            "projects": [
                {"name": name, "result_dirs": dirs}
                for name, dirs in sorted(projects.items())
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
