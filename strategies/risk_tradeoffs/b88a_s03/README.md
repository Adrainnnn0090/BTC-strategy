# B88A_S03

P02多头不变，后冷空头预测由Huber损失改为absolute_error对应中位数目标；仍按种子/lag平均。

模型家族：base_tree, price47, short_median。共同实现与模型只保存一份，参见[`src/btc_strategy`](../../../src/btc_strategy)和[`models`](../../../models)。

|2018—2025历史开发指标|数值|
|---|---:|
|STRESS累计净收益|+6045.23059%|
|四成本最差日度峰谷回撤|32.26306%|
|DELAY累计净收益|+2287.67405%|

回撤取舍有限，不代表低风险或未来回撤上限。 全部2026经济数据排除在本轮交付的训练、调参、筛选及账户之外；尚无新2026验证。

复现（仓根目录）：

```bash
python -m btc_strategy.replay --strategy B88A_S03
```

默认由实际numeric模型重建预测，再生成目标、入场许可并重放四个成本账户，比较完整账本并作独立Decimal核对。`--cached-forecasts`仅为缓存预测回放对照，不等于模型重建或重新训练。

原研究：[`studies/B88A-short-net-loss-families`](../../../provenance/studies/B88A-short-net-loss-families/registration.json)，本地recipe `S03`。参见[四成本、年度与集中度明细](../../../docs/RESULTS_DETAIL.md#b88a_s03)及[风险边界](../../../docs/RISK_AND_LIMITATIONS.md)。
