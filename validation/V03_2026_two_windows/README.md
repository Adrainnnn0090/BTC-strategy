# V03复现入口

[报告](REPORT.md) · [原合同](PROTOCOL.md) · [完整结果](results/results.json) · [账本](results/accounts/)

仅2017—2025训练；两个2026窗口都是验证，不能加入训练或据此调参。完整价格296日，C04矿业输入缺失被阻断；价格来源PIT仍有条件，旧验证消费不改称新鲜盲测。

## 核验已有结果

仓库根目录，Python3.12及固定依赖：

```bash
uv sync --locked --extra test
uv run --locked python -m pytest -q
uv run --locked python -m btc_strategy.verify --integrity --review --models --targets
uv run --locked python -m btc_validation.verify --outcomes
uv run --locked python validation/V03_2026_two_windows/summarize_accounts.py
```

最后一步只从封存账本导出CSV、核对Decimal净值与回撤和方向归因，不产生新预测、不拟合、不改变原始结果seal。`--chart`可选，需要本机另有matplotlib，未加入策略依赖。

## 物理隔离重拟合

拟合与评价分开运行；不要把整个仓库或验证目录挂给训练容器。以下是Linux shell示例。新输出目录必须为空，worker拒绝覆盖。原训练镜像和验证镜像ID见[训练收据](training/isolation-and-prior-parity.json)与[运行收据](verification/execution-receipt.json)；当前构建代码与实际经济运行代码逐文件SHA绑定。

```bash
docker build -t btc-validation-v03 .
python validation/V03_2026_two_windows/prepare_train_inputs.py --out /tmp/v03-train
mkdir -p /tmp/v03-refit
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --tmpfs /tmp:rw,nosuid,nodev,size=1g \
  --user "$(id -u):$(id -g)" \
  --mount type=bind,src=/tmp/v03-train,dst=/train,readonly \
  --mount type=bind,src=/tmp/v03-refit,dst=/out \
  btc-validation-v03 python -I -m btc_validation.train
```

prepare_train_inputs仅校验并复制五份过去输入和原manifest，不读取validation/intake。prices/mining均在2025Dec31终止；历史政策原封存来源元数据仅作核验，不包含供训练使用的2026价格/标签。重新拟合属于复现，不能用2026结果决定是否保留某个模型。

## 冻结权重重放验证

用仓库已经封存的权重，生成仅供推理的挂载。其历史价格用于因果特征warmup，不能送入训练；原始训练和2026数据仍各自保存在独立文件。不要用整个仓库替代这个角色受限的挂载。

```bash
python validation/V03_2026_two_windows/prepare_eval_inputs.py --out /tmp/v03-inference
mkdir -p /tmp/v03-replay
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --tmpfs /tmp:rw,nosuid,nodev,size=1g \
  --user "$(id -u):$(id -g)" \
  --mount type=bind,src=/tmp/v03-inference,dst=/validation,readonly \
  --mount type=bind,src=/tmp/v03-replay,dst=/out \
  btc-validation-v03 python -I -m btc_validation.evaluate
```

新运行的UTC、Git版本及输入registration哈希会不同，不能因此声称原始收据逐字相等。应比较数值模型、预测、目标及逐日marks/fills/trades/financing；原`results/`与seal保持首次运行原件。C04在数据未补齐时仍应阻断。上述步骤不是要求重复调参或重新消费验证集。
