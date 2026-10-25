# 十二轮审查索引

六个AI分析角色按轮提交，再由主agent审核；共72份原始意见和12份主审记录。角色按指令不读取彼此意见，使用相同冻结事实。工作目录共享，不是操作系统级六重沙箱，也不是六个人类专家或72份独立市场样本。实际工程隔离另见无网络容器证据。

|轮次|主题|主审|六项原始结论|
|---|---|---|---|
|01|声明边界与研究合同|[主审](rounds/01/CHAIR.md)|[statistics](rounds/01/statistics.json) · [data](rounds/01/data.json) · [models](rounds/01/models.json) · [execution](rounds/01/execution.json) · [risk](rounds/01/risk.json) · [repro](rounds/01/repro.json)|
|02|年度分集与封存|[主审](rounds/02/CHAIR.md)|[statistics](rounds/02/statistics.json) · [data](rounds/02/data.json) · [models](rounds/02/models.json) · [execution](rounds/02/execution.json) · [risk](rounds/02/risk.json) · [repro](rounds/02/repro.json)|
|03|标签成熟与隔离期|[主审](rounds/03/CHAIR.md)|[statistics](rounds/03/statistics.json) · [data](rounds/03/data.json) · [models](rounds/03/models.json) · [execution](rounds/03/execution.json) · [risk](rounds/03/risk.json) · [repro](rounds/03/repro.json)|
|04|因子可得性和来源时点|[主审](rounds/04/CHAIR.md)|[statistics](rounds/04/statistics.json) · [data](rounds/04/data.json) · [models](rounds/04/models.json) · [execution](rounds/04/execution.json) · [risk](rounds/04/risk.json) · [repro](rounds/04/repro.json)|
|05|模型方程与实现一致性|[主审](rounds/05/CHAIR.md)|[statistics](rounds/05/statistics.json) · [data](rounds/05/data.json) · [models](rounds/05/models.json) · [execution](rounds/05/execution.json) · [risk](rounds/05/risk.json) · [repro](rounds/05/repro.json)|
|06|执行、滑点、融资与净值|[主审](rounds/06/CHAIR.md)|[statistics](rounds/06/statistics.json) · [data](rounds/06/data.json) · [models](rounds/06/models.json) · [execution](rounds/06/execution.json) · [risk](rounds/06/risk.json) · [repro](rounds/06/repro.json)|
|07|敞口、止损与跨年风险|[主审](rounds/07/CHAIR.md)|[statistics](rounds/07/statistics.json) · [data](rounds/07/data.json) · [models](rounds/07/models.json) · [execution](rounds/07/execution.json) · [risk](rounds/07/risk.json) · [repro](rounds/07/repro.json)|
|08|多重试验与有效独立性|[主审](rounds/08/CHAIR.md)|[statistics](rounds/08/statistics.json) · [data](rounds/08/data.json) · [models](rounds/08/models.json) · [execution](rounds/08/execution.json) · [risk](rounds/08/risk.json) · [repro](rounds/08/repro.json)|
|09|年度、行情与盈利集中|[主审](rounds/09/CHAIR.md)|[statistics](rounds/09/statistics.json) · [data](rounds/09/data.json) · [models](rounds/09/models.json) · [execution](rounds/09/execution.json) · [risk](rounds/09/risk.json) · [repro](rounds/09/repro.json)|
|10|导出模型与离线复现|[主审](rounds/10/CHAIR.md)|[statistics](rounds/10/statistics.json) · [data](rounds/10/data.json) · [models](rounds/10/models.json) · [execution](rounds/10/execution.json) · [risk](rounds/10/risk.json) · [repro](rounds/10/repro.json)|
|11|修复和对抗性检查|[主审](rounds/11/CHAIR.md)|[statistics](rounds/11/statistics.json) · [data](rounds/11/data.json) · [models](rounds/11/models.json) · [execution](rounds/11/execution.json) · [risk](rounds/11/risk.json) · [repro](rounds/11/repro.json)|
|12|最终验收与未解决风险|[主审](rounds/12/CHAIR.md)|[statistics](rounds/12/statistics.json) · [data](rounds/12/data.json) · [models](rounds/12/models.json) · [execution](rounds/12/execution.json) · [risk](rounds/12/risk.json) · [repro](rounds/12/repro.json)|

[最终主审报告](FINAL_REPORT.md) · [附件路径与SHA](evidence_manifest.json) · [事前协议](protocol/CHARTER.md)

原报告中的`/workspace/BTCExpertReview/workspaces/<role>/...`附件对应本仓`review/evidence/<role>/...`。[顺序轮次时间记录](run_timeline.json)使用观察到的文件时间，非外部签名时间证明。原始报告和失败快照保持逐字节，不回写为后来PASS。源ledger路径由`provenance/export_manifest.json`及各模型manifest映射；本仓不是整个原实验室的镜像。支持脚本保留原审计环境路径，复现入口以README命令为准。
