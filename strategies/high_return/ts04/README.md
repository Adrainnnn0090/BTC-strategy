# TS04

ME01上只把模型缺失期空头盈利追踪距离从12%收紧至4%。

模型家族：base_tree, price47, short_huber。共同实现与模型只保存一份，参见[`src/btc_strategy`](../../../src/btc_strategy)和[`models`](../../../models)。

|2018—2025历史开发指标|数值|
|---|---:|
|STRESS累计净收益|+9838.40901%|
|四成本最差日度峰谷回撤|32.58572%|
|DELAY累计净收益|+4400.06564%|

历史收益较高；规则筛选使用已消耗开发历史，冷启动、退出时点和复利贡献大。 全部2026经济数据排除在本轮交付的训练、调参、筛选及账户之外；尚无新2026验证。

复现（仓根目录）：

```bash
python -m btc_strategy.replay --strategy TS04
```

默认由实际numeric模型重建预测，再生成目标、入场许可并重放四个成本账户，比较完整账本并作独立Decimal核对。`--cached-forecasts`仅为缓存预测回放对照，不等于模型重建或重新训练。

原研究：[`studies/B107-cold-short-profit-trailing`](../../../provenance/studies/B107-cold-short-profit-trailing/registration.json)，本地recipe `TS04`。参见[四成本、年度与集中度明细](../../../docs/RESULTS_DETAIL.md#ts04)及[风险边界](../../../docs/RISK_AND_LIMITATIONS.md)。
