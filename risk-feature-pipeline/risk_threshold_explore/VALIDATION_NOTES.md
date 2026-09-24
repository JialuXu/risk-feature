# risk_threshold_explore — 实测验证笔记 + 已知问题

> 验证日期：2026-05-12  
> 数据：`/Volumes/Xujl/Skill/data/raw/`（舆情特征宽表 ⨝ 客户信息含评级；883 行 × 374 列 / 102 坏客户）  
> 平台：macOS 14（Darwin 25.4.0）+ Python 3.12.13

## ✅ 修复状态（2026-05-12 第二轮）

所有 4 个 bug + 3 个语义改进**已修复**。下方各项前的 ✅ 表示已落地。详见 `~/.claude/plans/optbinning-cli-plan-distributed-tarjan.md` 修复方案与各文件 diff。

## 1. 验证步骤与结果

| 阶段 | 命令 | 结果 |
|---|---|---|
| Level 1 | `run --pipeline generic` | ✅ OK，14 个文件落盘 |
| 候选探索 | `explore_thresholds --pairs-file pairs_youqing.csv`（10 个 pair） | ✅ OK，1.67s；evaluated=4，valid=1，skipped=6 |
| audit 合并 | 自动 | ✅ 原 `project_name / level / iv_overfit_features / unstable_rules` 全部保留；新增 `threshold_candidates` 节点 |
| state | 自动 | ✅ 未推进 level；history 末位是 `explore_thresholds` |
| query 兼容性 | `query --kind lr --dim 控股类型 --group 私人控股` | ✅ 不受影响 |
| 可视化 | `visualize --kinds thresholds` | ⚠️ 图能出（4 张 binning + 2 张 summary），但有 **2 个渲染 bug**（见下） |

---

## 2. Bug 清单（按严重度排序）

### ✅ 🔴 BUG-1 ｜ chart_threshold.py 用 inf 上界判断颜色，导致高风险柱误涂为低风险蓝（已修）

- **现象**：`风险标签_信贷逾期_数量 > 0.5` 这条规则（4.93x，规则有效=True），分箱图里**两根柱都是蓝色** (`#2E86C1` POS_COLOR)。应当：高风险侧（n=31，坏率 67.7%）= 红色。
- **根因**：`chart_threshold.py:101-105` 用 `np.isfinite(upp) and upp > cutoff` 判颜色。当 bin 是 `[0.50, inf)` 时 `upp=inf`，`np.isfinite(inf)=False` 短路成 False → 走 else 分支涂蓝。
- **建议修复**：改用 lo 下界 + 方向：
  ```python
  for lo, hi, _ in [_parse_bin_bounds(b) for b in bins]:
      is_high = (lo >= cutoff) if direction == 'positive' else (hi <= cutoff)
      colors.append(NEG_COLOR if is_high else POS_COLOR)
  ```
- **影响**：仅可视化误导；CSV / audit 中风险方向与候选阈值数据**正确**。
- **优先级**：高（直接误导业务人员视觉读图）

### ✅ 🟡 BUG-2 ｜ visualize 子命令把已生成的 `thresholds` 误报为 skipped（已修）

- **现象**：`charts=thresholds_binning:4, thresholds_summary:2`（已成功）和 `skipped=thresholds（缺对应 CSV/规则）` 同时出现。
- **根因**：`visualize.py:741` 的 stamp 用 `set(kinds) - set(result_paths.keys())` 算 skipped。我注册时 key 用了拆分的 `thresholds_binning / thresholds_summary`，但 `kinds` 里是 `thresholds` 单名 → 集合差永远命中。
- **建议修复**：在 `visualize.py` 的分发块同时注册一个聚合 key：
  ```python
  if 'thresholds' in kinds:
      bin_paths = chart_threshold_binning(...)
      sum_paths = chart_threshold_summary(...)
      _record('thresholds_binning', bin_paths)
      _record('thresholds_summary', sum_paths)
      if bin_paths or sum_paths:
          out['thresholds'] = []  # 占位，让 stamp 不再误报
  ```
  或更简单：让 stamp 用 `key.startswith(k)` 模糊匹配。
- **影响**：用户看到 "skipped" 警示会误以为没出图；实际产物都在。
- **优先级**：中

### ✅ 🟡 BUG-3 ｜ chart_threshold 标题用 ✓/✗，多数中文字体不含这两个字符（已修）

- **现象**：日志连续 8 条 `UserWarning: Glyph 10003 (CHECK MARK) missing from font(s) STHeiti.`；图标题里 `✓有效` 渲染成 `□有效`（方框）。
- **根因**：`chart_threshold.py:130`：`valid_tag = '✓有效' if valid else '✗未通过门槛'`。`STHeiti` / Linux 默认 `WenQuanYi Zen Hei` / `Noto Sans CJK` 都不含 U+2713 / U+2717。
- **建议修复**：换 ASCII 等价 — `'[有效]' / '[未通过]'`，或用中文「合」「否」。
- **影响**：纯视觉；不阻断生成。
- **优先级**：低（Linux 上几乎肯定也复现）

### ✅ 🟢 BUG-4 ｜ 候选阈值表「不通过原因」空值在 CSV 读出后变 NaN（已修）

- **现象**：`规则有效=True` 那行的 `不通过原因` 列在 CSV 重读后是 `NaN`（不是空字符串）。
- **根因**：pandas `to_csv` 把 `''` 写成空字段，`read_csv` 默认把空字段读成 `NaN`。
- **建议修复**：写盘时用 `to_csv(..., na_rep='')`；或读盘时 `fillna({'不通过原因': ''})`。
- **影响**：下游脚本若用 `df['不通过原因'].str.contains(...)` 会爆 `AttributeError`，但目前链路内部没有这类调用。
- **优先级**：低

---

## 3. 设计语义需要在文档讲清的点

### ✅ NOTE-1 ｜ 用「全样本 IV」做门槛会漏「分群强但全样本弱」的特征（已修：分群 IV 优先 + IV来源列）

- **实测**：`风险标签_信贷逾期_占比` 在「私人控股」分群下 IV=0.75 可信，但**全样本** IV=0（高度零集中、全样本拿不出有效分箱）。当前判定 `MIN_IV_FULL=0.02` → `不通过原因='全局IV < 0.02'`，规则被打成 invalid。
- **业务侧**：这条规则其实**风险倍数=5.11、p=0、触警率 7.6%**，非常强。被门槛误杀。
- **建议**：把「全局IV」门槛改为「该 segment 下 IV」门槛（从 `iv_group_all` 查），更贴合"分群规则"的语义；或同时记录两个 IV，让规则有效用 `max(iv_full, iv_group)`。
- **优先级**：高（影响默认结论质量）

### ✅ NOTE-2 ｜ zero-inflated count 特征 + min_bin_size=0.05 易被 optbinning 判「无有效分箱」（已修：兜底 + CLI `--min-bin-size`）

- **实测**：`传导舆情_信贷逾期_数量` 在私人控股分群下：395 个样本，377 个 0、14 个 1、4 个 2 — 非零占比 4.6%，**刚好低于 `min_bin_size=0.05`** → optbinning 给出 `splits=[]` → skip。但这恰好是高 IV 特征（0.79）。
- **业务侧**：损失了能直接当规则的"非零即风险"型特征。
- **建议**：
  - 在 `OPTBIN_PARAMS` 里把 `min_bin_size` 降到 0.03（或暴露为 CLI flag）；
  - 失败后兜底：若该特征 ≥ 80% 是某常值（多半是 0），自动用「>常值」作为切点重算一次；
  - 至少在 audit 里记下"零集中度过高"原因而不是笼统的"无有效分箱"。
- **优先级**：中

### ✅ NOTE-3 ｜ `Bin (Count %)` 等列名带空格/括号，未汉化（已修：_OPTBIN_RENAME + drop JS）

- 分箱明细 CSV 里仍是 optbinning 原生英文列：`Bin / Count / Count (%) / Non-event / Event / Event rate / WoE / IV / JS`。
- 我代码只 prepend 了 `分群维度/分群名称/特征` 和 append `是否候选阈值边界`，没改 optbinning 默认列名。
- 建议给定一个 rename mapping，统一中文化（与全局风格一致：`样本数 / 占比 / 好客户数 / 坏客户数 / 坏率 / WoE / IV分量`）。
- **优先级**：低（数据正确，纯命名一致性）

---

## 4. Linux 移植注意点（未来在其它 agent 安装）

### A. 依赖与安装

| 项 | 状态 | 备注 |
|---|---|---|
| `optbinning>=0.19` | ✅ 已写入 `pyproject.toml [project] dependencies` | 0.21 在 macOS 装好。Linux 装时会带 `cvxpy / ortools / scipy / matplotlib` 等较重 C 扩展，**首次 `pip install` 可能 60-120 秒**；建议 Docker 时单独一层加速重建 |
| Python `>=3.10` | ✅ pyproject 已要求 | Linux 上 3.10/3.11/3.12 都验过 ortools，3.13 暂不被 optbinning 0.21 支持 |
| PEP 668 锁定环境 | ⚠️ macOS Homebrew 走 `--break-system-packages` 才装上 | Linux Docker 通常 venv 即可；agent 安装脚本里建议先 `python -m venv .venv && source .venv/bin/activate` |

### B. fcntl / 文件锁

- `pipeline_state.py` 用 `fcntl.flock`。**Linux/macOS 通用**，Windows 不支持（本项目本来就不打算上 Windows）。

### C. 中文字体

- macOS 用 `STHeiti`；Linux 容器里默认通常**没装中文字体**，matplotlib fallback 后**所有中文显示为方框**。
- 现有 `risk_visualization/scripts/font_utils.py` 已经做 OS 探测，但 Linux 上需要预装：
  ```dockerfile
  RUN apt-get update && apt-get install -y fonts-wqy-zenhei fonts-noto-cjk
  ```
- `chart_threshold.py` 的 `✓ / ✗` 字符（U+2713 / U+2717）在 `WenQuanYi Zen Hei` / `Noto Sans CJK` 上**也不全**，即 BUG-3 在 Linux 同样成立；BUG-3 ✅ 已修。

### D. 中文文件名

- 输出 CSV 名含中文：`youqing_test_候选阈值表.csv`、`threshold_binning_控股类型_私人控股_xxx.png`。
- Linux 文件系统（ext4）支持 UTF-8 文件名无问题；但若挂载到 SMB / NFS 老协议或 zip 打包到 Windows 时可能乱码。
- 建议在 Linux agent 中默认 `LANG=C.UTF-8` 或 `en_US.UTF-8`。

### E. 路径

- 我代码用 `risk_core.paths.get_project_root()` + `RISK_PROJECT_ROOT` / `RISK_OUTPUT_ROOT` 环境变量，**Linux 完全适用**。建议 agent 启动时 explicit 设置这两个 env 而不是依赖 CWD 探测。

### F. 时区

- `cli_io.utc_now_iso()` 用 `datetime.now(timezone.utc).astimezone().isoformat()` —— 实际是**本地时区**，依赖容器 TZ 配置。建议 Docker 里 `ENV TZ=Asia/Shanghai` + `RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime`。
- 当前 audit / state.json 的时间戳格式 `2026-05-12T14:11:00.363652+08:00`；如 TZ 缺失会变 `+00:00`，可读但与生产记录不一致。

### G. 文件系统大小写敏感

- macOS 默认大小写不敏感，Linux 严格敏感。我代码里没有大小写歧义；但 `risk_threshold_explore` vs `risk-threshold-explore`（hyphen vs underscore）这种命名差异**要警觉**——CLI 命令用下划线 `explore_thresholds`，包名也是下划线，一致。

### H. CLI 调用形式（agent 侧）

- 推荐 agent 用：
  ```bash
  cd /path/to/risk-feature-pipeline && \
  PYTHONPATH=$(pwd) RISK_OUTPUT_ROOT=/data/output \
  python -m risk_pipeline explore_thresholds --project xxx --pairs-file pairs.csv
  ```
- **不要**让 agent 把 `risk_threshold_explore` 当独立 Python 包 import 调用 —— 它依赖 `risk_core` 底座在同一 sys.path 下（只依赖 risk_core）。`python -m risk_pipeline` 已经在 `cli.py` 第 25-27 行做了 sys.path 注入，最干净。

### I. matplotlib backend

- 容器无显示器时需 `import matplotlib; matplotlib.use('Agg')`。
- 当前 `risk_visualization/scripts/style.py` 仅 `configure_chinese_font()`，未设 backend。**Linux 容器跑 visualize 大概率会用 Agg backend（matplotlib 默认无 DISPLAY 时回落 Agg），但稳妥起见可以加一行：
  ```python
  import matplotlib
  matplotlib.use('Agg')
  ```
  写在 `style.py` 顶部，先于 `pyplot` import。

---

## 5. 实测产物清单（参考）

```
/tmp/skill_test_data/data/results/youqing_test/
├── youqing_test_audit.json                          ← 已含 threshold_candidates 节点
├── youqing_test_候选阈值表.csv                       ← 4 行候选（含 valid + 未通过原因）
├── youqing_test_候选阈值_分箱明细.csv                 ← 14 行（4 个 pair × 各自分箱数）
├── youqing_test_IV分析结果_全量.csv 等 Level 1 老产物
└── .pipeline_state.json                              ← current_level = Level 1，未推进

/tmp/skill_test_data/output/youqing_test/charts/
├── threshold_binning_控股类型_私人控股_风险标签_信贷逾期_数量.png  ← 颜色 bug
├── threshold_binning_控股类型_私人控股_风险标签_信贷逾期_占比.png
├── threshold_binning_控股类型_私人控股_最早舆情距今天数.png
├── threshold_binning_客户性质_其他有限责任公司_最早舆情距今天数.png
├── threshold_summary_控股类型.png                              ← 颜色正确，红=有效灰=未通过
└── threshold_summary_客户性质.png
```

---

## 6. 修复优先级建议

按优先级，建议下次修复批次：

1. **BUG-1**（chart 颜色）+ **BUG-3**（✓/✗ 字体）—— 一次性改 `chart_threshold.py`，10 分钟
2. **NOTE-1**（IV 门槛改用分群 IV）—— 改 `threshold_explore.py:_lookup_iv_full`、`_judge_validity`，需要从 `Results.iv_group_all` 加一支查询；20 分钟 + 单测调整
3. **BUG-2**（visualize stamp 误报 skipped）—— 改 `visualize.py`，5 分钟
4. **NOTE-2**（zero-inflated 兜底）—— 设计层稍重，建议先加 CLI flag `--min-bin-size`，再考虑算法兜底；30 分钟
5. **BUG-4**（NaN ↔ 空串）+ **NOTE-3**（分箱明细列名汉化）—— 顺手做；5 分钟

总计约 1.5 小时可清完。
