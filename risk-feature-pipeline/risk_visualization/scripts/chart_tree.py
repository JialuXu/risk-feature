# -*- coding: utf-8 -*-
"""决策树可视化：

- 路线 B（首选）：从 `_intermediate/rule_tree_*.pkl` 加载 sklearn 树，用 plot_tree 渲染
- 路线 A（降级）：从 `_风险规则表.csv` 反推路径，按公共前缀拼回二叉分裂图

两条路都按 scope（全样本 / 各分群）出多张图。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from . import style  # 字体配置
from .style import (
    POS_COLOR, NEG_COLOR, NEUTRAL_COLOR, FIGSIZE_TREE, GRID_COLOR,
)


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', '_', str(name).strip()) or 'x'


# ---------- 路线 B：pkl + plot_tree ----------

def _render_pkl_tree(
    pkl_path: Path,
    out_path: Path,
    title: str,
    dpi: int,
) -> Optional[Path]:
    try:
        import joblib
        from sklearn.tree import plot_tree
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    try:
        bundle = joblib.load(pkl_path)
    except Exception as e:
        print(f'[跳过 tree] pkl 加载失败 {pkl_path.name}: {e}')
        return None

    tree = bundle.get('tree') if isinstance(bundle, dict) else bundle
    feature_names = bundle.get('feature_names') if isinstance(bundle, dict) else None
    if tree is None:
        return None

    fig, ax = plt.subplots(figsize=FIGSIZE_TREE)
    plot_tree(
        tree,
        feature_names=feature_names,
        class_names=['好', '坏'],
        filled=True,
        rounded=True,
        impurity=True,
        proportion=False,
        precision=3,
        fontsize=9,
        ax=ax,
    )
    ax.set_title(title)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return out_path


# ---------- 路线 A：从规则 CSV 反推 ----------

_OP_REVERSE_CN = {'大于等于': '>=', '大于': '>', '小于等于': '<=', '小于': '<', '等于': '=='}
_RULE_TOKEN_RE = re.compile(
    r'^\s*(?P<feat>.+?)\s+(?P<op>大于等于|大于|小于等于|小于|等于|>=|<=|>|<|==)\s+(?P<thr>-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*$'
)


def _parse_conditions(text: str) -> List[Tuple[str, str, float]]:
    """把 `特征A 大于 0.5 且 特征B 小于等于 0.3` 拆成 [(feat, op, thr), ...]。"""
    if not isinstance(text, str) or not text.strip():
        return []
    parts = re.split(r'\s+且\s+|\s+AND\s+|\s+&&\s+', text)
    out = []
    for p in parts:
        m = _RULE_TOKEN_RE.match(p)
        if not m:
            continue
        feat = m.group('feat').strip()
        op = _OP_REVERSE_CN.get(m.group('op'), m.group('op'))
        thr = float(m.group('thr'))
        out.append((feat, op, thr))
    return out


class _Node:
    __slots__ = ('feat', 'op', 'thr', 'children', 'leaf')

    def __init__(self):
        self.feat: Optional[str] = None
        self.op: Optional[str] = None
        self.thr: Optional[float] = None
        self.children: List['_Node'] = []
        self.leaf: Optional[Dict] = None


def _build_tree_from_paths(rules: List[Dict]) -> _Node:
    """按规则路径的公共前缀拼回二叉树。

    rules: [{'conditions': [(feat,op,thr),...], 'leaf_meta': {...}}, ...]
    """
    root = _Node()
    for r in rules:
        conds = r['conditions']
        leaf_meta = r['leaf_meta']
        node = root
        for (feat, op, thr) in conds:
            existing = next(
                (c for c in node.children
                 if c.feat == feat and c.op == op and c.thr == thr),
                None,
            )
            if existing is None:
                new = _Node()
                new.feat, new.op, new.thr = feat, op, thr
                node.children.append(new)
                node = new
            else:
                node = existing
        node.leaf = leaf_meta
    return root


def _layout_tree(root: _Node) -> Tuple[Dict[int, Tuple[float, float]], List[Tuple[int, int]], Dict[int, _Node]]:
    """简单层级布局：BFS 给每层均匀铺位。"""
    pos: Dict[int, Tuple[float, float]] = {}
    edges: List[Tuple[int, int]] = []
    nodes: Dict[int, _Node] = {}

    layers: List[List[Tuple[int, _Node, int]]] = []  # [(id, node, parent_id)]
    nid = [0]

    def bfs():
        queue = [(root, -1, 0)]
        while queue:
            next_queue = []
            this_layer = []
            for node, parent_id, depth in queue:
                cur_id = nid[0]
                nid[0] += 1
                nodes[cur_id] = node
                this_layer.append((cur_id, node, parent_id))
                if parent_id >= 0:
                    edges.append((parent_id, cur_id))
                for child in node.children:
                    next_queue.append((child, cur_id, depth + 1))
            layers.append(this_layer)
            queue = next_queue

    bfs()

    # 每层均匀分配 x，y 自顶向下
    n_layers = len(layers)
    for li, layer in enumerate(layers):
        n = len(layer)
        for i, (cid, _, _) in enumerate(layer):
            x = (i + 1) / (n + 1)
            y = 1 - (li / max(n_layers - 1, 1))
            pos[cid] = (x, y)

    return pos, edges, nodes


def _render_path_tree(
    rules_df: pd.DataFrame,
    out_path: Path,
    title: str,
    dpi: int,
    max_rules: int = 30,
) -> Optional[Path]:
    """没 pkl 时的退化：从规则 CSV 反推树形。"""
    import matplotlib.pyplot as plt

    if rules_df is None or rules_df.empty or '规则条件' not in rules_df.columns:
        return None

    # 取覆盖 lift 较高的前 N 条，避免画面太密
    df = rules_df.copy()
    sort_col = 'Lift' if 'Lift' in df.columns else None
    if sort_col:
        df['Lift'] = pd.to_numeric(df['Lift'], errors='coerce')
        df = df.sort_values('Lift', ascending=False)
    df = df.head(max_rules)

    rules = []
    for _, row in df.iterrows():
        conds = _parse_conditions(row.get('规则条件', ''))
        if not conds:
            continue
        rules.append({
            'conditions': conds,
            'leaf_meta': {
                'bad_rate': pd.to_numeric(row.get('规则坏账率', None), errors='coerce'),
                'coverage': pd.to_numeric(row.get('覆盖率', None), errors='coerce'),
                'lift': pd.to_numeric(row.get('Lift', None), errors='coerce'),
                'stability': str(row.get('稳定性等级', '')),
                'rule_id': row.get('规则编号', ''),
            },
        })
    if not rules:
        return None

    root = _build_tree_from_paths(rules)
    pos, edges, nodes = _layout_tree(root)

    fig, ax = plt.subplots(figsize=FIGSIZE_TREE)
    # 边
    for src, dst in edges:
        x1, y1 = pos[src]
        x2, y2 = pos[dst]
        ax.plot([x1, x2], [y1, y2], color=NEUTRAL_COLOR, linewidth=0.8, alpha=0.6, zorder=1)

    # 节点
    for nid_, (x, y) in pos.items():
        node = nodes[nid_]
        if node.leaf is not None:
            br = node.leaf.get('bad_rate')
            color = POS_COLOR if (br is not None and not pd.isna(br) and br < 0.5) else NEG_COLOR
            label = (f"r{node.leaf.get('rule_id','')}\n"
                     f"bad={br:.1%}\n"
                     f"cov={node.leaf.get('coverage',0):.1%}\n"
                     f"lift={node.leaf.get('lift',0):.2f}\n"
                     f"{node.leaf.get('stability','')}")
            ax.scatter(x, y, s=600, color=color, edgecolors='white', zorder=2)
            ax.text(x, y - 0.025, label, ha='center', va='top', fontsize=7, color='#2C3E50')
        elif node.feat is not None:
            label = f'{node.feat}\n{node.op} {node.thr:.4g}'
            ax.scatter(x, y, s=400, color='#FDFEFE', edgecolors='#34495E', linewidths=1.2, zorder=2)
            ax.text(x, y, label, ha='center', va='center', fontsize=8, color='#2C3E50')
        else:
            # root
            ax.scatter(x, y, s=200, color='#34495E', zorder=2)
            ax.text(x, y + 0.02, '根', ha='center', va='bottom', fontsize=9, color='#2C3E50')

    ax.set_xlim(0, 1)
    ax.set_ylim(-0.05, 1.05)
    ax.axis('off')
    ax.set_title(title + '（路径还原图：pkl 不存在时的降级渲染）')

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return out_path


# ---------- 顶层入口 ----------

def chart_tree(
    rules_df: Optional[pd.DataFrame],
    intermediate_dir: Optional[Path],
    out_dir: Path,
    dpi: int = 300,
) -> List[Path]:
    """决策树可视化。

    优先：扫 intermediate_dir 下所有 rule_tree_*.pkl，每个出一张 plot_tree
    降级：用 rules_df 反推路径树（按 segment_dim/segment_value 分组）
    """
    paths: List[Path] = []
    out_dir.mkdir(parents=True, exist_ok=True)

    pkl_rendered = False
    if intermediate_dir is not None and intermediate_dir.is_dir():
        pkls = sorted(intermediate_dir.glob('rule_tree_*.pkl'))
        for pkl in pkls:
            scope = pkl.stem.replace('rule_tree_', '')
            out = out_dir / f'tree_{_safe(scope)}.png'
            rendered = _render_pkl_tree(pkl, out, title=f'决策树 | {scope}', dpi=dpi)
            if rendered:
                paths.append(rendered)
                pkl_rendered = True

    # 即使 pkl 已经渲染，规则反推图也保留作为对照（更紧凑、含 lift）
    if rules_df is not None and not rules_df.empty:
        # A4 后规则表分群值列改名为「分群名称」，兼容旧版「分群值」
        seg_col = '分群名称' if '分群名称' in rules_df.columns else (
            '分群值' if '分群值' in rules_df.columns else None
        )
        if '分群维度' in rules_df.columns and seg_col is not None:
            for (d, g), sub in rules_df.groupby(['分群维度', seg_col]):
                out = out_dir / f'tree_paths_{_safe(d)}__{_safe(g)}.png'
                rendered = _render_path_tree(
                    sub, out, title=f'规则路径树 | {d} = {g}', dpi=dpi,
                )
                if rendered:
                    paths.append(rendered)
        else:
            out = out_dir / 'tree_paths_全样本.png'
            rendered = _render_path_tree(
                rules_df, out, title='规则路径树 | 全样本', dpi=dpi,
            )
            if rendered:
                paths.append(rendered)

    if not paths:
        print('[跳过 tree] 既无 rule_tree_*.pkl 也无可解析的 _风险规则表.csv')

    return paths
