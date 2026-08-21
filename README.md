# SRC-Auto

一个面向补天 SRC 的低成本、CPU 友好、人工确认门控控制层。V1 的目标不是“扫描数量”，而是缩短人工复核时间、降低误报和重复、形成最小证据，并让每一个真实目标请求都可审计、可停止、可恢复。

## 快速开始（本地靶场）

在 PowerShell 中：

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
python -m unittest discover -s tests -v
python -m src_auto new --target-id local-lab --scope config/targets/local-lab/scope_confirmed.yaml --mode local
# 将上一步输出的 run_id 代入下一行
python -m src_auto run --run-id <RUN_ID> --scope config/targets/local-lab/scope_confirmed.yaml --local-lab
python -m src_auto findings --run-id <RUN_ID>
python -m src_auto reports
```

也可使用 `START.bat`、`STOP.bat`、`STATUS.bat`；它们不会创建开机自启动或后台任务。

## 真实 SRC 的唯一人工步骤

把平台规则、测试时间、允许的根域/主机/端口、排除项和授权来源写入独立的 `scope_confirmed.yaml`，由人复核后将 `confirmed` 和 `allow_network_contact` 都设为 `true`。候选文件不能直接升级权限。之后仍需人工查看候选报告并在补天平台手动提交。

## 重要限制

当前机器缺少 WSL2、Go、Node/Docker 和外部扫描器时，`tool-status` 会显示 `unavailable`；这不是模拟通过。外部工具的安装、版本和平台规则见 `tools.lock.yaml`、`IMPLEMENTATION_REPORT.md` 与 `KNOWN_ISSUES.md`。
