# 证据来源与适用边界

本仓以原注册、年度封印、实际数值模型和完整账户为控制来源，来源映射及SHA见`../provenance/export_manifest.json`和`../models/manifest.json`。专家角色的意见必须回到这些证据与实际检查，不以投票替代证明。

|来源|地位与读取范围|用于什么|不证明什么|
|---|---|---|---|
|[The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)，2015作者版本|原始方法论文全文可读|反复回测选择与PBO框架的动机|没有因此算出本仓有效PBO，也不认证本仓alpha|
|[The Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)，2014作者版本|原始方法论文全文可读|多重选择、非正态收益和试验次数披露的必要性|未获得完整有效搜索族，不能凭115登记或成员数伪造DSR|
|[Nautilus backtesting](https://nautilustrader.io/docs/latest/concepts/backtesting/)|官方文档，一般机制；精确执行用本仓固定2.0.0rc4及实测|事件引擎、报价、撮合、保证金配置需要明确假设|最新文档不自动认证本仓日度报价、借贷可得性或真实融资后清算|
|[scikit-learn TimeSeriesSplit 1.6](https://scikit-learn.org/1.6/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)|官方版本化方法文档；本仓安装1.6.1|时间顺序与gap的一般原则|本仓标签成熟另外要求61/62日边界，6日gap不是独立性证明|
|[GradientBoostingRegressor 1.6](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.GradientBoostingRegressor.html)|官方版本化API；本仓实际numeric模型另作重建|损失函数、随机种子和树参数语义|Huber alpha不是上涨概率，absolute_error也不是对14个成员预测取中位数|

加州大学PBO存档页本次抓取返回429；使用作者公开PDF作为可读取原始证据，未把不可访问页面内容当已核验。检索/读取日期为2026-10-25（Asia/Shanghai）；这只是文献访问时间，不是市场经济观察。

## 用户指定插件的实际用途

- Research Evidence Finder：原始论文查找、来源验证、反证与不确定性。
- Research Methodology：事前范围与问题、证据账本、范围/对象过滤和逐轮结论。
- Research & Writing Copilot：声明追溯、文档与复现说明；不制造专家背书。
- Data / validate-data：原始记录权威、分集、算式、字段连接及物料完整性检查。
- Stock & ETF Research Panel：盲审、固定事前角色覆盖、证据挑战和非投票主风险审查。BTC策略代码审计不做股票估值、ETF穿透或个人投资建议；六审计角色是针对本对象的适配，不冒充完整股票筛选流程。

所有角色均为AI分析视角，不是人类或持牌顾问，不构成外部审计；相同市场、模型和交易的复用也不是新的独立市场样本。本仓不包含交易下单或生产接入指令。
