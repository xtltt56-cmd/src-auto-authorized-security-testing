# 可视化升级前回退基线

## 基线身份

- 项目：`D:\网络安全文件夹\SRC-Auto`
- 升级分支：`codex/storybook-visual-upgrade`
- 基线提交：`cfd9d2d`（完整 SHA 可用 `git rev-parse baseline-pre-storybook-20260826` 查询）
- 基线标签：`baseline-pre-storybook-20260826`
- 基线工作树：`D:\网络安全文件夹\SRC-Auto\.worktrees\storybook-visual-upgrade`
- 基线验收：`python -m unittest discover -s tests -p 'test_*.py'`，239 个测试通过

## 回退原则

回退只切换程序源码、配置模板、测试和说明，不删除或覆盖 `data`、`reports`、`evidence`、`logs`、`runs`、`validation`、Docker 卷、密钥和用户生成报告。升级过程继续在独立工作树内进行，当前旧 WinForms 启动器和 CLI 不会被删除。

## 安全回退方式

推荐使用项目内脚本在新的工作树中复现基线，避免覆盖当前目录：

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
& '.\tools\restore-pre-storybook-baseline.ps1'
```

脚本默认创建 `D:\网络安全文件夹\SRC-Auto\.worktrees\rollback-pre-storybook`，然后可在该目录运行旧版检查。若目录已存在，脚本会拒绝覆盖；请指定新的 `-Destination`。

## 手工核验

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
git show --stat baseline-pre-storybook-20260826
git worktree list
```

基线恢复后，先执行：

```powershell
python -m unittest discover -s tests -p 'test_*.py'
```

随后按原有 `START_SYSTEM.ps1 -LegacyGui` 或 `START.bat` 启动。回退不代表允许访问真实目标；原有授权、范围和人工提交边界继续有效。

## 基线内容边界

已保存：源码、PowerShell 工具、测试、配置模板、设计参考图、计划和使用说明。未从工作区复制运行期数据库、日志、ZAP 会话、缓存、报告和依赖目录；这些内容应在 D 盘按原目录保留，不纳入可视化升级提交。
