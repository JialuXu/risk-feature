"""指标去重: rapidfuzz 文本相似度. 首版无 embedding, 接口预留."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from rapidfuzz import fuzz, process


@dataclass
class DedupResult:
    candidate_code: str
    candidate_name: str
    matched_code: str | None
    matched_name: str | None
    score: float
    is_duplicate: bool


def text_similarity(a: str, b: str, method: str = "token_set_ratio") -> float:
    """rapidfuzz 文本相似度. 0-100."""
    fn = getattr(fuzz, method, fuzz.token_set_ratio)
    return float(fn(a, b))


def find_top_similar(
    candidate_text: str,
    existing_pairs: list[tuple[str, str]],  # [(ind_code, ind_name_cn), ...]
    top_k: int = 5,
    method: str = "token_set_ratio",
) -> list[tuple[str, str, float]]:
    """返回元表中最相似的 top_k 条 (ind_code, ind_name, score)."""
    if not existing_pairs:
        return []
    fn = getattr(fuzz, method, fuzz.token_set_ratio)
    choices = {i: name for i, (_, name) in enumerate(existing_pairs)}
    matches = process.extract(candidate_text, choices, scorer=fn, limit=top_k)
    return [
        (existing_pairs[idx][0], existing_pairs[idx][1], float(score))
        for _name, score, idx in matches
    ]


def check_duplicate(
    candidate: dict,
    existing_pairs: list[tuple[str, str]],
    threshold: float = 85.0,
    method: str = "token_set_ratio",
    embedding_backend: Callable[[str, str], float] | None = None,
) -> DedupResult:
    """对单条候选指标做去重检查.

    embedding_backend: 预留接口. 若提供, 与文本分数取 max.
    """
    candidate_code = candidate.get("ind_code", "")
    candidate_name = candidate.get("ind_name_cn", "")
    # 主匹配用名称 (中文短串,token_set_ratio 友好)
    similar = find_top_similar(candidate_name, existing_pairs, top_k=1, method=method)
    if not similar:
        return DedupResult(candidate_code, candidate_name, None, None, 0.0, False)

    matched_code, matched_name, score = similar[0]

    # embedding 加权 (首版关闭)
    if embedding_backend is not None:
        biz = candidate.get("biz_definition", "")
        emb_score = embedding_backend(f"{candidate_name} {biz}", matched_name) * 100
        score = max(score, emb_score)

    is_dup = score >= threshold
    return DedupResult(
        candidate_code=candidate_code,
        candidate_name=candidate_name,
        matched_code=matched_code,
        matched_name=matched_name,
        score=score,
        is_duplicate=is_dup,
    )
