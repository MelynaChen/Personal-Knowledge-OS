# Personal Knowledge OS — Daily Dashboard

本地 SQLite 是唯一真实来源；独立 Worker 将新导入的数据单向同步到 Notion。日常操作都可以在浏览器完成，不调用 OpenAI API，也不需要 `OPENAI_API_KEY`。

## 预览
<img width="1477" height="1200" alt="image" src="https://github.com/user-attachments/assets/76a1ce20-e421-4553-be1d-873ee55a79e4" />

## 启动

需要 Python 3.12。首次安装时在项目根目录执行 `python -m venv .venv`、`python -m pip install -e ".[dev]"`；仅首次创建配置文件时复制 `.env.example` 为 `.env`，填入 `NOTION_TOKEN` 和 `NOTION_PARENT_PAGE_ID`，并在 Notion 父页面授权 Integration。不要覆盖已有 `.env`，也不要提交它。

每次更新代码后，先在项目根目录执行：

```powershell
alembic upgrade head
```

Terminal 1，启动网页：

```powershell
cd C:\Users\Melyn\Documents\Codex\2026-09-29\new-chat\personal-knowledge-os
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2，启动同步 Worker：

```powershell
cd C:\Users\Melyn\Documents\Codex\2026-09-29\new-chat\personal-knowledge-os
.\.venv\Scripts\Activate.ps1
python -m app.workers.sync_worker
```

Browser：打开 `http://127.0.0.1:8000` 。已有 FastAPI 进程没有使用 `--reload` 时，修改代码后需重启该进程。

## 每日使用

1. 从 Dashboard 的 **Copy Prompt Context** 打开 Prompt Helper，复制已有知识树和复用规则，粘贴到 ChatGPT 每日任务中。
2. ChatGPT 生成 JSON 后，在 **Import** 页面粘贴，或先用 **Load Example** 试用。
3. 点击 **Preview**。检查日期、知识路径和 `NEW`、`DUPLICATE`、`CONFLICT` 状态；冲突时不能提交。
4. 点击 **Commit & Sync**。这一步才会写入 SQLite；Worker 随后同步到 Notion。页面每 5 秒刷新状态，完成后显示 **Synced to Notion**。示例提交同样会写入真实数据。
5. 在 Dashboard 查看今日任务，点击任务调整本地状态、阅读 Note。在 Reviews 页面给到期复习打 1～5 分。
6. History 可查看原始 JSON、同步步骤与错误，并对可重试的失败操作使用 **Retry Failed Sync**。System 显示连接、队列和数据库状态。

Task Status 的三种值是 `Not started`、`In progress`、`Done`，本阶段仅在本地 SQLite 更新；不会修改已经同步的 Notion 正文。Prompt Helper 只生成可复制文本，不自动调用 ChatGPT。

## 开发与诊断

`/docs` 保留用于开发调试，普通日常使用无需打开。`python -m app.cli notion health`、`notion verify` 和 `sync once` 仍可用于诊断；初始化命令 `python -m app.cli notion init` 可重复执行。自动测试全部使用隔离数据库和 mock，不访问真实 Notion：

```powershell
python -m pytest
```

手动真实 Notion smoke test 为 `python scripts/notion_smoke_test.py`；它会创建带 `TEST-PKOS` 标记的页面，默认不删除。SQLite 位于项目 `data/`，运行中备份应使用 SQLite 在线备份功能，或停机后复制数据库及关联文件。
