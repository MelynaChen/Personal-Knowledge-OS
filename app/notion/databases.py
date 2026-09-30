"""Four data sources, one relation definition per link, and strict verification."""
from sqlalchemy import select

from app.models import NotionDatabase
from app.notion.client import NotionConfigurationError, RemoteConflict, require_notion_settings
from app.notion.pagination import paginated

TITLES = {"knowledge_tree": "Knowledge Tree", "daily_tasks": "Daily Tasks",
          "notes": "Notes", "review_queue": "Review Queue"}


def _base_properties() -> dict[str, dict]:
    common = {"External ID": {"rich_text": {}}, "Content Hash": {"rich_text": {}},
              "Sync Status": {"select": {"options": [{"name": name} for name in
                                 ("pending", "processing", "completed", "partial", "failed", "needs_update")]}},
              "Schema Version": {"number": {}}}
    return {
        "knowledge_tree": {"Name": {"title": {}}, "Level": {"number": {}}, "Path": {"rich_text": {}},
                           "Category": {"select": {}}, "Description": {"rich_text": {}}, **common},
        "daily_tasks": {"Name": {"title": {}}, "Date": {"date": {}}, "Status": {"status": {}},
                        "Priority": {"select": {"options": [{"name": x} for x in ("Low", "Medium", "High")]}},
                        "Category": {"select": {}}, "Learning Goal": {"rich_text": {}},
                        "Action Steps": {"rich_text": {}}, "Output Required": {"rich_text": {}},
                        "Source": {"select": {"options": [{"name": "ChatGPT Plus"}]}}, **common},
        "notes": {"Title": {"title": {}}, "Date": {"date": {}},
                  **{name: {"rich_text": {}} for name in ("Summary", "Key Concepts", "Detailed Explanation",
                      "Examples", "Practice", "My Understanding", "Questions", "Common Mistakes",
                      "Next Topics", "Resources")}, **common},
        "review_queue": {"Name": {"title": {}}, "Initial Learning Date": {"date": {}},
                         "Review Level": {"number": {}}, "Next Review Date": {"date": {}},
                         "Status": {"select": {"options": [{"name": x} for x in
                                      ("Scheduled", "Paused", "Completed")]}},
                         "Difficulty": {"select": {"options": [{"name": x} for x in
                                          ("Easy", "Medium", "Hard")]}},
                         "Memory Score": {"number": {}}, **common},
    }


BASE_PROPERTIES = _base_properties()
RELATIONS = (
    ("knowledge_tree", "Parent", "knowledge_tree", None),
    ("daily_tasks", "Knowledge Node", "knowledge_tree", "Related Tasks"),
    ("notes", "Knowledge Node", "knowledge_tree", "Related Notes"),
    ("notes", "Related Task", "daily_tasks", "Notes"),
    ("review_queue", "Knowledge Node", "knowledge_tree", None),
    ("review_queue", "Related Note", "notes", "Reviews"),
    ("review_queue", "Related Task", "daily_tasks", "Review"),
)


class SchemaMismatch(RuntimeError):
    def __init__(self, differences: list[str]):
        self.differences = differences
        super().__init__("Notion schema mismatch: " + "; ".join(differences))


def _data_source_id(gateway, database: dict) -> str:
    sources = database.get("data_sources") or []
    if not sources:
        database = gateway.retrieve_database(database["id"])
        sources = database.get("data_sources") or []
    if len(sources) != 1:
        raise SchemaMismatch([f"database {database['id']} must have exactly one data source"])
    return sources[0].get("id") or sources[0]["data_source_id"]


def _find_child_database(gateway, parent_page_id: str, title: str) -> dict | None:
    found = [block for block in paginated(gateway.list_children, block_id=parent_page_id)
             if block.get("type") == "child_database" and block.get("child_database", {}).get("title") == title]
    if len(found) > 1:
        raise RemoteConflict("duplicate_database")
    return gateway.retrieve_database(found[0]["id"]) if found else None


def initialize_databases(session_factory, gateway) -> dict[str, NotionDatabase]:
    require_notion_settings(gateway.settings, parent=True)
    gateway.retrieve_page(gateway.settings.notion_parent_page_id)
    for logical_name, title in TITLES.items():
        with session_factory.begin() as session:
            row = session.scalar(select(NotionDatabase).where(NotionDatabase.logical_name == logical_name))
            if row is None:
                session.add(NotionDatabase(logical_name=logical_name, init_step="pending",
                                           property_ids_json={}, schema_version=1))
        with session_factory() as session:
            row = session.scalar(select(NotionDatabase).where(NotionDatabase.logical_name == logical_name))
            saved_id = row.database_id
        if saved_id:
            database = gateway.retrieve_database(saved_id)
        else:
            database = _find_child_database(gateway, gateway.settings.notion_parent_page_id, title)
            if database is None:
                database = gateway.create_database(
                    parent={"type": "page_id", "page_id": gateway.settings.notion_parent_page_id},
                    title=[{"type": "text", "text": {"content": title}}],
                    initial_data_source={"properties": BASE_PROPERTIES[logical_name]})
            data_source_id = _data_source_id(gateway, database)
            with session_factory.begin() as session:
                row = session.scalar(select(NotionDatabase).where(NotionDatabase.logical_name == logical_name))
                row.database_id = database["id"]
                row.data_source_id = data_source_id
                row.init_step = "base_created"
    with session_factory() as session:
        mapping = {row.logical_name: (row.database_id, row.data_source_id)
                   for row in session.scalars(select(NotionDatabase)) if row.logical_name in TITLES}
    for source, name, target, reverse_name in RELATIONS:
        source_id = mapping[source][1]
        target_id = mapping[target][1]
        properties = gateway.retrieve_data_source(source_id)["properties"]
        if name not in properties:
            relation = {"data_source_id": target_id,
                        "type": "dual_property" if reverse_name else "single_property",
                        "dual_property" if reverse_name else "single_property": {}}
            gateway.update_data_source(source_id, {name: {"relation": relation}})
            properties = gateway.retrieve_data_source(source_id)["properties"]
        actual = properties[name]
        if actual.get("type") != "relation" or actual["relation"].get("data_source_id") != target_id:
            raise SchemaMismatch([f"{source}.{name} points to the wrong data source"])
        if reverse_name:
            reverse = actual["relation"].get("dual_property", {})
            reverse_id = reverse.get("synced_property_id")
            if not reverse_id:
                raise SchemaMismatch([f"{source}.{name} has no reciprocal property ID"])
            target_properties = gateway.retrieve_data_source(target_id)["properties"]
            matched = next((p for p in target_properties.values() if p.get("id") == reverse_id), None)
            if matched is None:
                raise SchemaMismatch([f"{target}.{reverse_name} reciprocal property is missing"])
            if matched.get("name") != reverse_name:
                gateway.update_data_source(target_id, {reverse_id: {"name": reverse_name}})
    for logical_name in TITLES:
        props = gateway.retrieve_data_source(mapping[logical_name][1])["properties"]
        with session_factory.begin() as session:
            row = session.scalar(select(NotionDatabase).where(NotionDatabase.logical_name == logical_name))
            row.property_ids_json = {name: value["id"] for name, value in props.items()}
            row.init_step = "completed"
    verify_notion_schema(session_factory, gateway)
    with session_factory() as session:
        return {row.logical_name: row for row in session.scalars(select(NotionDatabase))
                if row.logical_name in TITLES}


def verify_notion_schema(session_factory, gateway) -> None:
    differences = []
    with session_factory() as session:
        rows = {row.logical_name: row for row in session.scalars(select(NotionDatabase))}
        for name in TITLES:
            row = rows.get(name)
            if not row or not row.database_id or not row.data_source_id:
                differences.append(f"{name}: missing database/data source ID")
                continue
            try:
                database = gateway.retrieve_database(row.database_id)
                source = gateway.retrieve_data_source(row.data_source_id)
            except Exception:
                differences.append(f"{name}: database or data source is not accessible")
                continue
            if row.data_source_id not in [item.get("id") or item.get("data_source_id")
                                          for item in database.get("data_sources", [])]:
                differences.append(f"{name}: data source does not belong to database")
            properties = source.get("properties", {})
            for label, definition in BASE_PROPERTIES[name].items():
                expected_type = next(iter(definition))
                actual = properties.get(label)
                if actual is None or actual.get("type") != expected_type:
                    differences.append(f"{name}.{label}: expected {expected_type}")
                elif row.property_ids_json.get(label) != actual.get("id"):
                    differences.append(f"{name}.{label}: property ID changed")
            for relation_source, label, target, reverse_name in RELATIONS:
                if relation_source != name and not (reverse_name and target == name):
                    continue
                actual = properties.get(label if relation_source == name else reverse_name)
                target_row = rows.get(target if relation_source == name else relation_source)
                if target_row is None or not target_row.data_source_id:
                    differences.append(f"{name}: related data source is missing")
                    continue
                expected_target = target_row.data_source_id
                if not actual or actual.get("type") != "relation" or actual["relation"].get("data_source_id") != expected_target:
                    differences.append(f"{name}.{label if relation_source == name else reverse_name}: relation mismatch")
                elif row.property_ids_json.get(label if relation_source == name else reverse_name) != actual.get("id"):
                    differences.append(f"{name}.{label if relation_source == name else reverse_name}: property ID changed")
    if differences:
        raise SchemaMismatch(differences)
