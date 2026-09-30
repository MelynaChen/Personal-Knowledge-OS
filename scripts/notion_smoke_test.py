"""Manual, opt-in Notion smoke test. Creates one TEST page; never deletes data."""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import get_settings
from app.database.session import SessionLocal
from app.notion.client import NotionGateway, require_notion_settings
from app.notion.databases import initialize_databases, verify_notion_schema
from app.notion.pagination import paginated
from app.notion.properties import metadata, title


def main() -> int:
    settings = get_settings()
    require_notion_settings(settings, parent=True)
    gateway = NotionGateway(settings)
    parent = gateway.retrieve_page(settings.notion_parent_page_id)
    # print("configured:", settings.notion_parent_page_id)
    # print("returned:  ", parent["id"])
    assert UUID(parent["id"]) == UUID(settings.notion_parent_page_id)
    rows = initialize_databases(SessionLocal, gateway)
    verify_notion_schema(SessionLocal, gateway)
    source_id = rows["knowledge_tree"].data_source_id
    marker = f"TEST-PKOS-{uuid4().hex}"
    properties = {"Name": title(marker), "Level": {"number": 1},
                  "Path": {"rich_text": [{"type": "text", "text": {"content": marker}}]},
                  **metadata(marker, marker)}
    created = gateway.create_page(parent={"type": "data_source_id", "data_source_id": source_id},
                                  properties=properties)
    found = list(paginated(gateway.query_data_source, data_source_id=source_id,
                           filter={"property": "External ID", "rich_text": {"equals": marker}}))
    assert len(found) == 1 and found[0]["id"] == created["id"]
    print(f"Smoke test passed. TEST page ID: {created['id']}. No cleanup was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
