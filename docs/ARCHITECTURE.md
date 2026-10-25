# 模型与策略怎样连接

本仓把预测模型、年度封存规则和账户执行分开。入口是[`replay.run`](../src/btc_strategy/replay.py)：实际模型重建预测 → [`compose`](../src/btc_strategy/strategies.py)组合固定策略 → Native执行 → 完整原账本比较 → 独立Decimal核算。默认路径不拿缓存预测代替模型；年度policy/risk本身是原研究已选结果，不在回放时重新校准。

## 六类实际模型

|模型家族|输入与监督目标|成员与聚合|
|---|---|---|
|base_tree|CAL44：历史价格动态与已知日历；60日持有的成本调整log-return|每年度7个ExtraTrees状态，按种子平均|
|stop44|CAL44；60日成熟窗口内固定STOP/日历退出的成本后单笔log-return|每年度7个ExtraTrees状态，按种子平均|
|price47|PRICE47：CAL44及额外价格列；与stop44同类STOP标签|每年度7个ExtraTrees状态；这是price-only分支，未使用成交量|
|short_huber|CAL44；计入数量舍入、费用、融资与退出的SHORT_NET simple return|7种子×L1/L2两个执行滞后，GradientBoosting Huber；先各head平均，再两head平均|
|short_median|同短头输入/标签，损失改为absolute_error|7种子×两个head；MEDIAN指损失/目标语义，成员预测仍平均|
|mining58|CAL44+两mask+八挖矿动态列+四强制归零状态列；成本调整log-return|每年度7个ExtraTrees状态；lag60可得性假设，严格PIT未认证|

列序在[feature_schema](../models/feature_schema.json)，具体profile、seed、树阈值、叶值、boosting initial/weight在[数值模型](../models)。全部状态均为96棵树，共392状态/37,632棵树；存于266个原始JSON/gzip文件。推理保留float32输入、float64阈值、`<=`走左及原聚合顺序，不依赖pickle。树输出是相应监督目标的分数，不能一概解释为上涨概率。

训练方法和标签原始源码保存在[`_frozen/lab`](../src/btc_strategy/_frozen/lab)，包括[`execution_labels.py`](../src/btc_strategy/_frozen/lab/execution_labels.py)、[`lagged_short.py`](../src/btc_strategy/_frozen/lab/lagged_short.py)。运行适配差异另在`provenance`登记；归档driver保留原路径合同，不是新仓公开入口。

## 年度路由与训练

fold Y在上一年末封存，决策日期窗口为`[Y-1-12-31, Y-12-31)`；执行再按case延迟1或2日。不能单用`date.year`选模型。2018的六族模型缺失状态保持None，不用后来的模型填补；冷启动规则与拟合模型信号分开。

[`training_inputs`](../training_inputs)是六族×八年的物理过去前缀。长样本需`i+61 <= cut-6`，短头共同样本需`i+62 <= cut-6`。60日标签重叠，6日gap不是统计独立保证。当前[`training.refit`](../src/btc_strategy/training.py)只重拟合已选最终参数；使用给定features/targets拟合一致，不代表独立重生标签、重做内层选择或全研究搜索。

## 九策略的规则关系

```text
共享base_tree + price47，短头short_huber
  P02 → 多头TP300% → 取消正波动折扣 → 冷期MA20/3%与5日负动量 → ME01
    ME01 → 冷期另需1日负动量 → MX03
    ME01 → 冷期空头盈利追踪距离4% → TS04 → 多头TP350% → LP35
  P02 + short_median替换短头 → B88A_S03

base_tree + stop44 → BAND100/3%与年度封存规则 → 纯多头Y01
  Y01 → 合资格折新开多头预算×0.75 → C02
base_tree + stop44 + short_huber → 冷/后期空头预算0.25/0.25 → K02
mining58 → 原H04/U02规则 → 合资格折新开多头预算×0.75 → C04
```

规则是预测许可、趋势过滤、波动缩放、入场预算和entry-owned止盈止损的组合。None不等于零预测，也不等于必须清仓；开仓保存的风险随旧仓跨年继续生效。LP35与TS04历史上只改变一笔退出日；收益优势可能来自资金路径而非新增预测能力。止损会受延迟、跳空和费用影响，预算不是持续gross上限，完整定义见[风险文档](RISK_AND_LIMITATIONS.md)。

各策略的命名空间、原登记、四成本、年度与集中度见[分类入口](../strategies/README.md)。这些是同一已消耗历史上的固定研究实现；2026真实经济数据未进入本仓运行物料，本次不作新验证或新搜索。
