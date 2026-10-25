# BTC Strategy Research

九项保留BTC策略的分类实现、实际年度数值模型、训练前缀、完整账户基准和可复现核验。

**这是2018—2025已消耗开发历史的研究交付，不是新鲜样本外alpha或实盘收益承诺。** 全部2026经济数据保持验证身份，本次不读取、不训练、不调参、不筛选，也不把既有验证消费记录改称盲测。

## 策略分类

|类别|策略|说明|
|---|---|---|
|[高收益分支](strategies/README.md)|LP35、TS04、ME01、MX03|共享价格模型，差异主要是冷启动过滤、止盈和仓位规则|
|[回撤取舍](strategies/README.md)|B88A_S03、C02、C04|中位数损失或透明降仓；回撤改善有限，不等于低风险|
|[空头敞口控制](strategies/exposure_controls/k02/README.md)|K02|冷/后期空头预算25%；不是持续gross上限|
|[纯多头基准](strategies/long_only/y01/README.md)|Y01|价格模型、趋势过滤及年度封存风控|

完整共同窗口、四成本、年度收益和盈利集中见[结果明细](docs/RESULTS_DETAIL.md)。LP35历史STRESS累计净收益+10127.92%，四成本最差日度峰谷回撤32.58572%，DELAY+4133.27%。它相对TS04仅一笔退出日改变，后续复利放大差异；不能因此声称新的预测能力。

## 快速复现

环境：Linux x86_64、Python3.12。

```bash
uv sync --locked --extra test
uv run --locked python -m pytest -q
uv run --locked python -m btc_strategy.verify --integrity --models --targets
uv run --locked python -m btc_strategy.replay --all
```

默认由实际模型重建预测，随后重组目标和入场许可、重放Native账户、比较完整原账本并独立Decimal核算。不是只把一串历史买卖信号重放。

```bash
uv run --locked python -m btc_strategy.training --family price47 --year 2025
```

训练命令只重拟合已选最终估计器，不重做原内层参数选择或整段策略研究。六族2025共56个最终状态已作抽样年度重拟合，其他年度不能据此称全部训练复现。完整层级和无网络容器命令见[复现说明](docs/REPRODUCIBILITY.md)。

## 文件结构

```text
strategies/         分类策略卡与配置，明确study命名空间
src/btc_strategy/   独立运行入口、纯规则、实际模型推理、训练与账户核验
models/             266个原始JSON/gzip文件，含392个数值模型成员
training_inputs/    6家族×8年物理训练前缀、ids、标签与cut
artifacts/          价格/因子、年度上下文、目标与36个完整原账户
provenance/         原源码/注册/模型哈希、失败与修正、独立适配差异
research/           历史试验元数据索引；有效独立试验次数仍未知
review/             6个AI角色×12轮的独立提交与逐轮主审记录
verification/       真实执行的核验收据，按范围区分
```

模型共享保存，不给每项策略复制一套权重。2018无可用模型的状态保留None，不用未来模型回填。年度模型路由使用显式fold和信号日期窗口，不能直接按日期年份选择最后一个模型。

## 专家审查与限制

审查要求是六个互不读取当轮其他角色意见的AI分析角色、每轮各一项结论，再由主agent复核，共十二轮。完成状态由以下命令检查，不能用文字声明代替：

```bash
uv run --locked python -m btc_strategy.verify --review
```

角色隔离属于盲审工作流，不是六个人类专家、外部审计或六份独立市场证据。实际隔离运行另有不挂旧项目、无网络、只读数据的容器收据。

[风险与限制](docs/RISK_AND_LIMITATIONS.md)必须与收益一起阅读：LP35逐日退出前short gross曾超过100%，止损触发并非成交亏损上限；Native有保证金机制，但外置模拟融资没有进入其原生钱包；来源PIT和全流程搜索偏差尚未解决。原研究失败与另立修正分别保留。

[证据与方法来源](docs/EVIDENCE_SOURCES.md)说明用户指定插件的具体用途与不适用部分。本仓仅作一般研究与复现，不含个人投资建议、实盘下单或生产接入。
