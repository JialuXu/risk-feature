# `trigger` —— 客户级风险落地的唯一合法入口（→ Level 2）

**先过阻断节点 2**（见 [blocking-gates.md](../blocking-gates.md)）：默认/自定义
features 都必须 `--confirmed`；默认特征匹配率守门 70% 的单一真源也在那张卡。

```bash
# 默认 RISK_FEATURES_GSFC 配置（用户已确认数据为工商财务主题）
python -m risk_pipeline trigger --project <项目名> \
  --use-default-features --confirmed

# 项目专属特征配置（用户已确认每个特征的方向和 IV；非 GSFC 主题必走这条）
python -m risk_pipeline trigger --project <项目名> \
  --features-file project_features.json --confirmed
```

`project_features.json` 必须是 JSON 数组，每条特征至少含：

```json
[
  {"report_name": "feat_name", "source_col": "源列名",
   "risk_direction": "positive|negative", "iv": 0.5,
   "category": "分类", "scope": "full"}
]
```

模板：`risk_trigger_extraction/examples/features_template_generic.json`。

产物三张表（`output/<project>/`）：`_风险触碰明细_宽表.csv` / `_长表.csv` / `_触碰阈值说明.csv`。

## 雷区

- 前置 Level 1（先 export），否则 exit 1。
- `--use-default-features` 仅 GSFC（工商财务）主题适用；其它主题必须 `--features-file`。
- 输出宽表默认剔除 `is_bad`/`企业规模` 等元信息列防 merge 冲突；
  需保留传 `--keep-metadata-cols 企业规模,...`。
- 修改底层宽表后必须重新 trigger，否则名单与数据失去一致性（见 levels.md）。
