"""Notion setup and one-shot worker commands."""
import argparse
import json
import sys

from app.api.sync_routes import notion_health
from app.database.session import SessionLocal
from app.notion.client import NotionGateway
from app.notion.databases import initialize_databases, verify_notion_schema
from app.workers.sync_worker import SyncWorker


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument("group", choices=["notion", "sync"])
    parser.add_argument("action", choices=["health", "init", "verify", "once"])
    args = parser.parse_args(argv)
    if (args.group, args.action) not in {("notion", "health"), ("notion", "init"),
                                         ("notion", "verify"), ("sync", "once")}:
        parser.error("unsupported command")
    try:
        if args.action == "health":
            result = notion_health()
            print(json.dumps(result))
            return 0 if result["schema_valid"] else 1
        gateway = NotionGateway()
        if args.action == "init":
            rows = initialize_databases(SessionLocal, gateway)
            print(json.dumps({"initialized": sorted(rows)}))
        elif args.action == "verify":
            verify_notion_schema(SessionLocal, gateway)
            print(json.dumps({"schema_valid": True}))
        else:
            count = SyncWorker(SessionLocal, gateway).run_once()
            print(json.dumps({"processed": count}))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)[:500]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
