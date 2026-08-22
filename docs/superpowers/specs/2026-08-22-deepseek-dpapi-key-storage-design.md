# DeepSeek API 密钥 DPAPI 存储设计

## 目标

为 SRC-Auto 提供一次性安全录入和后续自动加载 DeepSeek API 密钥的能力，同时保留每次启动时的人工授权硬门。密钥及其加密文件只能位于 `D:\网络安全文件夹\SRC-Auto` 范围内，不得以明文写入脚本、配置、数据库、日志、报告或 Git。

## 方案选择

采用 Windows Data Protection API（DPAPI）的当前用户保护模式。PowerShell 使用 `ConvertFrom-SecureString` 将隐藏输入的 `SecureString` 转换为绑定当前 Windows 用户和当前电脑的加密文本，并保存到：

```text
D:\网络安全文件夹\SRC-Auto\config\secrets\deepseek_api_key.dpapi
```

不采用系统或用户环境变量持久化，因为其长期明文暴露面较大；不采用 Windows 凭据管理器，因为用户要求项目内容只放在指定 D 盘目录中。

## 组件

### 一次性保存工具

新增 `tools/save_deepseek_key.ps1`：

- 先说明保存范围和 DPAPI 限制；
- 使用 `Read-Host -AsSecureString` 隐藏录入；
- 拒绝空输入；
- 使用当前用户 DPAPI 加密；
- 只写入固定的项目内路径；
- 不输出密钥、长度、哈希或加密内容；
- 成功后清理临时变量并显示简体中文结果；
- 使用 UTF-8 BOM，兼容 Windows PowerShell 5.1。

### 启动器加载

修改 `START_SYSTEM.ps1`：

1. 启动时先询问是否启用 DeepSeek；
2. 选择否、回车或无效输入时，设置会话同意为禁用，不读取加密文件；
3. 选择是时，优先使用当前进程已有的 `DEEPSEEK_API_KEY`；
4. 当前进程没有密钥时，尝试从固定 DPAPI 文件解密；
5. 解密成功后仅把明文放入当前启动进程的环境变量；
6. 文件不存在或解密失败时，显示明确提示并回退到现有隐藏输入流程；
7. 不因密钥存在而自动调用 DeepSeek；真实请求仍需人工执行 `remote-triage`。

### Git 排除

在 `.gitignore` 中排除 `config/secrets/`。即使文件内容已经由 DPAPI 加密，也不得提交到版本控制。

## 数据流

```text
一次性隐藏输入
  -> SecureString
  -> 当前用户 DPAPI 加密
  -> D 盘固定加密文件

每次启动
  -> 人工选择否：不读取文件，远程 AI 硬门关闭
  -> 人工选择是：读取并由 DPAPI 解密
  -> 仅当前进程环境变量
  -> 仍需人工 remote-triage 才会联网
```

## 失败和安全行为

- 空输入：不创建或覆盖加密文件；
- 保存失败：显示通用错误，不显示密钥或异常中的敏感正文；
- 解密失败：不调用 API，提示重新保存；
- 文件由其他用户或其他电脑复制而来：DPAPI 解密失败并保持远程 AI 禁用；
- 选择否：不得读取 DPAPI 文件，远程 Provider 在网络连接前返回 `remote_ai_disabled_for_session`；
- API 密钥轮换：重新运行保存工具，原加密文件在同一固定路径被新加密内容替换；
- 威胁边界：DPAPI 可防止磁盘文件被直接读取为明文，但无法防御已经控制当前 Windows 用户会话的恶意程序。

## 验证

实现必须满足以下测试：

- 保存工具和启动器均为 UTF-8 BOM，Windows PowerShell 5.1 解析错误为零；
- 保存工具包含隐藏输入和 DPAPI 加密，不使用 `setx`，不写明文密钥；
- 加密文件不包含测试明文，并可由同一 Windows 用户解密为原值；
- 选择否时不执行读取或解密路径，网络请求为零；
- 选择是且加密文件有效时，启动器能够加载密钥但不自动调用远程 API；
- 解密失败时保持禁用并显示简体中文提示；
- 完整 Python 自动化测试、PowerShell 语法检查和中文乱码扫描通过。

## 验收标准

用户只需在保存工具中再输入一次新密钥。此后每次启动只回答是否启用 DeepSeek：选择是时自动加载，选择否时不读取、不解密、不调用。项目和检测输出中不得出现密钥明文。
