# Personal Knowledge OS — Phase 3

SQLite 是业务数据的唯一真实来源。用户把 ChatGPT Plus 生成的 JSON 粘贴到导入接口；系统先保存到 SQLite，再由独立 Worker 单向同步到 Notion。程序不调用 OpenAI API，也不需要 `OPENAI_API_KEY`。

## 安装和本地服务

初次使用需要 Python 3.12。在 PowerShell 中：

```powershell
cd C:\Users\Melyn\Documents\Codex\2026-09-29\new-chat\personal-knowledge-os
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env  # 仅首次创建，已有 .env 时不要覆盖
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

完成配置后的启动方式
```powershell
cd C:\Users\Melyn\Documents\Codex\2026-09-29\new-chat\personal-knowledge-os\.venv\Scripts
python -m venv .venv
python -m app.workers.sync_worker
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/docs` 查看 API。未配置 Notion 时，本地预览、提交和 FastAPI 均可使用；初始化、Worker 和同步需要 Notion 配置。

### 网页导入示范

打开 `http://127.0.0.1:8000/`。点击“载入示例 JSON”（或粘贴自己的 JSON），再点“预览”。确认任务和知识路径后，点“提交并同步”。页面会显示 Import ID，并每 5 秒刷新 Worker 同步状态。载入示例和预览不会写入数据；只有提交会写入 SQLite，并让 Worker 向 Notion 创建页面。修改 JSON 后必须重新预览。若 FastAPI 已经在运行且没有使用 `--reload`，更新代码后先重启 FastAPI 进程。

## Notion 配置

1. 在 Notion 的 integrations 页面创建内部 Integration，复制其密钥到 `.env` 的 `NOTION_TOKEN`。不要把 `.env` 加入版本控制。
2. 创建一个供本系统使用的父页面，用该页面菜单的 **Connections / Add connections** 授权刚创建的 Integration。
3. 复制父页面 URL 中的页面 ID 到 `.env` 的 `NOTION_PARENT_PAGE_ID`。
4. 执行初始化与检查：

```powershell
python -m app.cli notion health
python -m app.cli notion init
python -m app.cli notion verify
```

`notion init` 可以重跑：程序先检查 SQLite 记录和父页面已有数据库，再补建缺失的四个数据库、Relation 和 Property ID。若用户手工删除或改动必需字段，验证会返回 `SchemaMismatch`，同步会停止。

## 导入与同步

先向 `POST /import/preview` 发送 `{"raw_text":"...JSON..."}`，取得 `preview_hash`。再向 `POST /import/commit` 发送相同 `raw_text` 和 `preview_hash`。提交仅写 SQLite 和持久队列，返回 HTTP 202、`import_id`、`sync_status`。

在另一终端启动独立 Worker：

```powershell
cd C:\Users\Melyn\Documents\Codex\2026-09-29\new-chat\personal-knowledge-os
.\.venv\Scripts\Activate.ps1
python -m app.workers.sync_worker
```

开发时可用 `python -m app.cli sync once` 执行一批待处理操作。`GET /imports/{id}` 返回每项本地保存与 Notion 同步状态；`POST /imports/{id}/retry` 只重新排队可重试的失败操作。

远端页面按 `External ID` 检索和绑定。创建结果未知时会延迟复查，不能立即重复 POST。正文保存在应用专用 Toggle 内，批次标记用于重试恢复；用户在 Toggle 外添加的内容不会被清理。首次写入后内容默认不变；内容哈希改变时需要人工处理，Phase 3 不自动合并。Notion → SQLite 同步尚未实现。

## 测试与手动 Smoke Test

自动化测试全部使用 mock，不调用真实 Notion：

```powershell
python -m pytest -q
```

只有在配置好 Token、父页面并明确希望在真实 Notion 写入测试页时，手动执行：

```powershell
python scripts/notion_smoke_test.py
```

该脚本会初始化 Schema、创建一个带 `TEST-PKOS` 标记的知识页并读回。默认不删除测试页。SQLite 数据库位于 `data/`，运行中备份请使用 SQLite 在线备份功能，或停机后复制数据库及关联文件。
