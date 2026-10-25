# 第11轮主审

原候选对抗检查确有缺口，全部保留失败；在c743921定向关闭2018缺失合同、V别名、训练plan身份/完整日期与未知cost早拒绝，并由发现者追加复测。当前实现可进入最终研究归档验收，不获得PIT、OOS或实盘资格。

|角色|结论|意见|
|---|---|---|
|statistics|a642de16相对1b008bf的代码修改仅给既有回放输出增加风险口径与资格文字；独立差异、AST和合成对抗检查支持历史数值/分类/来源绑定不变，Consumed、非新鲜OOS、有效独立tests未知及最终拟合不等于原选择复现的界限均保留，工程修复没有新增经济或统计证据。|supported|
|data|a642de16已准确澄清training hook不是OS沙箱，关键模型/日期拒绝与封存训练前缀抽核通过；但合成测试仍发现验证文件别名未被路径模式拒绝、重复过去日期及错误plan.family可到达fit哨兵，故不能把本次文档修复解释为任意坏输入均被入口完整阻断。|qualified|
|models|候选a642de16的数字模型/数学运行代码保持R10状态，加载器20项有界合成检查中19项符合预期且无静默零值回退；但仍可把2018 manifest伪设为present并载入7个合成状态，缺少“2018必须missing/None”的强制历史合同。真实manifest未出现该问题，数值结论不因此失效，但此硬化缺口应修复后再验收，不能把本轮结果概括为全部对抗检查通过。|qualified|
|execution|对a642de16的有界独立回归支持该补丁仅增加metric_scope与risk_qualification输出：LP35/BASE默认数字模型路径重建目标并运行Native后，完整account和summary保持原值，新增标签正确区分成交后/订单前后日度口径且不承诺连续敞口或成交亏损上限。|supported|
|risk|a642de1的gross口径修复已在一份LP35/BASE历史重放中验证，新增说明字段以外的原API结果、账本与Decimal均精确不变；未来输入及CLI未知枚举前置拒绝通过，但Python run API对未知cost仍在目标处理后才拒绝，须限定其“前置”声明，paper/live等未解决风险不因标签修复而获得认证。|qualified|
|repro|对候选a642de的本角色初始问题回归通过：无旧工程源码读取或替身的清洁导入、13个禁读路径、20个类型/年份/家族/完整日期读前例、2018不可用语义及price-only惰性因子均通过；私有合成模型/清单/审查工件的17项故障均拒绝。原第05/07轮失败保留。verify_integrity只认证所给清单的声明内容，故本轮另将实际886项清单锚定到冻结commit及SHA，不把任意空清单PASS0误称为完整发布验收。|supported|

## 范围过滤

将a642de原19/20和其他残余明确记为未通过，不用正常数据重放或多数supported覆盖它们；只按修复后具体反例的独立重测关闭具体问题。可信manifest的内容一致与其真实性/覆盖范围另分层。

## 对象过滤

c743921是修复候选；原模型/训练数据/目标/账户与经济执行函数未变。附加三份retst是原R11问题的版本化关闭证据，不加算为三个市场样本或三轮审查。

## 主审处理

- 接受并实施models的2018反向missing合同：2018不能被manifest改成present，任何numeric state读取前拒绝。
- 接受并实施data的V01/V02点号/下划线别名拒绝，以及plan.family/intyear/完整连续唯一过去日期/intcut/embargo6/missing身份检查，states与fit之前执行。
- 接受并实施risk的未知cost和坏类型在verify_targets/compose/model/engine之前拒绝；保留原gross标签和全部原summary值。
- 三位发现者r11-retest独立通过，原r11失败JSON及原check附件不覆写；补丁不更改权重、风险阈值或历史账户。
- 披露integrity信任清单身份、需Git提交/manifestSHA锚定；hook仍非OS sandbox，不扩大安全声明。
