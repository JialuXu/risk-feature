"""加载 表清单.csv + 表字段清单.csv, 提供字段查询."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

from .io_utils import read_csv


@dataclass(frozen=True)
class TableField:
    table_en: str
    table_cn: str
    field_en: str
    field_cn: str
    field_type: str


@dataclass
class FieldDict:
    """基础表字段字典. 支持 exact / fuzzy 查询."""
    fields: list[TableField]

    @lru_cache(maxsize=4096)
    def find_by_field_cn(self, name_cn: str) -> list[TableField]:
        return [f for f in self.fields if f.field_cn == name_cn]

    @lru_cache(maxsize=4096)
    def find_by_field_en(self, name_en: str) -> list[TableField]:
        return [f for f in self.fields if f.field_en == name_en]

    def find_in_table(self, table_en: str) -> list[TableField]:
        return [f for f in self.fields if f.table_en == table_en]

    def fuzzy_search_by_cn(self, query: str, top_k: int = 5, score_cutoff: int = 70) -> list[tuple[TableField, int]]:
        """按中文模糊搜索."""
        choices = {i: f.field_cn for i, f in enumerate(self.fields)}
        matches = process.extract(query, choices, scorer=fuzz.WRatio,
                                  limit=top_k, score_cutoff=score_cutoff)
        return [(self.fields[idx], score) for _name, score, idx in matches]

    def field_exists(self, table_en: str, field_en: str) -> bool:
        return any(f.table_en == table_en and f.field_en == field_en for f in self.fields)

    def list_tables(self) -> list[str]:
        return sorted({f.table_en for f in self.fields})


def load_field_dict(
    table_list_csv: str | Path,
    table_field_csv: str | Path,
) -> FieldDict:
    """从两个 CSV 加载字段字典."""
    table_rows = read_csv(table_list_csv)
    table_cn_map = {r["表英文名"]: r["表中文名"] for r in table_rows}

    field_rows = read_csv(table_field_csv)
    fields = [
        TableField(
            table_en=r["表英文名"],
            table_cn=table_cn_map.get(r["表英文名"], ""),
            field_en=r["字段英文名"],
            field_cn=r["字段中文名"],
            field_type=r["字段类型"],
        )
        for r in field_rows
    ]
    return FieldDict(fields=fields)


def load_default_field_dict(project_root: Path | None = None,
                            references_dir: Path | None = None) -> FieldDict:
    """从 references/ 加载 (推荐入口). references_dir 缺省 = {project_root}/references."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent
    refs = Path(references_dir) if references_dir is not None else project_root / "references"
    return load_field_dict(refs / "表清单.csv", refs / "表字段清单.csv")
