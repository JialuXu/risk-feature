#!/usr/bin/env python3
"""配置驱动的风险衍生指标持续孵化流水线。

脚本读取字段资产字典、衍生模板库和候选指标生成规则，生成候选指标池、
评分清单、正式指标加工需求清单、规则中台适配清单和孵化闭环台账。
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
DEFAULT_CONFIG_DIR = Path("衍生指标设计/衍生指标持续孵化流水线")
DEFAULT_OUTPUT_DIR = DEFAULT_CONFIG_DIR / "auto_output"
DEFAULT_SOURCE_SCHEMA = Path("衍生指标设计/基础指标（已落地）/表字段清单.csv")

QUALITY_TEMPLATE_PREFIXES = ("TPL_QUALITY",)
PAIR_REQUIRED_TEMPLATES = {"TPL_RATIO_001", "TPL_RATIO_003", "TPL_COMBO_001", "TPL_COMBO_002", "TPL_SCORE_001"}
LOW_VALUE_ROLES = {"主键", "明细主键", "时间字段", "文本", "分群维度"}
LOW_VALUE_FIELD_KEYWORDS = (
    "名称",
    "姓名",
    "地址",
    "编号",
    "代码",
    "备注",
    "账号",
    "账户",
    "行号",
    "文号",
    "链接",
    "正文",
    "摘要",
)
HIGH_VALUE_FIELD_KEYWORDS = (
    "逾期",
    "不良",
    "关注",
    "违约",
    "欠税",
    "处罚",
    "冻结",
    "执行",
    "异常",
    "风险",
    "评级",
    "分类",
    "负债",
    "担保",
    "现金流",
    "到期",
    "余额",
    "敞口",
    "授信",
    "收入",
    "利润",
)

FIELD_ASSET_COLUMNS = [
    "字段资产编号",
    "主题域",
    "来源库名",
    "来源模式",
    "来源表英文名",
    "来源表中文名",
    "字段英文名",
    "字段中文名",
    "字段类型",
    "字段角色",
    "字段粒度",
    "时间属性",
    "主关联键",
    "可聚合",
    "可做分子",
    "可做分母",
    "可做窗口统计",
    "可做趋势变化",
    "可做时效计算",
    "可做规则配置",
    "建议衍生模板组",
    "风险方向建议",
    "空值含义建议",
    "质量检查规则",
]


@dataclass(frozen=True)
class FieldAsset:
    row: dict[str, str]

    @property
    def asset_id(self) -> str:
        return self.row.get("字段资产编号", "")

    @property
    def domain(self) -> str:
        return self.row.get("主题域", "")

    @property
    def table_en(self) -> str:
        return self.row.get("来源表英文名", "")

    @property
    def field_en(self) -> str:
        return self.row.get("字段英文名", "")

    @property
    def field_cn(self) -> str:
        return self.row.get("字段中文名", "")

    @property
    def role(self) -> str:
        return self.row.get("字段角色", "")

    @property
    def data_type(self) -> str:
        return self.row.get("字段类型", "")

    @property
    def grain(self) -> str:
        return self.row.get("字段粒度", "")

    @property
    def time_attr(self) -> str:
        return self.row.get("时间属性", "")

    @property
    def join_key(self) -> str:
        return self.row.get("主关联键", "")

    @property
    def risk_direction(self) -> str:
        return self.row.get("风险方向建议", "待判断")

    @property
    def rule_ready(self) -> bool:
        return is_yes(self.row.get("可做规则配置", ""))


@dataclass(frozen=True)
class Template:
    row: dict[str, str]

    @property
    def template_id(self) -> str:
        return self.row.get("模板编号", "")

    @property
    def name(self) -> str:
        return self.row.get("模板名称", "")

    @property
    def domains(self) -> str:
        return self.row.get("适用主题域", "")

    @property
    def roles(self) -> str:
        return self.row.get("适用字段角色", "")

    @property
    def types(self) -> str:
        return self.row.get("适用字段类型", "")

    @property
    def grains(self) -> str:
        return self.row.get("适用粒度", "")

    @property
    def name_rule(self) -> str:
        return self.row.get("生成指标名称规则", "")

    @property
    def formula(self) -> str:
        return self.row.get("加工公式模板", "")

    @property
    def window(self) -> str:
        return self.row.get("窗口参数", "")


def repair_unquoted_type_commas(row: list[str], expected_len: int) -> list[str]:
    """修复未加引号的 Hive 类型字段，例如 DECIMAL(30,2) 被拆成两列。"""
    repaired = list(row)
    i = 0
    while len(repaired) > expected_len and i < len(repaired) - 1:
        cell = repaired[i].strip()
        next_cell = repaired[i + 1].strip()
        if "(" in cell and ")" not in cell and ")" in next_cell:
            repaired[i] = f"{repaired[i]},{repaired[i + 1]}"
            del repaired[i + 1]
            continue
        i += 1
    return repaired


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows: list[dict[str, str]] = []
        for row in reader:
            if len(row) != len(header):
                row = repair_unquoted_type_commas(row, len(header))
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            if len(row) > len(header):
                row = row[: len(header) - 1] + [",".join(row[len(header) - 1 :])]
            rows.append(dict(zip(header, row)))
        return rows


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def is_yes(value: str) -> bool:
    return value.strip() in {"是", "Y", "y", "YES", "yes", "True", "true", "1"}


def tokens(value: str) -> list[str]:
    normalized = value.replace("、", "/").replace("|", "/").replace(",", "/")
    return [item.strip() for item in normalized.split("/") if item.strip()]


def is_numeric_type(data_type: str) -> bool:
    data_type = data_type.upper()
    return any(key in data_type for key in ("DECIMAL", "INT", "DOUBLE", "FLOAT", "NUMBER"))


def infer_domain(table_en: str, field_cn: str) -> str:
    text = f"{table_en}_{field_cn}".upper()
    if "FNC" in text or "FIN" in text or any(key in field_cn for key in ("资产", "负债", "利润", "收入", "现金流", "财务")):
        return "财务"
    if "PUB_OPINION" in text or "舆情" in field_cn:
        return "舆情"
    if "CRDTC" in text or "OTHER_CRDTC" in text or any(key in field_cn for key in ("征信", "机构数", "担保", "未结清")):
        return "征信"
    if "CRDT" in text or "LMT" in text or any(key in field_cn for key in ("授信", "额度", "敞口")):
        return "授信敞口"
    if "OVDUE" in text or "LEV5" in text or "RISK_LIST" in text or any(key in field_cn for key in ("逾期", "五级分类", "风险等级")):
        return "贷款风险"
    if "LON" in text or any(key in field_cn for key in ("贷款", "借据", "到期日", "利率")):
        return "贷款行为"
    if any(key in text for key in ("EXEC", "EQUITY", "PENAL", "JUSTICE", "TAX", "OPER_EXCEP", "SERIOUS_ILLEGAL", "LOST_CRDT")):
        return "工商司法"
    if "WARN_SIGNAL" in text or "RULE" in text or any(key in field_cn for key in ("预警", "规则", "反馈")):
        return "预警反馈"
    if "BASIC_INFO" in text or any(key in field_cn for key in ("行业", "企业规模", "客户性质", "成立日期")):
        return "客户主数据"
    return "通用"


def infer_role(field_en: str, field_cn: str, field_type: str) -> str:
    en = field_en.upper()
    cn = field_cn
    type_upper = field_type.upper()
    if en in {"CUST_NO", "LP_ORG_NO", "LON_NO", "LMT_NO", "CASE_NO", "RULE_NO", "SIGNAL_NO"} or "编号" in cn:
        return "主键"
    if "DATE" in type_upper or type_upper == "DATE" or en.endswith("_DT") or "TIME" in en or any(key in cn for key in ("日期", "时间", "报告期", "公布日", "发布时间")):
        if any(key in cn for key in ("处理时间", "数据日期", "分区")) or en in {"ETL_DT", "ETL_TIMESTAMP", "PART_YMD", "PART_YM"}:
            return "时间字段"
        return "事件日期" if any(key in cn for key in ("处罚", "逾期", "变动", "列入", "冻结", "公布", "发布", "下发")) else "日期"
    if any(key in cn for key in ("是否", "标识", "状态", "有效")) or en.startswith("IS_") or en.endswith("_FLG") or en.endswith("_FLAG"):
        return "标识"
    if any(key in cn for key in ("等级", "评级", "分类", "信号等级")):
        return "等级"
    if any(key in cn for key in ("标签", "类型", "类别", "行业", "性质", "规模")):
        return "标签" if "标签" in cn else "分群维度"
    if any(key in cn for key in ("次数", "笔数", "数量", "机构数", "公司数", "天数", "期限")):
        return "次数" if "天数" not in cn else "天数"
    if any(key in cn for key in ("比例", "占比", "率", "比率")):
        return "比例"
    if any(key in cn for key in ("金额", "余额", "资产", "负债", "收入", "利润", "资本", "估值", "现金流")):
        return "余额" if "余额" in cn else "金额"
    if is_numeric_type(field_type):
        return "数值"
    return "文本"


def infer_grain(table_en: str, role: str) -> str:
    text = table_en.upper()
    if any(key in text for key in ("OVDUE", "CHG", "PUB_OPINION", "EXEC", "EQUITY", "PENAL", "JUSTICE", "TAX", "OPER_EXCEP", "WARN_SIGNAL")):
        return "客户事件"
    if any(key in text for key in ("LON_BAL", "LON_INFO", "BW_CRDT", "LMT_INFO")):
        return "贷款明细" if "LON" in text or "BW_CRDT" in text else "额度明细"
    if "FNC_IDX" in text:
        return "客户报表期"
    if "CRDTC" in text:
        return "客户报告快照"
    if role == "主键":
        return "主键字段"
    return "客户快照"


def infer_time_attr(field_en: str, field_cn: str, role: str) -> str:
    en = field_en.upper()
    if role in {"事件日期", "日期", "时间字段"}:
        return "事件日期" if role == "事件日期" else "业务日期"
    if "REPORT_TERM" in en:
        return "报告期"
    if "REPORT_DATE" in en:
        return "报告日期"
    if en in {"ETL_DT", "PART_YMD", "PART_YM"}:
        return "分区日期"
    return "依赖表级时间字段"


def infer_join_key(table_en: str) -> str:
    text = table_en.upper()
    if "LON" in text:
        return "LP_ORG_NO+CUST_NO+LON_NO"
    if "LMT" in text:
        return "LP_ORG_NO+CUST_NO+LMT_NO"
    if any(key in text for key in ("EXEC", "JUSTICE", "TAX", "EQUITY", "PENAL", "OPER_EXCEP")):
        return "LP_ORG_NO+CUST_NO+事件ID"
    if "WARN_SIGNAL" in text:
        return "LP_ORG_NO+CUST_NO+SIGNAL_NO"
    return "LP_ORG_NO+CUST_NO"


def yes_no(value: bool) -> str:
    return "是" if value else "否"


def infer_capabilities(role: str, field_type: str) -> dict[str, str]:
    numeric = is_numeric_type(field_type)
    aggregatable = role in {"金额", "余额", "次数", "天数", "比例", "等级", "数值"}
    event_like = role in {"事件日期", "日期", "标签", "标识", "等级", "金额", "余额", "次数"}
    return {
        "可聚合": yes_no(aggregatable),
        "可做分子": yes_no(role in {"金额", "余额", "次数", "天数", "比例", "等级", "数值"}),
        "可做分母": yes_no(role in {"金额", "余额", "次数", "数值"} and numeric),
        "可做窗口统计": yes_no(event_like),
        "可做趋势变化": yes_no(role in {"金额", "余额", "次数", "天数", "比例", "等级", "数值"}),
        "可做时效计算": yes_no(role in {"事件日期", "日期"}),
        "可做规则配置": yes_no(role in {"金额", "余额", "次数", "天数", "比例", "等级", "标签", "标识", "事件日期"}),
    }


def infer_template_group(role: str) -> str:
    mapping = {
        "金额": "金额水平/占比/变化/窗口合计模板",
        "余额": "余额汇总/结构占比/变化模板",
        "次数": "次数水平/窗口频次/趋势变化模板",
        "天数": "最大值/时效/阈值模板",
        "比例": "比例水平/变化/阈值模板",
        "等级": "最高等级/等级分布模板",
        "标签": "标签计数/标签大类/占比模板",
        "标识": "是否发生/标识余额占比模板",
        "事件日期": "事件频次/最近距今/当前有效模板",
        "日期": "时效/年龄/期限模板",
    }
    return mapping.get(role, "数据质量/观察模板")


def infer_risk_direction(role: str, field_cn: str) -> str:
    if role in {"主键", "时间字段", "分群维度", "文本"}:
        return "中性"
    if any(key in field_cn for key in ("流动比率", "速动比率", "现金比率", "覆盖", "偿债能力")):
        return "越低风险越高"
    if any(key in field_cn for key in ("逾期", "不良", "关注", "欠税", "处罚", "冻结", "执行", "异常", "违约", "负债", "担保", "非银", "到期", "下调")):
        return "越高风险越高"
    if role in {"金额", "余额", "次数", "天数", "比例", "等级", "标识", "事件日期"}:
        return "按业务含义判断"
    return "中性"


def infer_null_meaning(role: str) -> str:
    if role in {"事件日期", "标签", "标识"}:
        return "无事件或未采集需区分"
    if role in {"金额", "余额", "次数"}:
        return "无记录、0值和缺失需区分"
    if role in {"比例", "等级"}:
        return "无法计算或未采集"
    return "未维护或不适用"


def infer_quality_rule(role: str, field_type: str) -> str:
    if role == "主键":
        return "非空和唯一性校验"
    if role in {"金额", "余额"}:
        return "金额非负和极端值校验"
    if role in {"次数", "天数"}:
        return "非负整数校验"
    if role == "比例":
        return "比例合理范围校验"
    if role in {"日期", "事件日期", "时间字段"}:
        return "日期格式和不晚于观察日校验"
    if role in {"标签", "等级", "标识", "分群维度"}:
        return "枚举值字典校验"
    if is_numeric_type(field_type):
        return "数值范围校验"
    return "空值率和文本长度校验"


def initialize_field_dict(source_schema: Path, output_path: Path) -> list[dict[str, str]]:
    source_rows = read_csv(source_schema)
    rows: list[dict[str, str]] = []
    domain_counts: dict[str, int] = {}
    for source in source_rows:
        table_en = source.get("表英文名", "")
        field_en = source.get("字段英文名", "")
        field_cn = source.get("字段中文名", "")
        field_type = source.get("字段类型", "")
        domain = infer_domain(table_en, field_cn)
        role = infer_role(field_en, field_cn, field_type)
        prefix = domain_prefix(domain)
        domain_counts[prefix] = domain_counts.get(prefix, 0) + 1
        capabilities = infer_capabilities(role, field_type)
        row = {
            "字段资产编号": f"FD_{prefix}_{domain_counts[prefix]:04d}",
            "主题域": domain,
            "来源库名": source.get("数据库英文名", ""),
            "来源模式": source.get("模式英文名", ""),
            "来源表英文名": table_en,
            "来源表中文名": "",
            "字段英文名": field_en,
            "字段中文名": field_cn,
            "字段类型": field_type,
            "字段角色": role,
            "字段粒度": infer_grain(table_en, role),
            "时间属性": infer_time_attr(field_en, field_cn, role),
            "主关联键": infer_join_key(table_en),
            "建议衍生模板组": infer_template_group(role),
            "风险方向建议": infer_risk_direction(role, field_cn),
            "空值含义建议": infer_null_meaning(role),
            "质量检查规则": infer_quality_rule(role, field_type),
        }
        row.update(capabilities)
        rows.append(row)
    write_csv(output_path, rows, FIELD_ASSET_COLUMNS)
    return rows


def domain_matches(field: FieldAsset, template: Template) -> bool:
    domain_tokens = tokens(template.domains)
    return "通用" in domain_tokens or field.domain in domain_tokens


def role_matches(field: FieldAsset, template: Template) -> bool:
    role_tokens = tokens(template.roles)
    if "任意" in role_tokens or "通用" in role_tokens:
        return True
    if field.role in role_tokens:
        return True
    if "数值型" in role_tokens and is_numeric_type(field.data_type):
        return True
    if "事件日期" in role_tokens and field.role in {"事件日期", "日期"}:
        return True
    return False


def type_matches(field: FieldAsset, template: Template) -> bool:
    type_tokens = tokens(template.types)
    if not type_tokens or "任意" in type_tokens:
        return True
    if "数值型" in type_tokens and is_numeric_type(field.data_type):
        return True
    if any(token in field.data_type.upper() for token in type_tokens):
        return True
    if field.role in type_tokens:
        return True
    return False


def grain_matches(field: FieldAsset, template: Template) -> bool:
    grain_tokens = tokens(template.grains)
    return not grain_tokens or any(token in field.grain for token in grain_tokens)


def template_matches(field: FieldAsset, template: Template) -> bool:
    return (
        domain_matches(field, template)
        and role_matches(field, template)
        and type_matches(field, template)
        and grain_matches(field, template)
    )


def is_quality_template(template: Template) -> bool:
    return template.template_id.startswith(QUALITY_TEMPLATE_PREFIXES)


def requires_field_pair(template: Template) -> bool:
    return template.template_id in PAIR_REQUIRED_TEMPLATES


def is_low_value_field(field: FieldAsset) -> bool:
    if field.role in LOW_VALUE_ROLES:
        return True
    if any(keyword in field.field_cn for keyword in LOW_VALUE_FIELD_KEYWORDS):
        return not any(keyword in field.field_cn for keyword in HIGH_VALUE_FIELD_KEYWORDS)
    return False


def is_high_value_field(field: FieldAsset) -> bool:
    return any(keyword in field.field_cn for keyword in HIGH_VALUE_FIELD_KEYWORDS)


def is_rendered(row: dict[str, str]) -> bool:
    text = "|".join(row.values())
    return "{" not in text and "}" not in text


def has_self_division(row: dict[str, str]) -> bool:
    formula = row.get("加工公式草案", "") or row.get("加工公式", "")
    if "分子" not in formula or "分母" not in formula:
        return False
    compact = formula.replace(" ", "")
    if "/" not in compact:
        return False
    left, right = compact.split("/", 1)
    left = left.replace("分子", "")
    right = right.replace("分母", "")
    return left and left == right


def is_valid_candidate(row: dict[str, str]) -> bool:
    return is_rendered(row) and not has_self_division(row)


def render_name(template: Template, field: FieldAsset) -> str:
    name = template.name_rule or f"{field.field_cn}_{template.name}"
    replacements = {
        "{字段中文名}": field.field_cn,
        "{事件中文名}": field.field_cn,
        "{金额字段中文名}": field.field_cn,
        "{等级字段中文名}": field.field_cn,
        "{指标中文名}": field.field_cn,
        "{分子字段中文名}": field.field_cn,
        "{分母字段中文名}": "可比基准",
        "{N}": "12",
        "{X}": "高",
        "{标签大类}": "重点风险类",
        "{主体类型}": "自身",
        "{条件类别}": "重点类别",
        "{维度中文名}": field.field_cn,
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    return name


def render_formula(template: Template, field: FieldAsset) -> str:
    formula = template.formula or f"按{template.name}加工{field.field_cn}"
    replacements = {
        "字段值": field.field_en,
        "字段": field.field_en,
        "目标字段": field.field_en,
        "金额字段": field.field_en,
        "事件日期": field.field_en,
        "等级字段": field.field_en,
        "事件ID": "事件唯一键",
        "观察日": "snapshot_date",
        "{N}": "12",
    }
    for old, new in replacements.items():
        formula = formula.replace(old, new)
    return formula


def default_window(template: Template) -> str:
    window = template.window
    if "N=" in window:
        return "近12个月"
    if "最近一期" in window:
        return "最近一期"
    if "当前期" in window:
        return "当前期"
    if "历史累计" in window:
        return "历史累计"
    return window.split("/")[0] if window else "待定"


def infer_indicator_type(template: Template) -> str:
    text = f"{template.name}{template.template_id}"
    if any(key in text for key in ("占比", "结构", "集中度", "Top")):
        return "结构类"
    if any(key in text for key in ("变化", "同比", "较上一", "近窗")):
        return "变化类"
    if any(key in text for key in ("次数", "事件频次", "计数")):
        return "事件频次类"
    if any(key in text for key in ("距今", "当前有效", "时效")):
        return "时效类"
    if "标识" in text:
        return "规则标识类"
    if any(key in text for key in ("加权", "强度", "金额合计", "分")):
        return "强度类"
    return "水平类"


def domain_prefix(domain: str) -> str:
    mapping = {
        "财务": "FIN",
        "征信": "CRD",
        "授信敞口": "CRD",
        "贷款行为": "LOAN",
        "贷款风险": "LOAN",
        "舆情": "OPN",
        "工商司法": "BIZ",
        "风险名单": "RISK",
        "预警反馈": "RISK",
        "客户主数据": "CUST",
    }
    return mapping.get(domain, "GEN")


def rule_potential(field: FieldAsset, indicator_type: str) -> str:
    if not field.rule_ready or field.risk_direction == "中性":
        return "低"
    if field.risk_direction == "按业务含义判断" and not is_high_value_field(field):
        return "低"
    if field.risk_direction == "按业务含义判断":
        return "中"
    if indicator_type in {"规则标识类", "时效类", "事件频次类", "结构类"}:
        return "高"
    return "中"


def candidate_status(potential: str) -> str:
    if potential == "高":
        return "规则候选"
    if potential == "中":
        return "候选"
    return "观察"


def generate_candidates(fields: list[FieldAsset], templates: list[Template], max_per_field: int, include_quality: bool) -> list[dict[str, str]]:
    counters: dict[str, int] = {}
    candidates: list[dict[str, str]] = []
    for field in fields:
        if field.role in {"主键", "明细主键", "时间字段"} or is_low_value_field(field):
            continue
        matches = [
            template
            for template in templates
            if template_matches(field, template)
            and (include_quality or not is_quality_template(template))
            and not requires_field_pair(template)
        ]
        for template in matches[:max_per_field]:
            prefix = domain_prefix(field.domain)
            counters[prefix] = counters.get(prefix, 0) + 1
            indicator_type = infer_indicator_type(template)
            potential = rule_potential(field, indicator_type)
            row = {
                "候选指标编号": f"AUTO_{prefix}_{counters[prefix]:03d}",
                "候选指标名称": render_name(template, field),
                "主题域": field.domain,
                "生成规则编号": "AUTO_MATCH",
                "匹配模板编号": template.template_id,
                "来源字段资产编号": field.asset_id,
                "来源表英文名": field.table_en,
                "来源字段英文名": field.field_en,
                "指标类型": indicator_type,
                "统计窗口": default_window(template),
                "加工公式草案": render_formula(template, field),
                "风险方向": field.risk_direction,
                "规则适配潜力": potential,
                "候选状态": candidate_status(potential),
                "进入正式需求条件": "覆盖率、稳定性、业务解释和规则可配置性通过评分门槛",
            }
            if is_valid_candidate(row):
                candidates.append(row)
    return candidates


def generate_scores(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for idx, candidate in enumerate(candidates, start=1):
        potential = candidate["规则适配潜力"]
        conclusion = "规则候选" if potential == "高" else "候选" if potential == "中" else "观察"
        rows.append(
            {
                "评分记录编号": f"AUTO_SCORE_{idx:04d}",
                "候选指标编号": candidate["候选指标编号"],
                "候选指标名称": candidate["候选指标名称"],
                "主题域": candidate["主题域"],
                "验证批次": "待验证",
                "验证样本范围": "待计算",
                "目标标签口径": "未来6个月逾期或分类下调或风险名单纳入",
                "覆盖率": "待计算",
                "缺失率": "待计算",
                "异常值比例": "待计算",
                "IV值": "待计算",
                "相关性方向": "待计算",
                "LR系数方向": "待计算",
                "坏客户覆盖率": "待计算",
                "规则命中率": "待计算",
                "误报率": "待计算",
                "业务解释性评级": "待人工确认",
                "规则可配置性评级": potential,
                "综合评分": "待计算",
                "分层结论": conclusion,
                "建议动作": "历史回测" if potential != "低" else "暂入观察池",
                "进入正式需求原因或暂缓原因": candidate["进入正式需求条件"],
            }
        )
    return rows


def select_formal_candidates(candidates: list[dict[str, str]], max_formal: int) -> list[dict[str, str]]:
    priority = {"高": 0, "中": 1, "低": 2}
    eligible = [
        row
        for row in candidates
        if row["规则适配潜力"] in {"高", "中"}
        and is_valid_candidate(row)
        and not row["候选指标名称"].endswith("_是否缺失")
    ]
    return sorted(eligible, key=lambda row: (priority.get(row["规则适配潜力"], 9), row["候选指标编号"]))[:max_formal]


def generate_formal_demands(candidates: list[dict[str, str]], batch_id: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for idx, candidate in enumerate(candidates, start=1):
        prefix = domain_prefix(candidate["主题域"])
        rows.append(
            {
                "批次号": batch_id,
                "指标版本": "V1",
                "指标编码": f"{prefix}{idx:03d}",
                "指标名称": candidate["候选指标名称"],
                "来源候选指标编号": candidate["候选指标编号"],
                "主题域": candidate["主题域"],
                "指标类型": candidate["指标类型"],
                "适用对象": "对公客户",
                "指标粒度": "客户级",
                "统计窗口": candidate["统计窗口"],
                "刷新频率": "月度",
                "来源表英文名": candidate["来源表英文名"],
                "来源字段英文名": candidate["来源字段英文名"],
                "关联键": "LP_ORG_NO+CUST_NO",
                "时间字段": "按字段资产字典配置",
                "过滤条件": "取观察日之前有效数据，避免使用未来信息",
                "加工公式": candidate["加工公式草案"],
                "逻辑详细说明": "由字段资产字典和衍生模板库自动生成，提交开发前需业务复核。",
                "风险方向": candidate["风险方向"],
                "是否规则候选": "是" if candidate["规则适配潜力"] == "高" else "否",
                "规则配置建议": "按历史验证结果确定比较符和阈值" if candidate["规则适配潜力"] != "低" else "暂不建议直接配置规则",
                "验收口径": "核对来源字段、窗口边界、空值处理和样本抽查结果",
                "状态": "待开发" if candidate["规则适配潜力"] == "高" else "待复核",
            }
        )
    return rows


def generate_rule_adapters(demands: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for idx, demand in enumerate([row for row in demands if row["是否规则候选"] == "是"], start=1):
        compare = "=" if "标识" in demand["指标类型"] else ">=" if "越高" in demand["风险方向"] else "<="
        threshold = "1" if compare == "=" else "待历史验证"
        rows.append(
            {
                "规则编号": f"AUTO_RENG_{idx:04d}",
                "规则名称": f"{demand['指标名称']}规则",
                "来源指标编码": demand["指标编码"],
                "来源候选指标编号": demand["来源候选指标编号"],
                "规则类型": "单指标阈值规则" if demand["指标类型"] != "变化类" else "趋势突变规则",
                "触发对象": "客户",
                "观察期": demand["统计窗口"],
                "比较符": compare,
                "阈值口径": threshold,
                "阈值来源": "历史验证+业务经验",
                "触发频率": demand["刷新频率"],
                "冷却期": "30天",
                "风险等级": "待验证",
                "是否下发": "待定",
                "是否人工确认": "是",
                "规则表达式草案": f"{demand['指标编码']} {compare} {threshold}",
                "处置建议": "由业务方根据命中客户清单确认处置动作",
                "试运行状态": "待试运行",
                "反馈回流字段": "命中结果/下发结果/人工认定/解除状态/误报原因",
            }
        )
    return rows


def generate_ledgers(demands: list[dict[str, str]], rules: list[dict[str, str]], batch_id: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for idx, demand in enumerate(demands, start=1):
        rows.append(
            {
                "台账编号": f"AUTO_LEDGER_IND_{idx:04d}",
                "对象类型": "指标",
                "对象编号": demand["指标编码"],
                "对象名称": demand["指标名称"],
                "当前阶段": demand["状态"],
                "来源批次": batch_id,
                "进入时间": "待定",
                "最近验证时间": "待定",
                "最近试运行时间": "待定",
                "累计验证次数": "0",
                "累计试运行次数": "0",
                "累计命中客户数": "待计算",
                "累计下发客户数": "待计算",
                "人工认定风险数": "待计算",
                "解除或误报数": "待计算",
                "坏客户覆盖率": "待计算",
                "误报率": "待计算",
                "稳定性结论": "待验证",
                "业务反馈摘要": "待业务反馈",
                "状态调整规则": "验证通过则进入规则候选或正式开发；误报高则降级观察",
                "下一阶段动作": "补充历史样本验证",
                "责任角色": "业务方+数据团队",
                "备注": "自动生成台账",
            }
        )
    offset = len(rows)
    for idx, rule in enumerate(rules, start=1):
        rows.append(
            {
                "台账编号": f"AUTO_LEDGER_RULE_{idx + offset:04d}",
                "对象类型": "规则",
                "对象编号": rule["规则编号"],
                "对象名称": rule["规则名称"],
                "当前阶段": rule["试运行状态"],
                "来源批次": batch_id,
                "进入时间": "待定",
                "最近验证时间": "待定",
                "最近试运行时间": "待定",
                "累计验证次数": "0",
                "累计试运行次数": "0",
                "累计命中客户数": "待计算",
                "累计下发客户数": "待计算",
                "人工认定风险数": "待计算",
                "解除或误报数": "待计算",
                "坏客户覆盖率": "待计算",
                "误报率": "待计算",
                "稳定性结论": "待验证",
                "业务反馈摘要": "待业务反馈",
                "状态调整规则": "连续试运行稳定且误报可控则升级正式规则",
                "下一阶段动作": "配置规则中台试运行",
                "责任角色": "业务方+风险中台",
                "备注": "自动生成规则台账",
            }
        )
    return rows


def run(args: argparse.Namespace) -> None:
    config_dir = Path(args.config_dir)
    output_dir = Path(args.output_dir)
    initialized_field_dict = config_dir / "字段资产字典_自动初始化.csv"

    if args.init_field_dict:
        source_schema = Path(args.source_schema)
        initialized_rows = initialize_field_dict(source_schema, initialized_field_dict)
        print(f"已从原始字段清单初始化字段资产: {len(initialized_rows)}")
        print(f"字段资产字典初稿: {initialized_field_dict}")
        if args.init_only:
            return

    field_dict_path = Path(args.field_dict) if args.field_dict else initialized_field_dict if args.init_field_dict else config_dir / "字段资产字典.csv"
    fields = [FieldAsset(row) for row in read_csv(field_dict_path)]
    templates = [Template(row) for row in read_csv(config_dir / "衍生模板库.csv")]

    candidates = generate_candidates(fields, templates, args.max_templates_per_field, args.include_quality_indicators)
    scores = generate_scores(candidates)
    formal_candidates = select_formal_candidates(candidates, args.max_formal)
    demands = generate_formal_demands(formal_candidates, args.batch_id)
    rules = generate_rule_adapters(demands)
    ledgers = generate_ledgers(demands, rules, args.batch_id)

    write_csv(output_dir / "候选指标池_自动生成.csv", candidates, list(candidates[0].keys()) if candidates else [])
    write_csv(output_dir / "候选指标评分清单_自动生成.csv", scores, list(scores[0].keys()) if scores else [])
    write_csv(output_dir / "正式指标加工需求清单_自动生成.csv", demands, list(demands[0].keys()) if demands else [])
    write_csv(output_dir / "规则中台适配清单_自动生成.csv", rules, list(rules[0].keys()) if rules else [])
    write_csv(output_dir / "指标孵化闭环台账_自动生成.csv", ledgers, list(ledgers[0].keys()) if ledgers else [])

    print(f"已生成候选指标: {len(candidates)}")
    print(f"已生成正式需求: {len(demands)}")
    print(f"已生成规则候选: {len(rules)}")
    print(f"输出目录: {output_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成风险衍生指标持续孵化流水线输出")
    parser.add_argument("--config-dir", default=str(DEFAULT_CONFIG_DIR), help="配置CSV所在目录")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="自动生成结果输出目录")
    parser.add_argument("--source-schema", default=str(DEFAULT_SOURCE_SCHEMA), help="原始Hive表字段清单CSV")
    parser.add_argument("--field-dict", default="", help="指定字段资产字典CSV；不指定时使用配置目录下字段资产字典.csv")
    parser.add_argument("--init-field-dict", action="store_true", help="先从原始表字段清单自动初始化字段资产字典")
    parser.add_argument("--init-only", action="store_true", help="只初始化字段资产字典，不继续生成指标")
    parser.add_argument("--batch-id", default="BATCH_AUTO_001", help="输出批次号")
    parser.add_argument("--max-templates-per-field", type=int, default=3, help="每个字段最多匹配的模板数量")
    parser.add_argument("--max-formal", type=int, default=50, help="进入正式需求清单的最大指标数量")
    parser.add_argument("--include-quality-indicators", action="store_true", help="包含字段缺失、异常值等数据质量类候选指标")
    return parser


if __name__ == "__main__":
    run(build_parser().parse_args())
