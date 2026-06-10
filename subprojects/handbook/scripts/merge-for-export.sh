#!/usr/bin/env bash
set -euo pipefail

BOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$BOOK_DIR/../.." && pwd)"
OUT_DIR="$BOOK_DIR/_export"
ORDER_FILE="$BOOK_DIR/scripts/export-order.txt"
MERGE_FILE="$OUT_DIR/handbook-merged.md"

mkdir -p "$OUT_DIR"
: >"$MERGE_FILE"

{
  echo "---"
  echo "title: Skill 文档手册（合并导出）"
  echo "lang: zh-CN"
  echo "date: $(date +%Y-%m-%d)"
  echo "---"
  echo ""
} >>"$MERGE_FILE"

while IFS= read -r rel || [[ -n "${rel:-}" ]]; do
  rel="${rel#"${rel%%[![:space:]]*}"}"
  rel="${rel%"${rel##*[![:space:]]}"}"
  [[ -z "$rel" ]] && continue
  [[ "$rel" == \#* ]] && continue

  src="$REPO_ROOT/$rel"
  if [[ ! -f "$src" ]]; then
    echo "缺少文件：$src" >&2
    exit 1
  fi

  {
    echo ""
    echo "---"
    echo ""
    echo "## 文档来源：$rel"
    echo ""
  } >>"$MERGE_FILE"

  cat "$src" >>"$MERGE_FILE"
done <"$ORDER_FILE"

echo "已生成：$MERGE_FILE"
