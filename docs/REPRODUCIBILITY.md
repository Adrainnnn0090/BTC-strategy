# 复现层级与命令

支持的核验环境：Linux x86_64、Python3.12，依赖由`uv.lock`及带hash的`requirements.lock`固定。已测试版本与执行结果保存在`verification/`，不承诺不同平台下重拟合的逐位相同。

```bash
uv sync --locked --extra test
uv run --locked python -m pytest -q
uv run --locked python -m btc_strategy.models
uv run --locked python -m btc_strategy.replay --all
```

`replay`默认从实际numeric树重建预测，重组全部目标/许可，运行Native账户并比较完整原账本，再做Decimal核算。`--cached-forecasts`只用于缓存预报回放对照；不是模型推理或训练复现。此时仍只允许2017—2025数据。

按家族重拟合一个已选最终模型年度：

```bash
uv run --locked python -m btc_strategy.training --family price47 --year 2025
```

这只重拟合封存的最终参数，不重做原内层选择或整段策略搜索；不会覆盖原模型。训练使用`training_inputs/<year>/<family>.json.gz`中的物理过去前缀、共同ids与标签，运行时拒绝读取测试context、账户、其他家族或其他年度训练物料。2018有意无状态，不得用后来模型回填。六家族2025共56个最终估计器已作抽样年度重拟合，其他年度不能据此称全部重拟合通过。

实际数值模型是JSON/gzip树节点、阈值和叶值，不需要pickle。`models/manifest.json`列出年度窗口、source、SHA、因子schema和训练包。原研究注册与失败保存在`provenance/`；`_frozen`是逐字节源码档案，旧driver保留原路径合同，不能当作新仓直接入口。新入口使用26模块纯运行时，只对clock依赖做已记录导入适配，经济函数体不变。

如安装wheel后离开克隆目录运行，显式设置`BTC_STRATEGY_ROOT`为克隆仓根。代码不会隐式搜寻旧研究工程。

## 容器核验

```bash
docker build -t btc-strategy-audit .
docker run --rm --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,nosuid,nodev,size=1g \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$(pwd),dst=/research,readonly" \
  btc-strategy-audit python -I /research/scripts/verify_offline.py
```

容器只挂本仓只读数据，旧研究和交易工程不挂载；验证时无网络。联网构建阶段若在受管代理环境，按平台规定使用BuildKit的`proxy_ca`证书secret，保持TLS校验；证书不写入镜像。本仓不存凭据。构建所下载的依赖和文献访问时间不是2026市场经济数据。

## 验证声明的区别

1. 文件与source hash一致；
2. 实际模型推理与原预报一致；
3. 目标/入场许可一致；
4. 完整Native账户及独立Decimal核算一致；
5. 封存最终估计器重拟合一致；
6. 新鲜样本外泛化、真实成交与融资后清算安全。

前五项有各自限定的执行证据，不能自动推出第六项。全部2026经济数据维持验证身份，本次未重新运行验证。
