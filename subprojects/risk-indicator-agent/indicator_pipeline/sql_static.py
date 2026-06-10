"""calc_logic 伪式静态解析 (sqlglot). 只看结构合不合规, 不执行."""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp


# 禁词:不允许 calc_logic 直接用系统当日,因为参考日要看 ref_date_logic
_FORBIDDEN_FUNCS = {"current_date", "current_timestamp", "now", "today"}


@dataclass
class SQLCheckResult:
    parseable: bool
    referenced_columns: list[str]
    referenced_tables: list[str]
    referenced_functions: list[str]
    forbidden_used: list[str]
    parse_error: str | None


def analyze_calc_logic(calc_logic: str) -> SQLCheckResult:
    """尝试把 calc_logic 当 SQL 表达式解析, 提取列引用和函数."""
    # calc_logic 可能含中文 + 多行 + 注释,先剥离主体
    body = "\n".join(
        line for line in calc_logic.splitlines()
        if line.strip() and not line.strip().startswith("·")
    )

    # 试用 SELECT 包一层让 sqlglot 能 parse
    wrapped = f"SELECT {body}"
    try:
        tree = sqlglot.parse_one(wrapped, dialect="hive")
    except Exception as e:
        return SQLCheckResult(
            parseable=False,
            referenced_columns=[],
            referenced_tables=[],
            referenced_functions=[],
            forbidden_used=[],
            parse_error=str(e),
        )

    columns: list[str] = []
    tables: list[str] = []
    functions: list[str] = []
    for node in tree.walk():
        # sqlglot v23+ Expression.walk yields Expression objects directly
        if isinstance(node, exp.Expression):
            n = node
        elif isinstance(node, tuple) and node:
            n = node[0]
        else:
            continue
        if isinstance(n, exp.Column):
            col = n.name or n.this.name if hasattr(n, "this") else n.name
            if col:
                columns.append(col)
        elif isinstance(n, exp.Table):
            t = n.name
            if t:
                tables.append(t)
        elif isinstance(n, exp.Func):
            fname = n.sql_name() if hasattr(n, "sql_name") else type(n).__name__
            functions.append(fname.lower())

    forbidden = [f for f in functions if f.lower() in _FORBIDDEN_FUNCS]

    return SQLCheckResult(
        parseable=True,
        referenced_columns=sorted(set(columns)),
        referenced_tables=sorted(set(tables)),
        referenced_functions=sorted(set(functions)),
        forbidden_used=sorted(set(forbidden)),
        parse_error=None,
    )


def has_partition_predicate(sql_text: str) -> bool:
    """简单检测 SQL 是否含分区谓词 (part_ymd / partition / etl_dt)."""
    lowered = sql_text.lower()
    return any(k in lowered for k in ("part_ymd", "partition", "etl_dt"))
