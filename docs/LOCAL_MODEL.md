# 当前本地模型与迁移说明

核验日期：2026-10-05。适用于本地 `agent/controlled-upgrade` 开发分支，不代表已发布的 v0.11.2 下载包已更新。

> 后续选择更新：用户已改选 **DeepSeek V4.1 Flash** 为 SRC-Auto Agent 主模型（调用 ID `deepseek-flash`），整机已用内存门限改为 30 GiB。Qwen3.5-9B 仅保留为可手动选择的本地模型；下方比较与本地试验中的 20 GiB 均为当时的历史设置。OpenCode 的本地配置不因这次仅针对 SRC-Auto Agent 的选择而再次修改。

## 1. 选择结果

本机统一使用 **Qwen3.5-9B Q4_K_M**，Ollama 名称为 `qwen3.5-local:9b-q4_k_m`。这是官方模型的本地运行参数别名，不是另外训练的新模型，也不会额外复制一份权重。

- SRC-Auto 的 bulk、primary、expert 都指向同一别名；受控 Agent 复用 primary。
- `D:\Codex本地模型` 中 OpenCode 的默认模型、Chat、Plan 和 HYBRID 的本地兜底均改为这个别名。
- 本地权重仍在 `D:\Codex本地模型\models`；`C:\Users\lenovo\.ollama\models` 是指向该位置的目录联接，不是第二份权重。
- 没有修改云端凭据、计费入口或人工同意开关。SRC-Auto 的本地 Agent 不自动转用 DeepSeek；云端 Agent 循环仍保持关闭。
- Ollama 官方运行时和原有工具继续复用，没有安装第二套推理服务。

本机为 i5-13500H、32 GB 内存、Intel Iris Xe，无专用 CUDA 显卡。这个选择优先考虑平台决策、中文说明、资源余量和现有接口兼容，不是四款模型在全部任务上的绝对排名。

## 2. 官方模型对比与日期

| 模型 | 官方发布/首批权重日期 | 定位与取舍 | 本机对应权重文件大小（十进制） |
| --- | --- | --- | --- |
| Qwen3-Coder-30B-A3B-Instruct | 2025-07-31 | 30.5B 总参数、3.3B 激活参数的编码/工具模型；不是 Qwen3-30B-Thinking。权重大，原本加载后整机内存曾约 27 GiB，超过平台 20 GiB 闸门 | 约 18.56 GB |
| GPT-OSS-20B | 2025-08-05 | 约 21B 总参数、3.6B 激活参数的推理/工具模型；某些代码推理指标仍更高 | 约 13.79 GB |
| Qwen3.5-9B | 2026-03-02 | 综合知识、指令跟随和多模态能力；本机选 Q4_K_M 并缩小上下文 | 约 6.55 GB，含 5.63 GB 文本权重和 0.92 GB 视觉投影 |
| MiniCPM5-2B | 2026-09-07 | 实际总参数约 2.52B，非嵌入参数约 1.98B；更轻、更快，但现有非思考受控决策配方下稳定性不如 9B | Q4_K_M 约 1.56 GB |

官方证据：

- [Qwen3-Coder-30B 官方模型卡](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct)与[权重提交历史](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct/commits/main)。
- [OpenAI GPT-OSS 发布说明](https://openai.com/index/introducing-gpt-oss/)。
- [Qwen 官方仓库历史 News](https://github.com/QwenLM/Qwen3.8)记录 Qwen3.5-9B 于 2026-03-02 发布；旧 Qwen3.5 仓库地址目前重定向到这个仓库。
- [Qwen3.5-9B 官方模型卡](https://huggingface.co/Qwen/Qwen3.5-9B)：同一张发布方评测表中，9B 与 GPT-OSS-20B 的 MMLU-Pro 为 82.5/74.8、GPQA Diamond 为 81.7/71.5、IFEval 为 91.5/88.2；LiveCodeBench v6 则为 65.6/74.6，GPT-OSS-20B 更高。
- [MiniCPM 官方更新记录](https://github.com/OpenBMB/MiniCPM)与[MiniCPM5-2B 模型卡](https://huggingface.co/openbmb/MiniCPM5-2B)：其发布方报告 BFCL v4 66.6、IFEval 86.7、MMLU-Pro 70.8、LiveCodeBench v6 69.1；Terminal-Bench v2.1 为 8.6，表中 Qwen3.5-4B 为 25.8。

不同发布方的测试框架、推理预算和配置不完全相同，不能拼成统一排行榜。上面的官方分数也不等于本机 CPU、Q4 量化、短上下文和非思考模式的成绩。新版、参数更少或单项高分都不足以证明适合本平台。

## 3. 本机真实验证及边界

六项决策诊断都通过真正 Ollama 推理，使用现有 AgentModel 提示词、JSON Schema、4K 上下文、6 线程、temperature=0、think=false。它们只包含合成输入，不访问目标网站。

| 模型 | 严格下一步决策通过 | 每次决策耗时中位数 | 推理后整机已用内存采样最大值 |
| --- | --- | --- | --- |
| MiniCPM5-2B Q4_K_M | 3/6 | 2.40 秒 | 10.28 GiB |
| Qwen3.5-9B Q4_K_M | 4/6 | 19.89 秒 | 15.29 GiB |

MiniCPM 的失败主要是重复读取规范；9B 的两项失败是在已有证据时继续检查另一对象，没有按严格评分要求及时结束。**4/6 不是满分，也不是漏洞检出率。**这些结果只评价当前提示词和运行参数，不否定 MiniCPM 在其他推理预算或部署配方中的表现。

进一步用原项目 `lab/business-api/app.py` 建立本机回环原生靶场，调用真实 AgentRunner、模型决策、范围检查、三账号只读请求、候选入库及报告生成。没有模拟模型、放宽 CPU/内存限制或访问非本地目标。

最终指定对象验收（`validation/model-selection-20261005/qwen9-live-targeted/summary.json`）：

- case-01（阳性）：真实检查私有对象；状态 200/200/403；1 个候选；3 个工具动作、5 次 HTTP、4 次模型调用；100.47 秒。
- case-11（已修复阴性）：真实检查私有对象；状态 200/403/403；0 个候选；3 个工具动作、5 次 HTTP、4 次模型调用；91.47 秒。
- 两项均正常结束；`confirmed=false`、`submissionReady=false`，没有自动确认或提交。
- 完成时整机已用内存采样为 15.44/15.67 GiB，CPU 47.17%/51.43%；这不是连续采样峰值保证。

验收选择列表收窄到每项指定私有对象；权限清单仍有效，不向模型提供阳性/阴性答案。它证明两个选定对象能真实完成闭环，**不证明自动覆盖全部对象**。前一轮未收窄列表的阴性任务只检查了公共对象 case-16，虽然候选为零，但没有通过现在的私有对象覆盖条件，不计作最终阴性通过。相应记录保留在 `qwen9-live-serial`。

最初与其他测试并行运行时，CPU 约 80% 触发正常资源暂停，证据保留在 `qwen9-live`。改为串行后通过，未调整 70%/20 GiB 闸门。模型不可用或资源不足时，Agent 应暂停或转人工，不静默切云端；普通旧式候选研判的规则兜底不代表 Agent 仍在真实推理。

其他验收：Python 单元测试 379 项，378 项通过、1 项按环境跳过。OpenCode 原有可靠性自检验证配置加载、运行时自动测试、MCP 目录限制和最终模型存在性。

Ollama 的 OpenAI 兼容接口无害工具诊断中，笼统无参查询曾直接猜测状态；改成带查询编号的明确工具后，模型能返回正确调用，并消费工具回传值。但严格的“只输出状态字段值”要求未通过：输出为 `状态为：LOCAL_ONLY_OK`，不是裸值 `LOCAL_ONLY_OK`。没有把这个严格格式检查计作通过。原始失败输出保留在 `qwen9-tools-roundtrip.json`；随后仅修正诊断器的错误分类，将这种“使用了结果但添加前缀”的情况标为 `output_format_mismatch`，没有修改过去结果或继续跑真实推理。根据用户确认停止扩展验证，这不是完整复杂编码 Agent 回归，也不应声称工具使用永不出错。结构化消费必须保留程序端检查。

本轮没有完成五个 Docker 靶场重新运行、真实授权目标测试或原先暂停的全量长任务代理评价，不能沿用旧成绩宣称新模型已全部通过。

## 4. 参数、安装与重建

便携定义为 `config/Modelfile.local`：默认上下文 16,384、6 线程、最多输出 4,096。SRC-Auto 受控 Agent 的请求显式使用 4,096 上下文和非思考模式，避免仅凭官方 256K 上限在笔记本上分配大缓存。OpenCode 的模型上下文和输出限额同步为 16K/4K，模型选项 `reasoningEffort=none` 请求非思考输出（[OpenCode 模型配置](https://opencode.ai/docs/models/)、[Ollama 兼容努力等级说明](https://docs.ollama.com/api/openai-compatibility)）。Ollama 普通聊天界面的思考开关独立，不被这两套客户端设置强制覆盖。

重启 SRC-Auto 控制台和 OpenCode，以加载新配置。关闭其他高负载任务后再启用本地受控 Agent。手工选择本地模型应使用 `qwen3.5-local:9b-q4_k_m`。

在已安装 Ollama 且模型存储已配置为 D 盘的电脑上，项目根目录执行：

```powershell
ollama pull qwen3.5:9b-q4_K_M
ollama create qwen3.5-local:9b-q4_k_m -f config/Modelfile.local
ollama show qwen3.5-local:9b-q4_k_m
# 别名验证正常后可移除上游标签，权重仍由最终别名引用。
ollama rm qwen3.5:9b-q4_K_M
```

已下载文本权重 SHA256：`02d45dc1cf451ba2475ac33b301c2dd8f985abe4c182ce04a1f2f5bf0260278d`。
视觉投影 SHA256：`f836f08f921193f4d6b6a6952dba0a6fb116759d26a757bcb395d570d73976ca`。
记录用于核对本轮版本；模型标签将来可能变更，不能保证重新拉取一定同哈希。模型支持视觉不代表平台已经接入图片分析前端。

可重跑的显式本地推理验收（每轮真实推理会占 CPU；不要与全量测试并行）：

```powershell
python tools/validate_local_model_selection.py --model qwen3.5-local:9b-q4_k_m --output validation/model-recheck/decisions.json
python tools/validate_local_model_loop.py --output validation/model-recheck/loop
python tools/validate_local_model_tools.py --output validation/model-recheck/tools.json
python -m unittest discover -s tests
```

闭环验证要求新的输出目录，以免覆盖旧证据。严格决策诊断在不满足所有评分条件时返回非零，不应为了显示通过而删掉失败案例。

## 5. 清理与恢复

用户已明确同意将两套平台一起切换，并只保留最终本地模型。清理采用 Ollama 官方 `rm` 指定标签，避免直接删除共享 blob。旧 30B、20B 及其自定义别名、MiniCPM 比较模型、9B 上游重复标签属于本轮清理范围；其他项目、Docker 数据、云端配置、历史任务和运行时均不在清理范围。

迁移前配置、Modelfile 和旧标签元数据保存于 `data/model-migration-20261005/`，该目录已加入 Git 忽略规则，不能进入公开仓库。**没有保留旧模型的大体积权重副本**；若回退，需要先通过官方来源重新下载旧权重，再恢复原配置，并重新评估当前 30 GiB 资源闸门。不要把旧 manifest 单独复制回去冒充已安装权重。

已通过官方 `ollama rm` 清理 10 个多余标签；最后 `/api/tags` 只返回 `qwen3.5-local:9b-q4_k_m`，`ollama show` 仍可正确读取权重、量化信息和运行参数。清理前 34 个 blob 共 40,462,291,604 字节，清理后 6,550,825,872 字节，释放约 33.91 GB（31.58 GiB，包含本轮临时比较模型）；与最初两套旧权重的 32,350,146,798 字节相比，长期净减少约 25.80 GB（24.03 GiB）。计量只针对该模型存储，不以磁盘总剩余空间波动冒充清理量。

原配置和元数据备份保留，权重已删除，恢复旧模型需要重新下载。没有删除项目报告、数据库、用户文件、历史任务或 Docker 数据。本轮只做本地迁移，没有推送 GitHub、更新发布包或改动版本号。Ollama 界面如果仍显示旧列表，可关闭后重新打开刷新。
