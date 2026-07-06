# -*- coding: utf-8 -*-
"""Flag 单一注册表（解耦重构 Stage 4，DECOUPLING-DESIGN §4.3 / §9 阶段4）。

每个子命令的每条 flag 在此**只声明一次**：
  - ``cli._build_parser`` 遍历本表构建 argparse（不再手抄 add_argument）；
  - ``run`` 子命令的 flag 集从 **prepare∪analyze 并集派生**（``flags_for('run')``）：
    按 option-string 去重、``required`` 一律降 False（run 在 ``cmd_run`` 内自行校验
    generic 必填项）、``--steps``/``--category-dims`` 用 run 专属条目/覆盖；
  - ``cmd_run`` 的转发 Namespace 由 ``dests_for(cmd)`` 派生（不再手抄字段清单）。

由此根除 C15 结构性错误源：给 prepare/analyze 加一个 flag 只改本文件一处，
run 路径自动获得该 flag 并自动透传——不会再出现「漏改 run 分支 → 运行期静默 None」。

⚠ 条目 kwargs 逐字对齐 argparse 语义（help/type/choices/required/action/dest），
   8 个非 run 子命令的 ``--help`` 输出必须与阶段 4 之前**字节一致**（铁律 2）。
   run 的 --help 本阶段按设计**变化**：新增 --prepared/--features-file/--qual-dims/
   --project-name（并集带来），部分 help 文案改为继承 prepare 声明（单一真源）。

条目形状：
  普通 flag: {'opts': (option strings...), 'kwargs': {...add_argument kwargs...}}
  互斥组:    {'group': [条目...], 'required': True}   # 目前仅 trigger 使用
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 子命令注册顺序与 help（决定顶层 --help 的子命令列表顺序，勿随意调整）
# ---------------------------------------------------------------------------

SUBCOMMAND_ORDER = (
    'prepare', 'analyze', 'export', 'query', 'trigger',
    'report', 'visualize', 'explore_thresholds', 'run',
)

SUBCOMMAND_HELP = {
    'prepare': '构建 prepared.csv + features.json（前置态）',
    'analyze': '跑 univariate/iv/lr 子集（过渡态）',
    'export': '_intermediate/ → 8 张 CSV + LLM JSON（→ Level 1）',
    'query': '只读已有结果，top-N / 分群查询',
    'trigger': '客户级触碰提取（→ Level 2）',
    'report': 'LLM JSON → docx（→ Level 3）',
    'visualize': '生成 IV/相关性/LR/分群/规则/组合可视化（→ output/<project>/charts/）',
    'explore_thresholds': '候选规则阈值探索（optbinning 最优切点 + 业务级有效性判定）',
    'run': '便捷组合：generic 走 prepare→analyze→export',
}

# ---------------------------------------------------------------------------
# 各子命令的 flag 声明（唯一真源；顺序 = --help 内的展示顺序）
# ---------------------------------------------------------------------------

SPECS = {
    'prepare': [
        {'opts': ('--wide',), 'kwargs': {'required': True, 'help': '宽表 CSV 路径'}},
        {'opts': ('--bad-customer',), 'kwargs': {
            'default': None, 'help': '坏客户清单 CSV（宽表已有 target 时可省略）'}},
        {'opts': ('--merge-table',), 'kwargs': {
            'default': None,
            'help': '可选：在主键上 left-join 的补充表 CSV（如分群维度在另一张表，'
                    '如客户信息.csv）。免去手抄 pandas merge'}},
        {'opts': ('--merge-id-col',), 'kwargs': {
            'default': None, 'help': '补充表主键列名（默认与 --id-col 同）'}},
        {'opts': ('--merge-cols',), 'kwargs': {
            'default': None,
            'help': '只从补充表带入这些列（逗号分隔；缺省=带入全部非主键列）'}},
        {'opts': ('--id-col',), 'kwargs': {'required': True, 'help': '主键列名（无默认，必填）'}},
        {'opts': ('--target-col',), 'kwargs': {'required': True, 'help': '目标列名（无默认，必填）'}},
        {'opts': ('--bad-id-col',), 'kwargs': {
            'default': None, 'help': '坏客户清单主键列名（默认与 --id-col 同）'}},
        {'opts': ('--filter-file',), 'kwargs': {
            'default': None,
            'help': 'filter 规则 JSON。规则键: exclude/include(类别) | min/max/range(数值) | drop_na(布尔)。'
                    '示例: {"企业规模": {"exclude": ["0"]}, "非银机构占比": {"range": [0, 1]}, '
                    '"资产负债率": {"max": 1.0, "drop_na": true}}'}},
        {'opts': ('--exclude-features-file',), 'kwargs': {
            'default': None, 'help': '不参与分析的特征 JSON 数组'}},
        {'opts': ('--project', '--project-name'), 'kwargs': {
            'dest': 'project', 'required': True, 'help': '项目名（用作输出目录前缀）'}},
        {'opts': ('--confirmed-new-dataset',), 'kwargs': {
            'action': 'store_true', 'help': '[阻断节点 1] 首次使用新数据集时必传（一键确认）'}},
        # C15：拆分版确认 flag——三项全填 + 与 --id-col/--target-col 一致才视为确认通过
        {'opts': ('--confirmed-id-col',), 'kwargs': {
            'default': None,
            'help': '[阻断节点 1 / 拆分版] 显式声明确认的主键列名（须与 --id-col 一致）'}},
        {'opts': ('--confirmed-target-col',), 'kwargs': {
            'default': None,
            'help': '[阻断节点 1 / 拆分版] 显式声明确认的目标列名（须与 --target-col 一致）'}},
        {'opts': ('--confirmed-target-positive',), 'kwargs': {
            'default': None,
            'help': '[阻断节点 1 / 拆分版] 显式声明坏客户标记的取值（如 "1"），写入 audit'}},
        {'opts': ('--skip-preflight',), 'kwargs': {
            'action': 'store_true',
            # 注意：config/ 已迁到 risk_core/config/，但此 help 串刻意保留旧写法，
            # 以维持 `prepare`/`run --help` 字节不变（铁律2 冻结 --help）。勿改此路径。
            'help': '跳过 column_mapping.yaml 与宽表的字段映射预检（仅当你确认只跑全样本、'
                    '不需要分群分析时使用；否则建议先编辑 config/column_mapping.yaml）'}},
    ],

    'analyze': [
        {'opts': ('--project',), 'kwargs': {'required': True}},
        {'opts': ('--prepared',), 'kwargs': {
            'default': None, 'help': '默认 data/processed/{project}/prepared.csv'}},
        {'opts': ('--features-file',), 'kwargs': {
            'default': None, 'help': '默认 data/processed/{project}/features.json'}},
        {'opts': ('--steps',), 'kwargs': {
            'default': 'univariate,iv,lr',
            'help': '子集，逗号分隔；可选: univariate,iv,lr,rules；'
                    'CLI 强制按 univariate→iv→lr→rules 顺序。'
                    '加 rules 会跑决策树规则挖掘并把树持久化到 _intermediate/，'
                    '供 visualize 出真树图 / 规则散点 / 指标组合 / 共现网络'}},
        {'opts': ('--category-dims',), 'kwargs': {
            'default': None, 'help': '类别维度列名（逗号分隔），默认自动检测'}},
        {'opts': ('--qual-dims',), 'kwargs': {
            'default': None,
            'help': '资质标签列名（逗号分隔；空字符串=不用），默认自动检测'}},
        {'opts': ('--target-col',), 'kwargs': {
            'default': None, 'help': '默认从 features.json 读取'}},
    ],

    'export': [
        {'opts': ('--project',), 'kwargs': {'required': True}},
        {'opts': ('--intermediate-dir',), 'kwargs': {
            'default': None, 'help': '默认 data/processed/{project}/_intermediate/'}},
        {'opts': ('--output-subdir',), 'kwargs': {
            'default': None, 'help': 'data/results/ 下的子目录名，默认 {project}'}},
    ],

    'query': [
        {'opts': ('--project',), 'kwargs': {'required': True}},
        {'opts': ('--kind',), 'kwargs': {
            'choices': ['iv', 'iv_group', 'corr', 'lr'], 'required': True}},
        {'opts': ('--dim',), 'kwargs': {'default': None, 'help': '分群维度（如 企业规模）'}},
        {'opts': ('--group',), 'kwargs': {'default': None, 'help': '分群名称（如 小型企业）'}},
        {'opts': ('--top', '-n'), 'kwargs': {
            'type': int, 'default': 15, 'help': '取前 N 条（默认 15）'}},
        {'opts': ('--sign',), 'kwargs': {
            'choices': ['positive', 'negative'], 'default': None, 'help': '仅 kind=lr 生效'}},
        {'opts': ('--output-format',), 'kwargs': {
            'choices': ['table', 'csv', 'json'], 'default': 'table'}},
    ],

    'trigger': [
        {'opts': ('--project',), 'kwargs': {'required': True}},
        {'opts': ('--prepared',), 'kwargs': {'default': None}},
        {'group': [
            {'opts': ('--use-default-features',), 'kwargs': {
                'action': 'store_true', 'help': '使用 RISK_FEATURES 默认特征配置'}},
            {'opts': ('--features-file',), 'kwargs': {
                'default': None, 'help': '项目专属特征列表 JSON'}},
        ], 'required': True},
        {'opts': ('--id-col',), 'kwargs': {
            'default': None, 'help': '默认从 features.json 读取'}},
        {'opts': ('--target-col',), 'kwargs': {
            'default': None, 'help': '默认从 features.json 读取'}},
        {'opts': ('--keep-metadata-cols',), 'kwargs': {
            'default': None,
            'help': '宽表 CSV 中要保留的元信息列（逗号分隔），如 "企业规模,所属行业"。'
                    '默认全部剔除以避免与 prepared.csv merge 撞列冲突'}},
        {'opts': ('--confirmed',), 'kwargs': {
            'action': 'store_true', 'help': '[阻断节点 2] 必传：确认 features 配置正确'}},
    ],

    'report': [
        {'opts': ('--project',), 'kwargs': {'required': True}},
        {'opts': ('--llm-json',), 'kwargs': {
            'default': None, 'help': '默认 output/{project}/{project}_LLM报告数据.json'}},
        {'opts': ('--report-markdown',), 'kwargs': {
            'required': True, 'help': 'LLM 生成的 Markdown 报告'}},
        {'opts': ('--output',), 'kwargs': {
            'default': None, 'help': '默认 output/{project}/{project}.docx'}},
        {'opts': ('--purpose',), 'kwargs': {
            'choices': ['internal', 'external'], 'required': True,
            'help': '[阻断节点 3] internal=内部审阅 / external=对外交付'}},
        {'opts': ('--appendix-mode',), 'kwargs': {
            'default': None, 'choices': ['both', 'feature', 'segment', 'none', 'compact'],
            'help': '附录模式（默认 both）'}},
        {'opts': ('--confirmed-final-version',), 'kwargs': {
            'action': 'store_true', 'help': '[阻断节点 3] purpose=external 时必传'}},
    ],

    'visualize': [
        {'opts': ('--project',), 'kwargs': {'required': True}},
        {'opts': ('--kinds',), 'kwargs': {
            'default': None,
            'help': '逗号分隔: iv,iv_heatmap,corr_heatmap,lr_heatmap,'
                    'auc,segment,rules,combos,thresholds（默认全部）'}},
        {'opts': ('--dim',), 'kwargs': {
            'default': None,
            'help': '限定单一分群维度，如 企业规模（对 corr_heatmap/lr_heatmap/auc 生效）'}},
        {'opts': ('--top',), 'kwargs': {
            'type': int, 'default': 15, 'help': 'top-N 条形图截断（默认 15）'}},
        {'opts': ('--out-dir',), 'kwargs': {
            'default': None, 'help': '输出目录，默认 output/<project>/charts/'}},
        {'opts': ('--dpi',), 'kwargs': {'type': int, 'default': 300}},
    ],

    'explore_thresholds': [
        {'opts': ('--project',), 'kwargs': {'required': True}},
        {'opts': ('--prepared',), 'kwargs': {
            'default': None, 'help': '默认 data/processed/{project}/prepared.csv'}},
        {'opts': ('--pairs-file',), 'kwargs': {
            'required': True,
            'help': 'pair-list 文件（.csv 或 .json）：列 分群维度,分群名称,特征'}},
        {'opts': ('--target-col',), 'kwargs': {
            'default': None, 'help': '默认从 features.json 读取'}},
        {'opts': ('--results-subdir',), 'kwargs': {
            'default': None,
            'help': '结果子目录名，默认与 --project 同；产物落在 data/results/<subdir>/'}},
        {'opts': ('--min-risk-ratio',), 'kwargs': {
            'type': float, 'default': None, 'help': '风险倍数下限（默认 2.0）'}},
        {'opts': ('--max-p',), 'kwargs': {
            'type': float, 'default': None, 'help': '卡方 p 值上限（默认 0.05）'}},
        {'opts': ('--min-bad-high',), 'kwargs': {
            'type': int, 'default': None, 'help': '高风险侧坏客户数下限（默认 10）'}},
        {'opts': ('--alert-rate-min',), 'kwargs': {
            'type': float, 'default': None, 'help': '触警率下限（默认 0.01）'}},
        {'opts': ('--alert-rate-max',), 'kwargs': {
            'type': float, 'default': None, 'help': '触警率上限（默认 0.30）'}},
        {'opts': ('--min-iv',), 'kwargs': {
            'type': float, 'default': None,
            'help': '参考 IV 下限（默认 0.02 = IV_THRESHOLD.weak；优先取分群 IV，缺失回落全样本）'}},
        {'opts': ('--min-bin-size',), 'kwargs': {
            'type': float, 'default': None,
            'help': 'optbinning min_bin_size（默认 0.05；zero-inflated 数据可降到 0.02-0.03）'}},
    ],
}

# ---------------------------------------------------------------------------
# run 子命令：专属条目 + prepare∪analyze 并集派生
# ---------------------------------------------------------------------------

# run 专属 flag（并集之前先注册；--pipeline 是 run 的路由开关）
_RUN_ONLY = [
    {'opts': ('--pipeline',), 'kwargs': {
        'choices': ['credit', 'gsfc', 'generic'], 'required': True}},
]

# run 对并集条目的 kwargs 覆盖（按第一条 option-string 索引）。
# ⚠ '--steps' 必须覆盖为 default=None：analyze 的默认 'univariate,iv,lr' 若泄漏进 run，
#   会吞掉 cmd_run 的 generic 兜底 'univariate,iv,lr,rules'（丢 rules），并让
#   credit/gsfc 的 steps=None（全跑）语义失效——这是设计文档 §9 阶段4 点名的坑。
_RUN_OVERRIDES = {
    '--project': {'help': 'generic 必填'},
    '--wide': {'help': 'generic 必填'},
    '--id-col': {'help': 'generic 必填'},
    '--target-col': {'help': 'generic 必填'},
    '--steps': {'default': None,
                'help': 'credit/gsfc 步骤透传；generic 透传给 analyze'
                        '（缺省=credit/gsfc 全步骤、generic univariate,iv,lr,rules）'},
    '--category-dims': {'help': '类别维度列名（逗号分隔），默认自动检测；透传给 analyze。'
                                'credit/gsfc 用预置维度，传了会被忽略并告警'},
}


def _iter_plain(entries):
    """展平互斥组，逐条产出普通 flag 条目。"""
    for entry in entries:
        if 'group' in entry:
            yield from entry['group']
        else:
            yield entry


def flags_for(cmd):
    """返回子命令的 flag 条目列表；run 由 prepare∪analyze 并集派生。"""
    if cmd != 'run':
        return SPECS[cmd]

    merged = list(_RUN_ONLY)
    seen = {o for e in merged for o in e['opts']}
    for src in ('prepare', 'analyze'):
        for entry in _iter_plain(SPECS[src]):
            if any(o in seen for o in entry['opts']):
                continue  # 按 option-string 去重（--project/--target-col 等 prepare 先到先得）
            seen.update(entry['opts'])
            kwargs = dict(entry['kwargs'])
            kwargs.pop('required', None)  # run 内 required 一律降 False（cmd_run 自行校验）
            kwargs.update(_RUN_OVERRIDES.get(entry['opts'][0], {}))
            merged.append({'opts': entry['opts'], 'kwargs': kwargs})
    return merged


def _dest_of(entry):
    """按 argparse 规则推导条目的 dest：显式 dest 优先，否则取第一条长选项。"""
    kwargs = entry['kwargs']
    if 'dest' in kwargs:
        return kwargs['dest']
    opt = next((o for o in entry['opts'] if o.startswith('--')), entry['opts'][0])
    return opt.lstrip('-').replace('-', '_')


def dests_for(cmd):
    """返回子命令全部 flag 的 dest 列表（供 cmd_run 构造转发 Namespace）。"""
    return [_dest_of(e) for e in _iter_plain(flags_for(cmd))]
