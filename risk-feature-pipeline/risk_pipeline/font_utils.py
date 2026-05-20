# -*- coding: utf-8 -*-
"""跨 OS 中文字体探测（链路级共享）。

历史背景：原来这套代码只活在 `risk_visualization/scripts/font_utils.py`，
当 `risk_segment_univariate.boxplot` 也要画中文图时，它没法再依赖
`risk_visualization` 被导入（容易触发循环或路径不对）。所以提到这里作为唯一权威，
并把检测做得更宽容：
  1. 精确名匹配（沿用旧候选表）
  2. 关键词子串匹配（兼容 'Noto Sans CJK SC Regular' / 'NotoSansCJK-Regular' 等变体）
  3. matplotlib 的 findfont 兜底（处理别名）
  4. 配置完一次"渲染 中 字符"自检 —— 仍是方框时打印更醒目的诊断
旧入口 `risk_visualization.scripts.font_utils.configure_chinese_font` 现在转发到这里。
"""
from __future__ import annotations

import platform
import warnings
from typing import List, Optional

# 高频精确名（按平台优先级）
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
        'Source Han Sans CN', 'WenQuanYi Zen Hei', 'WenQuanYi Micro Hei',
        'AR PL UMing CN', 'AR PL UKai CN',
    ],
}

# 子串关键词：matplotlib 在不同平台/版本下可能把 CJK 字体注册成各种变体名
# 一律用关键词扫一遍 fontManager.ttflist，命中第一个非纯英文的字体
_CJK_KEYWORDS = (
    'CJK', 'Han', 'PingFang', 'Heiti', 'YaHei', 'SimHei', 'SimSun', 'KaiTi',
    'FangSong', 'WenQuanYi', 'Wenquan', 'Noto Sans SC', 'Noto Sans TC',
    'Noto Sans JP', 'Noto Sans KR', 'Source Han', 'Songti', 'Hiragino',
    'STHeiti', 'STSong', 'STFangsong', 'STKaiti',
)

_configured = False
_active_font: Optional[str] = None


def _platform_candidate_list() -> List[str]:
    sysname = platform.system()
    cands = list(_CANDIDATES.get(sysname, []))
    # 跨平台兜底：合并所有平台的候选，覆盖第三方安装
    for k, v in _CANDIDATES.items():
        if k == sysname:
            continue
        for f in v:
            if f not in cands:
                cands.append(f)
    return cands


def _match_by_keyword(available: set) -> Optional[str]:
    """从已加载字体里按关键词扫一遍。命中规则：字体名包含任一关键词。"""
    for name in sorted(available):
        for kw in _CJK_KEYWORDS:
            if kw.lower() in name.lower():
                return name
    return None


def _self_test_chinese_glyph(font_name: Optional[str]) -> bool:
    """配置完字体后画一个 '中' 字，检查是否落到我们设的字体上。"""
    if font_name is None:
        return False
    try:
        from matplotlib import font_manager
        # 验证 '中' 字是否能被该字体渲染
        fp = font_manager.FontProperties(family=font_name)
        path = font_manager.findfont(fp, fallback_to_default=False)
        if not path:
            return False
        # 进一步打开字体文件验证是否包含 '中' (U+4E2D) 这个 codepoint
        # PIL 检测最准确，但加依赖；matplotlib 自带 ft2font 也行
        try:
            from matplotlib import ft2font
            face = ft2font.FT2Font(path)
            if face.get_char_index(0x4E2D) == 0:
                return False
            return True
        except Exception:
            # ft2font 取不到时，返回 True 不阻塞（多数情况字体名匹配就够用）
            return True
    except Exception:
        return False


def configure_chinese_font(force: bool = False, refresh_cache: bool = False) -> Optional[str]:
    """探测并配置中文字体。返回命中的字体名（None = 全 miss）。

    Args:
        force:         幂等开关；True = 强制重跑探测（即使已配置过）
        refresh_cache: 重建 matplotlib 字体缓存。装了新字体但 matplotlib 还没看到时用
    """
    global _configured, _active_font
    if _configured and not force:
        return _active_font

    from matplotlib import font_manager, rcParams

    if refresh_cache:
        # font_manager._load_fontmanager 在 3.5+ 是公开的，但参数有变；fallback 用 _rebuild
        try:
            font_manager._load_fontmanager(try_read_cache=False)
        except Exception:
            try:
                font_manager._rebuild()  # type: ignore[attr-defined]
            except Exception:
                pass

    available = {f.name for f in font_manager.fontManager.ttflist}

    # 1. 精确名匹配（按平台优先级）
    hit: Optional[str] = None
    for name in _platform_candidate_list():
        if name in available:
            hit = name
            break

    # 2. 关键词子串匹配（兼容各种变体注册名）
    if hit is None:
        hit = _match_by_keyword(available)

    # 3. findfont 兜底（处理别名）
    if hit is None:
        for name in _platform_candidate_list():
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
            '[risk_pipeline.font_utils] 未发现任何中文字体，CJK 字符将渲染为方框。\n'
            '修复建议：\n'
            '  Linux:   sudo apt-get install fonts-noto-cjk  '
            '（或 fonts-wqy-zenhei）\n'
            '  Windows: 系统通常自带 Microsoft YaHei，若 matplotlib 仍找不到，'
            '尝试调用 configure_chinese_font(refresh_cache=True)\n'
            '  macOS:   通常自带 PingFang SC，无需额外安装'
        )
    else:
        # 中文字体优先；保留 DejaVu Sans 给非 CJK 字符（−、✗、希腊字母）做 fallback
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

        # 自检：'中' 字是否真能用 hit 渲染
        if not _self_test_chinese_glyph(hit):
            warnings.warn(
                f'[risk_pipeline.font_utils] 字体 {hit!r} 命中但不包含中文字形（U+4E2D），'
                '可能是字体名同名但内容只含英文。请尝试安装 fonts-noto-cjk 或 '
                'configure_chinese_font(refresh_cache=True)。'
            )

    # 即使没中文字体也修负号渲染（DejaVu Sans 有 U+2212）
    rcParams['axes.unicode_minus'] = False

    _configured = True
    _active_font = hit
    return hit


def active_font() -> Optional[str]:
    """返回当前配置好的中文字体名（未配置时返回 None）。"""
    return _active_font


__all__ = ['configure_chinese_font', 'active_font']
