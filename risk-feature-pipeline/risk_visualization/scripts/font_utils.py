# -*- coding: utf-8 -*-
"""中文字体 OS 探测（CLAUDE.md 硬要求）。

按 macOS / Windows / Linux 列候选字体，逐个用 matplotlib 的 fontManager 探测；
命中第一个即设到 rcParams['font.sans-serif']，并关掉 unicode_minus 的默认负号渲染。
全部 miss 时只 warn，不抛异常 —— 让没装中文字体的环境也能出图（CJK 会变方框）。
"""
from __future__ import annotations

import platform
import warnings
from typing import List, Optional

_CANDIDATES = {
    'Darwin': [
        'PingFang SC', 'Heiti SC', 'STHeiti', 'Hiragino Sans GB',
        'Arial Unicode MS', 'Songti SC',
    ],
    'Windows': [
        'Microsoft YaHei', 'SimHei', 'KaiTi', 'FangSong',
    ],
    'Linux': [
        'Noto Sans CJK SC', 'Noto Sans SC', 'Source Han Sans SC',
        'WenQuanYi Zen Hei', 'WenQuanYi Micro Hei', 'AR PL UMing CN',
        'AR PL UKai CN', 'DejaVu Sans',  # DejaVu = 最终兜底（不含 CJK）
    ],
}

_configured = False
_active_font: Optional[str] = None


def _candidate_list() -> List[str]:
    sysname = platform.system()
    cands = list(_CANDIDATES.get(sysname, []))
    # 跨平台兜底：把所有平台候选合一份（用户可能装了第三方 CJK 字体）
    for k, v in _CANDIDATES.items():
        if k == sysname:
            continue
        for f in v:
            if f not in cands:
                cands.append(f)
    return cands


def configure_chinese_font(force: bool = False) -> Optional[str]:
    """探测并配置中文字体。返回命中的字体名（None = 全 miss）。

    幂等：默认只配置一次；force=True 时强制重跑探测。
    """
    global _configured, _active_font
    if _configured and not force:
        return _active_font

    import matplotlib
    from matplotlib import font_manager, rcParams

    available = {f.name for f in font_manager.fontManager.ttflist}
    hit: Optional[str] = None
    for name in _candidate_list():
        if name in available:
            hit = name
            break

    if hit is None:
        # 再用 findfont 兜一次（处理别名）
        for name in _candidate_list():
            try:
                path = font_manager.findfont(
                    font_manager.FontProperties(family=name),
                    fallback_to_default=False,
                )
                if path:
                    hit = name
                    break
            except Exception:
                continue

    if hit is None:
        warnings.warn(
            '[risk_visualization] 未发现中文字体，CJK 字符将渲染为方框。'
            '建议：Linux 安装 fonts-noto-cjk；Windows 检查 Microsoft YaHei；'
            'macOS 通常自带 PingFang SC。'
        )
    else:
        # 中文字体优先；保留 DejaVu Sans 作为非 CJK 字符（如 −、✗、希腊字母）的 fallback
        existing = list(rcParams.get('font.sans-serif', []))
        chain = [hit]
        for f in ('DejaVu Sans', 'Liberation Sans', 'Bitstream Vera Sans'):
            if f not in chain:
                chain.append(f)
        for f in existing:
            if f not in chain:
                chain.append(f)
        rcParams['font.sans-serif'] = chain
        rcParams['font.family'] = 'sans-serif'

    rcParams['axes.unicode_minus'] = False  # 即使没中文字体，也修负号渲染

    _configured = True
    _active_font = hit
    return hit


__all__ = ['configure_chinese_font']
