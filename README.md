# Codex Account Manager

Codex Account Manager 是一个本地运行的 Windows 托盘应用，用于管理多个 ChatGPT Plus / Codex 账号。它为每个账号维护独立的 `CODEX_HOME`，切换账号只修改 Codex 的用户级环境变量，不会复制或修改用户的代码项目、Git 分支和工作区。

## 特性

- PySide6 托盘应用、单实例、QWebEngineView 和 QWebChannel。
- Vue 3 + TypeScript + Vite + Pinia + Element Plus 现代化界面，支持浅色、深色和跟随系统。
- 从当前 Codex Home 导入账号；复制后通过第二次 `account/read` 验证邮箱一致才保存。
- 账号独立保存完整 `CODEX_HOME`，支持改名、删除、打开目录、额度缓存和倒计时。
- 使用官方 `codex app-server` 读取账号和多额度桶，不读取或上传 Token。
- 切换前检测 Codex 进程，可在确认后关闭进程；通过 HKCU 注册表和 `WM_SETTINGCHANGE` 更新 `CODEX_HOME`。
- 配置原子写入、日志滚动与敏感信息脱敏，账号数据卸载时默认保留。
- GitHub Actions 自动构建 PyInstaller onedir 和 Inno Setup 当前用户安装器。

## 开发环境

- Windows 10/11
- Python 3.12+
- Node.js 22+
- 已安装并登录 Codex CLI，且 `codex` 在 PATH 中
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

## CODEX_HOME 工作机制

应用数据位于 `%LOCALAPPDATA%\CodexAccountManager`：

```text
config.json
accounts\<uuid>\codex_home\
logs\app.log
```

每个账号的 `auth.json`、sessions、history 和用户级配置都留在它自己的 Home 中。导入时复制一次，之后切换只将 `CODEX_HOME` 指向目标目录。代码项目目录完全共享，不会被应用复制、删除或切换。

如果 Codex 使用 Windows Credential Manager 保存凭据，凭据不会随目录复制。请在 Codex 配置中设置：

```toml
cli_auth_credentials_store = "file"
```

然后重新登录，再执行导入。应用不会读取、导出或打印 Credential Manager 中的 Token。

## 安全说明

这是 100% 本地应用。应用不会将 `auth.json`、Token、JWT、Authorization Header 或 API Key 写入配置、日志、Git 或第三方服务。日志只记录账号 ID、邮箱、Home 路径、App Server 状态和错误摘要，并会对常见敏感字段脱敏。

切换账号不会执行 `codex logout` 或 `account/logout`，也不会改变用户代码项目；它只切换 `CODEX_HOME`。已经打开的 Terminal、IDE 和 VS Code 不会自动更新环境变量，建议重新打开它们，或使用界面中的启动 Codex 按钮。

## 测试

```powershell
py -m pytest
```

测试覆盖配置损坏备份、无 BOM 原子写入、额度新旧返回结构和日志脱敏。真实额度读取需要本机安装 Codex 并登录，因此不会在单元测试中打印或模拟真实凭据。
