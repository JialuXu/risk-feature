# 查询配方

只在需要**非标准**查询（透视、跨分群对比、缺失模式、手动排序）时读本页。简单 top-N 用 `top_features()` 就够。

## 1. 跨分群对比同一特征

```python
feat = 'x_payment_delay_90d'
sub = r.iv_group_all.query('特征 == @feat and 分群维度 == "企业规模"')
print(sub[['分群名称', 'IV值', 'IV可信度']].to_string(index=False))
```

## 2. 筛选"多分群一致预测"的特征

```python
# 相关系数 > 0.05 在 ≥ 3 个分群中同时成立
from risk_result_query.scripts.results_loader import load_results
r = load_results('舆情特征分析')
mask = r.corr_long['|相关系数|'] > 0.05
count = r.corr_long[mask].groupby('特征').size()
stable = count[count >= 3].index.tolist()
```

## 3. IV 与 LR 系数对比（识别冗余/抑制特征）

```python
iv = r.iv_full.set_index('特征')['IV值']
lr = r.lr_coef_long.groupby('特征')['|系数|'].mean()
comp = iv.to_frame('IV').join(lr.to_frame('|LR|均值')).dropna()
# 冗余特征：IV 高但 LR 低（被其他特征替代解释）
redundant = comp[(comp['IV'] > 0.1) & (comp['|LR|均值'] < 0.05)]
```

## 4. 只看"可信"分群

```python
trusted = r.iv_group_all.query('IV可信度 == "可信"')
```

## 5. 正/负系数分别取 top

```python
lr_sub = r.lr_coef_long.query('分群维度 == "企业规模" and 分群名称 == "小型企业"')
top_pos = lr_sub.sort_values('系数', ascending=False).head(10)   # ↑风险
top_neg = lr_sub.sort_values('系数', ascending=True).head(10)    # ↓风险
```

## 6. 透视（分群 × 特征 的 IV 热力图底数据）

```python
pivot = r.iv_group_all.query('分群维度 == "企业规模"') \
         .pivot(index='特征', columns='分群名称', values='IV值')
```

## 7. 从原始宽表现算坏/好均值（`diff_long` 只有差值）

```python
import pandas as pd
df = pd.read_csv(原始宽表路径, encoding='utf-8-sig')
# 合并 is_bad 后：
feat = 'x_xxx'
df.groupby(['企业规模', 'is_bad'])[feat].mean().unstack()
```
