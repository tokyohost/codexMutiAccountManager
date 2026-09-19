# Codex Account Manager

Codex Account Manager 是一个本地运行的 Windows 托盘应用，用于管理多个 ChatGPT Plus / Codex 账号。应用共用一个 `CODEX_HOME`，每个账号只保存独立的 `auth.json` 登录快照，不会复制或修改用户的代码项目、Git 分支和工作区。

## 特性

- pywebview + 系统 Microsoft Edge WebView2 Runtime 托盘应用和单实例保护，不再内置 Chromium。
- Vue 3 + TypeScript + Vite + Pinia + Element Plus 现代化界面，支持浅色、深色和跟随系统。
- 从当前 Codex Home 导入账号；仅保存 `auth.json`，并通过第二次 `account/read` 验证邮箱一致才落盘。
- 可在保存当前账号后直接进入“登录其他账号”流程：不调用 logout，只移走活动认证文件并启动未登录状态的 Codex。
- Sessions、历史、插件、Skills 和用户配置共用，账号支持改名、删除、额度缓存和倒计时。
- 使用官方 `codex app-server` 读取账号和多额度桶，不读取或上传 Token。
- 切换前检测 Codex 进程，可在确认后关闭进程；共享 `CODEX_HOME` 保持不变，仅原子替换登录状态。
- 配置原子写入、日志滚动与敏感信息脱敏，账号数据卸载时默认保留。
- GitHub Actions 自动构建 PyInstaller onedir 和 Inno Setup 当前用户安装器。

## 开发环境

- Windows 10/11
- Python 3.12+
- Node.js 22+
- 已安装并登录 Codex CLI；应用会自动检查 PATH、npm 全局目录和常见 Windows 安装目录，无需手动配置 PATH
- 也支持 OpenAI Codex Desktop 的 `%LOCALAPPDATA%\OpenAI\Codex\bin\<版本>\codex.exe` 安装方式
- Windows 10/11 建议安装 Microsoft Edge WebView2 Runtime（大多数系统已预装）
- Inno Setup 6（仅打包安装器需要）

安装依赖：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements-dev.txt
cd frontend
npm ci
```

## 本地运行

先构建 Vue 页面：

```powershell
cd frontend
npm run build
cd ..
py main.py
```

前端开发时可启动 Vite：

```powershell
cd frontend
npm run dev
```

然后在另一个终端设置 `CODEX_MANAGER_DEV_URL=http://localhost:5173` 后启动 Python。开发模式才会使用 Vite Dev Server；生产包只加载本地 `frontend/dist/index.html`，不会启动 HTTP Server。

## 打包

构建顺序是 Vue → PyInstaller onedir → Inno Setup：

```powershell
.\scripts\build_installer.ps1
```

输出文件：

```text
release/CodexAccountManager-1.0.0-Setup-x64.exe
```

PyInstaller 使用 `CodexAccountManager.spec`，安装后的机器不需要 Python、Node 或 npm。GitHub Actions 的 `build.yml` 在 push、pull request 和手动触发时上传 Installer artifact；推送 `v1.0.0` 形式的 tag 会由 `release.yml` 创建 GitHub Release，并同时发布 `SHA256SUMS.txt`。

普通分支构建完成后不会自动创建 Release；发布时请先提交代码，再执行 `git tag v1.0.0` 和 `git push origin v1.0.0`。

## CODEX_HOME 工作机制

旧版本的应用数据位于 `%LOCALAPPDATA%\CodexAccountManager`：

```text
config.json
accounts\<uuid>\codex_home\
logs\app.log
```

当前版本改为认证快照目录结构：

```text
config.json
accounts\<uuid>\auth.json
logs\app.log
```

每个账号只保存一份本机明文 `auth.json` 快照。当前 `CODEX_HOME` 中的 sessions、history、插件、Skills、缓存和用户配置由所有账号共享。切换时应用会先保存当前账号可能已经刷新的认证文件，再通过临时文件、`fsync` 和 `os.replace` 原子替换活动 `auth.json`；二次验证失败会自动恢复原登录状态。

从旧版本升级时，已有 `accounts\<uuid>\codex_home` 会在首次使用该账号时提取为新的认证快照。旧目录在删除该账号前保留，避免自动迁移造成数据丢失。

如果 Codex 使用 Windows Credential Manager 保存凭据，凭据不会随目录复制。请在 Codex 配置中设置：

```toml
cli_auth_credentials_store = "file"
```

然后重新登录，再执行导入。应用不会读取、导出或打印 Credential Manager 中的 Token。

## 安全说明

这是 100% 本地应用。应用不会将 `auth.json`、Token、JWT、Authorization Header 或 API Key 写入配置、日志、Git 或第三方服务。日志只记录账号 ID、邮箱、Home 路径、App Server 状态和错误摘要，并会对常见敏感字段脱敏。

切换账号不会执行 `codex logout` 或 `account/logout`，也不会改变用户代码项目；它只原子替换共享 Home 中的活动 `auth.json`。已经运行的 Codex 进程可能缓存旧登录状态，因此切换前必须关闭，并在完成后重新启动。

添加多个账号时，先保存当前账号，再点击“登录其他账号”。应用会先同步当前账号最新认证快照，然后移走共享 Home 中的活动 `auth.json` 并启动 Codex 登录界面；此过程不会请求服务端注销。新账号登录完成后，回到账号管理器点击“添加当前账号”即可。

## 测试

```powershell
py -m pytest
```

测试覆盖配置损坏备份、无 BOM 原子写入、额度新旧返回结构和日志脱敏。真实额度读取需要本机安装 Codex 并登录，因此不会在单元测试中打印或模拟真实凭据。
