# -*- coding: utf-8 -*-
"""解耦重构 Stage 8 文档单一真源锁（纯 grep，不跑链路）。

锁四件事（DECOUPLING-DESIGN §9 阶段8「验证」列）：
  1. **50/70 漂移不复发**：全部 .md 里出现的「匹配率 < N%」必须与代码常量
     MIN_DEFAULT_FEATURE_MATCH_RATE 一致（曾经 CLAUDE.md 写 50%、AGENTS.md 写
     70%、代码 0.7——三方漂移正是本锁要抓的）。
  2. **references/ 树完整**：_index.md 存在，且其相对链接指到的每个文件都真实存在
     （防「索引指路、卡片缺席」）。
  3. **阻断 flag 拼写一致**：blocking-gates.md 里写的三个放行 flag 必须真实存在于
     组合根 argspec 对应子命令的声明中（文档教的命令必须能跑）。
  4. **懒加载结构就位**：AGENTS.md 引用 references/_index.md；12 个子 SKILL.md
     顶部有「何时读我」。
"""
from __future__ import annotations

import re
from pathlib import Path

PIPE_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PIPE_ROOT.parent
REFS = PIPE_ROOT / 'references'


def _iter_md():
    for base in (PIPE_ROOT, WORKSPACE_ROOT / 'CLAUDE.md'):
        if base.is_file():
            yield base
            continue
        for md in base.rglob('*.md'):
            parts = md.relative_to(base).parts
            # 跳过第三方参考与本地草稿目录
            if parts[0] in ('node_modules', '.git'):
                continue
            yield md


def test_match_rate_threshold_consistent_with_code():
    from risk_trigger_extraction.scripts.config import MIN_DEFAULT_FEATURE_MATCH_RATE
    expect = int(round(MIN_DEFAULT_FEATURE_MATCH_RATE * 100))
    pat = re.compile(r'匹配率[^0-9%\n]{0,10}(\d{1,3})\s*%')
    # DECOUPLING-DESIGN.md 刻意叙述历史上的 50/70 漂移与修复前失败场景，
    # 属"问题陈述"而非现行行为声明——豁免；其余文档必须与代码真值一致。
    exempt = {'DECOUPLING-DESIGN.md'}
    drift = []
    for md in _iter_md():
        if md.name in exempt:
            continue
        for m in pat.finditer(md.read_text(encoding='utf-8', errors='ignore')):
            if int(m.group(1)) != expect:
                drift.append(f'{md}: 匹配率写成 {m.group(1)}%（代码真值 {expect}%）')
    assert not drift, '文档匹配率阈值漂移（单一真源 = MIN_DEFAULT_FEATURE_MATCH_RATE）：\n' + '\n'.join(drift)


def test_references_index_links_resolve():
    index = REFS / '_index.md'
    assert index.is_file(), 'references/_index.md 缺失（懒加载索引是阶段8核心交付）'
    text = index.read_text(encoding='utf-8')
    missing = []
    for target in re.findall(r'\]\(([^)#http][^)]*)\)', text):
        if not (REFS / target).exists():
            missing.append(target)
    assert not missing, f'_index.md 指向的文件不存在：{missing}'
    # 反向：cli/ 下每张卡都应被索引提到
    unlisted = [p.name for p in (REFS / 'cli').glob('*.md') if p.name not in text]
    assert not unlisted, f'cli/ 有卡未进 _index.md：{unlisted}'


def test_blocking_flags_exist_in_argspec():
    from risk_mining import argspec
    def opts(cmd):
        return {o for e in argspec._iter_plain(argspec.flags_for(cmd)) for o in e['opts']}
    gates = (REFS / 'blocking-gates.md').read_text(encoding='utf-8')
    for flag, cmd in (
        ('--confirmed-new-dataset', 'prepare'),
        ('--confirmed-id-col', 'prepare'),
        ('--confirmed-target-col', 'prepare'),
        ('--confirmed-target-positive', 'prepare'),
        ('--confirmed', 'trigger'),
        ('--confirmed-final-version', 'report'),
    ):
        assert flag in gates, f'blocking-gates.md 缺 {flag} 的说明'
        assert flag in opts(cmd), f'{flag} 不在 argspec[{cmd}] 中——文档教的命令跑不通'


def test_lazy_load_structure_in_place():
    agents = (PIPE_ROOT / 'AGENTS.md').read_text(encoding='utf-8')
    assert 'references/_index.md' in agents, 'AGENTS.md 未指向 references/_index.md'
    skills = sorted(PIPE_ROOT.glob('risk_*/SKILL.md'))
    assert len(skills) >= 12, f'子 SKILL.md 数量异常：{len(skills)}'
    missing = [str(p.relative_to(PIPE_ROOT)) for p in skills
               if '何时读我' not in p.read_text(encoding='utf-8')]
    assert not missing, f'子 SKILL.md 缺「何时读我」顶栏：{missing}'
