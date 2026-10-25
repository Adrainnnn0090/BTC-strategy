# Y01

原双ExtraTrees价格收益头等权，BAND100/3%管理趋势，正预测许可，纯多头。

模型家族：base_tree, stop44。共同实现与模型只保存一份，参见[`src/btc_strategy`](../../../src/btc_strategy)和[`models`](../../../models)。

|2018—2025历史开发指标|数值|
|---|---:|
|STRESS累计净收益|+4282.78940%|
|四成本最差日度峰谷回撤|34.27590%|
|DELAY累计净收益|+2384.37106%|

不做空；仍承担多头趋势和跳空风险。 全部2026经济数据排除在本轮交付的训练、调参、筛选及账户之外；尚无新2026验证。

复现（仓根目录）：

```bash
python -m btc_strategy.replay --strategy Y01
```

默认由实际numeric模型重建预测，再生成目标、入场许可并重放四个成本账户，比较完整账本并作独立Decimal核对。`--cached-forecasts`仅为缓存预测回放对照，不等于模型重建或重新训练。

原研究：[`studies/B29-prior-forecast-exits`](../../../provenance/studies/B29-prior-forecast-exits/registration.json)，本地recipe `Y01`。参见[四成本、年度与集中度明细](../../../docs/RESULTS_DETAIL.md#y01)及[风险边界](../../../docs/RISK_AND_LIMITATIONS.md)。
