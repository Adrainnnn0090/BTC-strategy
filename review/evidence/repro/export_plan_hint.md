# 第01轮：给交付仓维护者的复现合同建议

这是一份工程建议，不是新仓验收结论。未编辑 `/workspace/BTC-strategy`，未执行研究模块或账户重放。

## 已核实的依赖入口

| 候选 | 已确认的来源与入口 |
| --- | --- |
| LP35、TS04、ME01、MX03 | `studies/B109-long-profit-local-coordinate/registration.json:recipes` 与 `lab/b109.py:targets` |
| B88A_S03 | `studies/B88A-short-net-loss-families/registration.json:recipes` 的本地ID `S03`，应保留study命名空间 |
| K02 | `studies/B72-cold-budget-exposure/registration.json:recipes` |
| Y01 | 多条继承链出现，应由主合同选定唯一冻结原型及对应血缘；不能仅按字符串同名合并 |
| C02、C04 | `studies/B31-constant-sizing-controls/registration.json:recipes` |

四入口的静态本地导入递归上界是98个`.py`，完整列表与文件hash见 `checks-r01.json:static_local_import_closure`。它包含研究操作、训练和验证角色，适合作为起始目录，不能称为已求得最小推理闭包。

## 必须在交付清单中分开说明

1. **可重建预测/账户的交付**：已拟合的逐年numeric状态、对应年度policy/feature顺序、数值预测代码、候选targets/entry/risk变换、成本与账户核算、允许输入和预期receipt/哈希。
2. **可重做训练的交付**：除上一项之外，原训练/标签/成熟和隔离规则、样本ID、种子、选择规则、训练制品环境与记录。不能把预测缓存作为已拟合模型本体，更不能把既有预测回放宣称为重新训练复现。

B88A状态检查：2018按登记为0，2019–2025每年56个，共392个状态hash均正确。对只交付S03的推理可进一步按选定loss/head/seed求取必要状态；全研究训练闭包仍需保留其他loss的研究记录以支持原历史声明。不要用未来拟合状态补齐2018。

## 路径解耦的实证定位

- `lab/io.py:4`已经按`__file__`求仓根；问题是保留其所需包/数据布局，而不是修复不存在的旧仓根绝对字符串。
- `carry_native.py:14–15`导入外部`binance_robot.execution`和`runner`。只需`INSTRUMENT/VENUE/paper_instrument`却会发生更多顶层导入。`runner.py:17–22`包含交易工程的contracts、settings、strategies.registry等依赖。可在新仓做最小等价适配；保留源SHA、原代码片段来源和新适配diff，不能改原文件。
- 原`project_runtime_sources`精确绑定`/workspace/BinanceTradingRobot/backend/.venv/lib/python3.12/site-packages/binance_robot/{execution,runner}.py`，`b109.verify:52`直接对旧路径读hash。B88A还绑定sklearn Python/CPython3.12 x86_64二进制旧路径。迁仓应使用相对/内容地址映射校验交付副本，并单独保存原登记作证据，不能把登记原件改写成新路径。
- `b109_io.py:40`和`b88a_io.py:43–44`的外部依赖白名单也与旧路径有关。应只调整新仓适配的运行时解析，仍确定性拒绝2026/V01/V02和非授权研究材料；绝不能把禁读目录改成任意读取。

## 最小验收合同

验收必须在旧源仓/旧交易工程路径不可见、无网络、无凭据的干净环境中执行，只写交付仓或其临时输出：

1. 九候选来源映射、文件清单与hash全部完整；Python/ABI/OS和依赖制品清单可离线安装。
2. 2018–2025年度state/policy绑定成立、因子与预测重建符合原数值语义；B88A沿用已登记`2e-12`容差，不事后放宽。
3. targets/entry/risk结构与冻结参考精确相等；保持无模型年份的可用性语义。
4. 授权重放案例的订单、成交、融资、mark、summary按原精度一致；报告路径哈希和所有差异，不能只对收益或“无异常”验收。
5. 对2026/V01/V02读尝试做合成路径拒绝检查，不打开真实禁读文件。

以上仅定义后续验收，不在第01轮运行账户或训练任务；不调用原冻结模块的`freeze/train/test/replay/run`来产生已有输出。
