"""元表本地存储: SQLite 主存 + CSV 快照双写, 支持 SCD2."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

from .io_utils import append_audit, write_csv

OPEN_EXP_DT = "9999-12-31"


# 与 meta_schema.yaml indicator_schema 一致的 40 字段 (顺序仅用于 CSV 输出友好)
META_COLUMNS: list[str] = [
    "ind_code", "ind_version", "ind_name_cn", "ind_name_en",
    "domain", "granularity", "window", "value_type", "value_unit",
    "biz_definition", "calc_logic",
    "source_tables", "source_fields", "source_domain_tables_blocked",
    "current_signal_strength", "current_iv", "current_iv_credibility",
    "current_coverage_rate", "current_risk_direction",
    "iv_history",
    "priority", "priority_history",
    "lifecycle_status", "physical_target",
    "proposer", "proposer_detail", "owner", "notes",
    "eff_dt", "exp_dt", "etl_dt", "etl_timestamp", "part_ymd",
    "is_dynamic_expansion", "dynamic_template", "dynamic_axes",
    "parent_template_code", "ref_date_logic", "null_handling",
    "post_processing_rule",
]

# 元表辅助列 (本地存储用,不属于业务 schema)
EXTRA_COLUMNS: list[str] = ["batch_id", "registered_at"]

ALL_COLUMNS = META_COLUMNS + EXTRA_COLUMNS

# JSON 序列化字段 (SQLite 没有数组/对象类型)
_JSON_FIELDS = {
    "source_tables", "source_fields", "source_domain_tables_blocked",
    "iv_history", "priority_history", "physical_target",
    "dynamic_axes", "null_handling",
}


class MetaStore:
    """元表读写抽象. 隐藏 JSON 序列化和 SCD2 拉链细节."""

    def __init__(self, sqlite_path: str | Path, snapshots_dir: str | Path,
                 audit_log: str | Path):
        self.sqlite_path = Path(sqlite_path)
        self.snapshots_dir = Path(snapshots_dir)
        self.audit_log = Path(audit_log)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        """初始化 SQLite 表结构. 业务字段全部 TEXT (JSON / 字符串日期), 数值字段单独转." """
        with self._conn() as conn:
            cols_sql = []
            for c in ALL_COLUMNS:
                if c in {"ind_version", "is_dynamic_expansion"}:
                    cols_sql.append(f"{c} INTEGER")
                elif c in {"current_iv", "current_coverage_rate"}:
                    cols_sql.append(f"{c} REAL")
                else:
                    cols_sql.append(f"{c} TEXT")
            cols_sql_str = ",\n  ".join(cols_sql)
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS indicator_meta (
                  {cols_sql_str},
                  PRIMARY KEY (ind_code, ind_version)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_domain ON indicator_meta(domain)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_priority ON indicator_meta(priority)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle ON indicator_meta(lifecycle_status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_exp_dt ON indicator_meta(exp_dt)")

    # ---------- 序列化 ----------

    @staticmethod
    def _to_db_row(record: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for c in ALL_COLUMNS:
            v = record.get(c)
            if c in _JSON_FIELDS and v is not None and not isinstance(v, str):
                v = json.dumps(v, ensure_ascii=False)
            if isinstance(v, (date, datetime)):
                v = v.isoformat()
            out[c] = v
        return out

    @staticmethod
    def _from_db_row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for c in _JSON_FIELDS:
            if d.get(c):
                try:
                    d[c] = json.loads(d[c])
                except (TypeError, json.JSONDecodeError):
                    pass
        return d

    # ---------- 查询 ----------

    def list_active(self, domain: str | None = None) -> list[dict[str, Any]]:
        """查所有当前态 (exp_dt = OPEN_EXP_DT) 且非废弃的指标."""
        sql = """SELECT * FROM indicator_meta
                 WHERE exp_dt = ? AND lifecycle_status NOT IN ('DEPRECATED','RETIRED')"""
        params: list[Any] = [OPEN_EXP_DT]
        if domain:
            sql += " AND domain = ?"
            params.append(domain)
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._from_db_row(r) for r in rows]

    def find(self, ind_code: str, version: int | None = None) -> dict[str, Any] | None:
        with self._conn() as conn:
            if version is not None:
                row = conn.execute(
                    "SELECT * FROM indicator_meta WHERE ind_code = ? AND ind_version = ?",
                    (ind_code, version),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM indicator_meta WHERE ind_code = ? AND exp_dt = ?",
                    (ind_code, OPEN_EXP_DT),
                ).fetchone()
        return self._from_db_row(row) if row else None

    def list_existing_pairs(self, domain: str | None = None) -> list[tuple[str, str]]:
        """返回 [(ind_code, ind_name_cn)]; 用于去重比对."""
        records = self.list_active(domain)
        return [(r["ind_code"], r["ind_name_cn"] or "") for r in records]

    # ---------- 写入 ----------

    def write_scd2(self, record: dict[str, Any], batch_id: str) -> str:
        """SCD2 写入.

        - 若 ind_code 已有当前态 + 业务字段有变 → 关闭旧版 + 开新版 (ind_version+1)
        - 若 ind_code 无当前态 → 直接 INSERT, ind_version=1
        - 若有当前态且业务字段无变 → 仅追加 iv_history / priority_history (不开新版本)

        返回操作描述: 'inserted' / 'new_version' / 'soft_update' / 'noop'.
        """
        rec = dict(record)
        rec.setdefault("ind_version", 1)
        rec.setdefault("eff_dt", date.today().isoformat())
        rec.setdefault("exp_dt", OPEN_EXP_DT)
        rec.setdefault("lifecycle_status", "ACTIVE")
        rec.setdefault("etl_timestamp", datetime.now().isoformat(timespec="seconds"))
        rec["batch_id"] = batch_id
        rec["registered_at"] = datetime.now().isoformat(timespec="seconds")

        existing = self.find(rec["ind_code"])
        action = "inserted"

        if existing is not None:
            if _has_business_change(existing, rec):
                # SCD2: 关闭旧版
                today = date.today().isoformat()
                with self._conn() as conn:
                    conn.execute(
                        "UPDATE indicator_meta SET exp_dt = ? WHERE ind_code = ? AND ind_version = ?",
                        (today, existing["ind_code"], existing["ind_version"]),
                    )
                rec["ind_version"] = int(existing["ind_version"]) + 1
                rec["eff_dt"] = today
                action = "new_version"
            else:
                # 软更新: 不开新版本, 但允许追加 iv_history 等
                rec["ind_version"] = existing["ind_version"]
                action = "soft_update"
                self._soft_update(existing["ind_code"], existing["ind_version"], rec)
                self._snapshot(batch_id)
                self._audit(f"soft_update {rec['ind_code']} v{rec['ind_version']} batch={batch_id}")
                return action

        db_row = self._to_db_row(rec)
        cols = ",".join(db_row.keys())
        placeholders = ",".join("?" * len(db_row))
        with self._conn() as conn:
            conn.execute(
                f"INSERT INTO indicator_meta ({cols}) VALUES ({placeholders})",
                tuple(db_row.values()),
            )
        self._snapshot(batch_id)
        self._audit(f"{action} {rec['ind_code']} v{rec['ind_version']} batch={batch_id}")
        return action

    def _soft_update(self, ind_code: str, version: int, rec: dict[str, Any]) -> None:
        """仅更新非业务字段 (iv_history, current_*, priority, priority_history, notes)."""
        soft_fields = [
            "current_signal_strength", "current_iv", "current_iv_credibility",
            "current_coverage_rate", "current_risk_direction",
            "iv_history", "priority", "priority_history", "notes",
            "etl_timestamp", "batch_id",
        ]
        db_row = self._to_db_row(rec)
        set_clauses = ", ".join(f"{c} = ?" for c in soft_fields if c in db_row)
        params = [db_row[c] for c in soft_fields if c in db_row]
        params += [ind_code, version]
        with self._conn() as conn:
            conn.execute(
                f"UPDATE indicator_meta SET {set_clauses} "
                f"WHERE ind_code = ? AND ind_version = ?",
                tuple(params),
            )

    def deprecate(self, ind_code: str) -> bool:
        """标 DEPRECATED 并关闭拉链."""
        today = date.today().isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE indicator_meta SET lifecycle_status='DEPRECATED', exp_dt=? "
                "WHERE ind_code=? AND exp_dt=?",
                (today, ind_code, OPEN_EXP_DT),
            )
            ok = cur.rowcount > 0
        if ok:
            self._audit(f"deprecate {ind_code}")
        return ok

    # ---------- 快照 ----------

    def _snapshot(self, batch_id: str) -> Path:
        """导出当前态 CSV 快照."""
        records = self.list_active()
        # 把 list/dict 字段序列化为 JSON 字符串以便 Excel 打开
        for r in records:
            for f in _JSON_FIELDS:
                if isinstance(r.get(f), (list, dict)):
                    r[f] = json.dumps(r[f], ensure_ascii=False)
        snapshot_path = self.snapshots_dir / f"indicator_meta_{batch_id}.csv"
        write_csv(snapshot_path, records, fieldnames=ALL_COLUMNS)
        return snapshot_path

    def _audit(self, message: str) -> None:
        append_audit(self.audit_log, message)


def _has_business_change(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """判断是否产生 SCD2 新版本: 业务字段任一改变 → True."""
    business_fields = [
        "ind_name_cn", "domain", "granularity", "window", "value_type",
        "biz_definition", "calc_logic",
        "source_tables", "source_fields",
        "is_dynamic_expansion", "dynamic_template", "ref_date_logic",
        "null_handling", "post_processing_rule",
    ]
    for f in business_fields:
        if _normalize(old.get(f)) != _normalize(new.get(f)):
            return True
    return False


def _normalize(v: Any) -> Any:
    if isinstance(v, list):
        return tuple(v)
    if isinstance(v, dict):
        return tuple(sorted(v.items()))
    return v
