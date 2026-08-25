# SRC-Auto 架构

```text
scope_candidate / scope_confirmed
              |
        ScopePolicy + ScopeGuard（失败关闭）
              |
      CLI -> SQLite Store -> 可恢复的流水线
              |                 |
      预算/磁盘/资源/STOP       外部适配器（可选）
              |
      归一化 -> 指纹/差异 -> 本地 AI 分诊
              |
      最小证据 -> 补天人工报告草稿

已有 Finding -> 脱敏预览 + SHA-256 摘要 -> 人工确认
              -> 一次 DeepSeek V4 Flash 审阅（或关闭的 OpenAI 适配器）
              -> ai_reviews 审计（不会覆盖本地分诊）

本地 Juice Shop 验证（独立、精确白名单）：

local_only.json + 已确认的回环 Scope
        -> preflight（仅 127.0.0.1/localhost:3000）
        -> 有界只读 GET / 重定向复查
        -> httpx + katana 表面发现（并发最多 5）
        -> 扫描后 Ground Truth 对比
        -> 基线/回归工件 + 人工报告
```

## 模块

- `src_auto.scope`：URL 解析、主机/端口匹配、重定向检查和 Scope 摘要；
- `src_auto.store`：SQLite 运行、资产快照/差异、Finding 去重、证据、检查点、报告、本地核算和独立 `ai_reviews`；
- `src_auto.controls`：预算、项目目录磁盘、资源和人工 STOP 门控；
- `src_auto.adapters`：BBOT、Subfinder、httpx、Katana、Nuclei、reconFTW、ZAP 的版本/状态检查和安全子进程边界；
- `src_auto.live_plan`：验证人工编写的外部计划，拒绝 Shell/危险标记，并在适配器启动前记录稳定摘要；
- `src_auto.pipeline`：确定性的 local-lab E2E 和失败关闭的外部门控，不虚构扫描器行为；
- `src_auto.ai`：bulk/primary/expert 路由、本地 Ollama 和无 API 启发式回退；这是唯一自动 AI 路径；
- `src_auto.remote_ai`：人工选择的 HTTPS DeepSeek/OpenAI transport，带数据最小化、严格 JSON、单次请求和 token 限制；
- `src_auto.runtime_policy`：Juice Shop 本地验证的本地 AI、精确主机/端口、重定向和并发硬门控；
- `src_auto.juice_shop`：有界本地 preflight/发现适配器，不启动 Docker、不扩展外链、不保留响应正文，并写入中文说明字段；
- `src_auto.i18n`：简体中文状态/原因映射、CLI 安全摘要和 `_zh` JSON 说明字段；
- `src_auto.validation`：官方元数据 Ground Truth 解析、保守分类、Finding 归一化和扫描后指标；
- `src_auto.reporting`：最小证据打包和中文人工复核报告草稿。

控制层不会重新实现第三方扫描器。官方工具缺失时状态为 `unavailable`，系统不会把 fixture
结果显示成实时扫描结果。交互式 CLI 和 `START_SYSTEM.ps1` 使用简体中文；机器 JSON 仍保留
英文字段和枚举值，以便审计和自动化解析。
