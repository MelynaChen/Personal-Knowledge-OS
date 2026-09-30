"""Validate the generated SQLite DDL when Alembic is not installed locally."""

import ast
import sqlite3
from pathlib import Path


source = Path("alembic/versions/0001_initial.py").read_text(encoding="utf-8")
module = ast.parse(source)
upgrade = next(item for item in module.body if isinstance(item, ast.FunctionDef) and item.name == "upgrade")
statements = [ast.literal_eval(node.value.args[0]) for node in upgrade.body]
connection = sqlite3.connect(":memory:")
connection.execute("PRAGMA foreign_keys=ON")
for statement in statements:
    connection.execute(statement)
tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
required = {"imports", "import_items", "knowledge_nodes", "tasks", "notes", "reviews",
            "review_events", "notion_objects", "notion_databases", "sync_operations",
            "sync_logs", "settings"}
assert required <= tables, required - tables
print(f"Validated {len(statements)} DDL statements and {len(required)} required tables")
