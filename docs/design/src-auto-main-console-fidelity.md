# SRC-Auto 主控制台视觉与交互对照记录

**日期：** 2026-08-26
**参考稿：** `design/frontend-mockups/2026-08-26-figma-v2/manifest.json`、`design/frontend-mockups/2026-08-26-figma-v2/README.md`、`design/frontend-mockups/2026-08-26-figma-v2/src-auto-main-console-concept-v1.png`
**实现：** `tools/src_auto_gui.ps1`（Windows Forms）
**实机截图：** `validation/gui/src-auto-main-console-2026-08-26.png`

## 对照结果

| 对照项 | 视觉/交互要求 | 实现证据 | 结果 |
| --- | --- | --- | --- |
| 1. 信息架构 | 左侧导航、右侧工作区、首页先展示安全边界 | `Show-SrcAutoMainWindow` 建立 208px 深蓝导航和白色工作区；导航覆盖工作台、本地靶场、目标授权、会话/API、发现报告、蓝队和审计 | 通过 |
| 2. 色彩与层级 | 深蓝导航、白色内容面、钴蓝主操作、绿色安全提示 | `$navColor`、`$accentColor`、`$safeColor` 与首页安全提示面板对应 | 通过 |
| 3. 三步主流程 | 本地靶场、录入授权目标、离线审阅三个入口保持一眼可见 | 三张步骤卡下方的 `actionLocalLab`、目标和离线审阅按钮均为真实控件并置于卡片前 | 通过；`tests.test_desktop_gui` 覆盖 |
| 4. 安全状态 | 首页明确显示“待人工操作”和“真实目标不会自动执行” | header 状态标签和侧栏安全状态固定显示；没有真实目标自动执行按钮 | 通过 |
| 5. 业务/蓝队扩展 | 新增会话/API 复核、蓝队被动分析、审计停止等入口，不改变人工授权边界 | `Show-SessionTaskWindow`、`Show-ProxyApiReviewWindow`、`Show-DefenseObservationWindow`、`Show-AuditSettingsWindow` 均有绑定处理器；审计动作写入项目 `STOP` 标记后关闭窗口 | 通过；点击回归测试通过 |
| 6. 退出与可恢复性 | 关闭、返回和停止动作必须真实生效 | `New-SrcAutoInfoWindow` 将自定义动作绑定到窗口实例，避免把按钮 sender 当作窗体；`test_audit_stop_button_is_real_and_sets_project_stop_marker` 通过 | 通过 |

## 截图说明

截图由本机启动器在不启动 Docker、不访问目标的情况下生成并保存到项目内。当前执行环境的可见桌面宽度小于设计基准，窗口右侧在截图中可能被系统工作区裁切；这属于捕获环境限制，不代表控件点击命中测试失败。控件尺寸、DPI 缩放和导航处理器仍由自动化 GUI 契约测试验证。用户实际使用时建议将窗口最大化或使用至少 1280×800 的工作区。

Figma 导出插件本轮没有产生新的可编辑代码文件，原因是导出额度/连接受限；仓库保留 manifest、信息架构与参考 PNG，生产界面以已验证的本地 Windows Forms 实现为准。该限制不会被描述为“已从 Figma 自动生成生产代码”。

## 交互验收命令

```powershell
Set-Location 'D:\网络安全文件夹\SRC-Auto'
python -m unittest tests.test_desktop_gui tests.test_desktop_workflows tests.test_local_lab_dashboard -v
```

这组测试只检查本地控件、固定回环入口和项目内工件，不会访问外部目标，也不会提交补天报告。
