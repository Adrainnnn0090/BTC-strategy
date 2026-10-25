# 保留策略分类

统一比较2018—2025已消耗开发历史，收益为STRESS净收益、回撤为四成本最差日度峰谷回撤。模型年度前推不使后来整段规则筛选成为新鲜OOS。

|家族|策略|核心差异|STRESS|最差DD|DELAY|
|---|---|---|---:|---:|---:|
|high_return|[LP35](high_return/lp35/README.md)|TS04上只把多头固定止盈从300%提高至350%。|+10127.92%|32.59%|+4133.27%|
|high_return|[TS04](high_return/ts04/README.md)|ME01上只把模型缺失期空头盈利追踪距离从12%收紧至4%。|+9838.41%|32.59%|+4400.07%|
|high_return|[ME01](high_return/me01/README.md)|P02价格模型、多头300%止盈、取消多头波动率折扣；模型缺失期MA20下3%及5日负动量新开空头。|+9261.50%|32.58%|+4890.53%|
|high_return|[MX03](high_return/mx03/README.md)|ME01上只在模型缺失期新开空头另要求1日负动量。|+9008.15%|32.58%|+4978.58%|
|risk_tradeoffs|[B88A_S03](risk_tradeoffs/b88a_s03/README.md)|P02多头不变，后冷空头预测由Huber损失改为absolute_error对应中位数目标；仍按种子/lag平均。|+6045.23%|32.26%|+2287.67%|
|exposure_controls|[K02](exposure_controls/k02/README.md)|L06模型与信号不变，冷启动及后期空头预算均改25%并保留原波动缩放。|+5027.44%|32.92%|+2325.11%|
|long_only|[Y01](long_only/y01/README.md)|原双ExtraTrees价格收益头等权，BAND100/3%管理趋势，正预测许可，纯多头。|+4282.79%|34.28%|+2384.37%|
|risk_tradeoffs|[C02](risk_tradeoffs/c02/README.md)|Y01在合资格2020–2025折把新开多头预算乘0.75；2018/2019保持原预算。|+2417.21%|31.89%|+1489.41%|
|risk_tradeoffs|[C04](risk_tradeoffs/c04/README.md)|H04滞后挖矿动态树多头，在合资格2020–2025折把新开预算乘0.75；来源PIT仍有条件。|+2390.43%|31.89%|+1637.24%|

LP35、TS04、ME01、MX03共享大量预测和交易，不能当作独立alpha组合。B88A_S03明确study命名空间，避免与旧B51同名策略混用。全部策略仍为研究资料，不包含实盘入口。
