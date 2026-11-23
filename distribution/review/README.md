# SRC-Auto 本地审阅版

面向 Windows x64，可打开 UTF-8 Markdown、TXT、JSON 报告，也可用固定版本 Bandit 对有权读取的 Python 项目做离线静态审阅。安装完成后可离线使用。规则提示需人工复核。

## 安装和更新

1. 在 [仓库 Releases](https://github.com/xtltt56-cmd/src-auto-authorized-security-testing/releases) 中找到名称含「本地审阅版」、标签以 `review-v` 开头的正式发行。下载 `SRC-Auto-Review-Setup.exe`，并用该发行的 `REVIEW-SHA256SUMS.txt` 核对安装器。
2. 双击安装器，选择 D 盘的上级目录。安装器创建 `SRC-Auto-Review` 子目录，显示版本和下载大小，经确认后下载。
3. 日常从安装目录双击 `SRC-Auto-Review.exe`。手动运行 `SRC-Auto-Review-Update.exe` 可检查更新，有上一版时也可回退。新版本自检成功后才切换，报告由用户自行选择保存位置。
4. 打开本机报告，或选择有权限的 Python 源码目录，确认读取后开始审阅。结果可另存为 TXT。

也可下载同一发行里的审阅版 ZIP，核对摘要并解压后，在解压目录运行 `.\python\pythonw.exe -I -B .\review.py`。手动解压适用于单独运行，自动维护版本目录和回退使用联网安装器。

## 构建与发行

构建需要 Windows x64 Python 3.12 和仓库的便携 Python 目录。`bandit-windows-x64.lock` 固定了 Bandit 和依赖的版本及 Windows wheel 摘要。

`py -3.12 distribution/review/build.py --version 0.18.0`

产物在 `artifacts/review-dist/`，包括 EXE、版本化 ZIP 和 `REVIEW-SHA256SUMS.txt`。构建会用包内运行时初始化窗口并实际运行 Bandit。对外发行使用独立标签，例如 `review-v0.18.0`，同时上传三个产物，取消 GitHub 的「Set as the latest release」选项，以保留仓库现有的正式下载入口。发布后确认 ZIP 资产已提供 SHA-256 摘要。后续发行递增审阅版版本号。

安装器读取 GitHub 公共发行列表，按版本号选择正式审阅版。下载使用版本化 URL，并核对资产大小和 GitHub 提供的 SHA-256。当前 EXE 没有 Windows 代码签名，系统可能提示未知发布者。
