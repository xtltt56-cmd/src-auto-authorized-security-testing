[CmdletBinding()]
param(
    [string]$ProjectRoot = 'D:\网络安全文件夹\SRC-Auto',
    [string]$Destination = 'D:\网络安全文件夹\SRC-Auto\.worktrees\rollback-pre-storybook'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$tag = 'baseline-pre-storybook-20260826'

if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    throw "项目目录不存在：$ProjectRoot"
}

$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
if ([System.IO.Path]::GetFullPath($Destination).StartsWith([System.IO.Path]::GetFullPath($resolvedProject + '\'), [System.StringComparison]::OrdinalIgnoreCase) -eq $false) {
    throw "回退工作树必须位于项目目录下：$Destination"
}

if (Test-Path -LiteralPath $Destination) {
    throw "目标目录已存在，为避免覆盖数据而停止：$Destination"
}

$tagExists = git -C $resolvedProject tag --list $tag
if (-not $tagExists) {
    throw "找不到基线标签 $tag。请先确认仓库已包含可回退提交。"
}

git -C $resolvedProject worktree add --detach $Destination $tag
if ($LASTEXITCODE -ne 0) {
    throw "创建基线工作树失败，退出码：$LASTEXITCODE"
}

Write-Host "已创建回退基线工作树：$Destination"
Write-Host "基线标签：$tag"
Write-Host '该工作树不会覆盖当前源码，也不会删除运行期数据。'
