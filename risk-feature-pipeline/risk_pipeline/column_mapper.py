# -*- coding: utf-8 -*-
"""
字段映射器：将通用字段名映射到本行实际字段名

使用方式:
    from risk_pipeline.column_mapper import ColumnMapper
    mapper = ColumnMapper()                      # 使用默认映射
    mapper = ColumnMapper("config/my_bank.yaml") # 使用自定义映射

    mapper.customer_id   # -> "客户编号" 或 "CUST_NO"
    mapper.target        # -> "is_bad" 或 "DEFAULT_FLAG"
    mapper.qual_prefix   # -> "是_"
    mapper.segment_dims  # -> ["所属行业", "客户性质", ...]
"""
from .config_loader import load_column_mapping


class ColumnMapper:
    """字段映射器：将通用字段名映射到本行实际字段名"""

    def __init__(self, config_path=None):
        """
        参数:
            config_path: 字段映射配置文件路径（可选）。
                如果不提供，使用 config/column_mapping.yaml 默认值。
        """
        self._mapping = load_column_mapping(config_path)

    def get(self, dotted_key, default=None):
        """
        通过点分路径获取映射值

        例:
            mapper.get('required.customer_id')  # -> "客户编号"
            mapper.get('qualification.prefix')  # -> "是_"
        """
        parts = dotted_key.split('.')
        value = self._mapping
        for p in parts:
            if isinstance(value, dict) and p in value:
                value = value[p]
            else:
                return default
        return value

    # ---- 常用字段的快捷属性 ----

    @property
    def customer_id(self):
        """主键字段名"""
        return self.get('required.customer_id', '客户编号')

    @property
    def target(self):
        """目标变量字段名"""
        return self.get('required.target', 'is_bad')

    @property
    def segment_dims(self):
        """分群维度字段名列表（值列表）"""
        dims = self.get('segment_dims', {})
        return list(dims.values()) if isinstance(dims, dict) else dims

    @property
    def segment_dims_dict(self):
        """分群维度映射字典（维度名 -> 字段名）"""
        return self.get('segment_dims', {})

    @property
    def credit_category_dims(self):
        """征信分析的分群维度列表"""
        return self.get('credit_category_dims', [])

    @property
    def qual_prefix(self):
        """二值标签列的前缀"""
        return self.get('qualification.prefix', '是_')

    @property
    def qual_columns(self):
        """显式指定的二值标签列（如果有），否则返回 None"""
        return self.get('qualification.columns')

    @property
    def amount_cols(self):
        """金额字段列表"""
        return self.get('amount_cols', [])

    @property
    def numeric_skip_cols(self):
        """千分位修复时跳过的列"""
        return self.get('numeric_skip_cols', [])

    @property
    def finance_merge_dup_cols(self):
        """宽表合并时财务侧重复列"""
        return self.get('finance_merge_dup_cols', [])

    @property
    def report_date(self):
        """报告日期字段名"""
        return self.get('required.report_date', '报告日期')

    @property
    def customer_id_str(self):
        """主键字符串列名（派生：主键 + '_str'）"""
        return f"{self.customer_id}_str"

    @property
    def change_date(self):
        """最近变更日期字段名"""
        date_list = self.get('date_cols', [])
        if isinstance(date_list, list) and len(date_list) >= 2:
            return date_list[1]
        return '最近变更日期'

    @property
    def industry_data_cols(self):
        """产业属性数据列列表"""
        return self.get('industry_data_cols', ['客户分层', '细分赛道', '产业大类', '所属阶段', '赛道'])

    @property
    def segment_iv_limits(self):
        """分群IV分析唯一值上限（维度名 -> 上限数，null 表示不限）"""
        return self.get('segment_iv_limits', {})

    @property
    def credit_raw_features(self):
        """征信原始特征列表"""
        return self.get('credit_raw_features', [])

    @property
    def credit_derived_features(self):
        """征信衍生特征列表"""
        return self.get('credit_derived_features', [])

    def detect_qual_cols(self, df_columns, prefix_override=None):
        """
        从 DataFrame 列名中检测资质标签列

        优先使用显式列出的 columns，否则按 prefix 匹配。

        参数:
            df_columns: DataFrame 的列名列表（或 Index）
            prefix_override: 覆盖默认前缀

        返回:
            qual_cols: 排序后的资质标签列名列表
        """
        explicit = self.qual_columns
        if explicit:
            return sorted([c for c in explicit if c in df_columns])
        prefix = prefix_override if prefix_override is not None else self.qual_prefix
        return sorted([c for c in df_columns if c.startswith(prefix)])

    def strip_qual_prefix(self, col_name):
        """去掉资质标签列的前缀，返回显示名"""
        prefix = self.qual_prefix
        if col_name.startswith(prefix):
            return col_name[len(prefix):]
        return col_name
