"""utf-8-sig CSV / JSON I/O —— 与姊妹项目 risk-feature-pipeline 编码一致."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def write_json(path: str | Path, obj: Any, indent: int = 2) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)


def read_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_csv(
    path: str | Path,
    rows: Iterable[Mapping[str, Any]],
    fieldnames: list[str] | None = None,
) -> int:
    """写 utf-8-sig CSV (Excel 友好). 返回写入行数."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    rows_list = list(rows)
    if not rows_list:
        if fieldnames:
            with p.open("w", encoding="utf-8-sig", newline="") as f:
                csv.DictWriter(f, fieldnames=fieldnames).writeheader()
        return 0
    if fieldnames is None:
        fieldnames = list(rows_list[0].keys())
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows_list:
            w.writerow(r)
    return len(rows_list)


def read_csv(path: str | Path) -> list[dict[str, Any]]:
    """读 CSV (兼容 utf-8 / utf-8-sig). 全部字段返回字符串型."""
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def append_audit(audit_path: str | Path, message: str) -> None:
    p = Path(audit_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    with p.open("a", encoding="utf-8") as f:
        ts = datetime.now().isoformat(timespec="seconds")
        f.write(f"[{ts}] {message}\n")
