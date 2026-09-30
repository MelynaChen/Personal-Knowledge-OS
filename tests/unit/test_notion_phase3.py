"""Offline contract tests: no real Notion client or network access."""
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.database.base import Base
from app.database.engine import make_engine
from app.models import ImportRecord, KnowledgeNode, NotionDatabase, NotionObject, SyncOperation, Task
from app.notion.blocks import CONTAINER_MARKER, block_batches, note_blocks, task_blocks
from app.notion.client import NotionConfigurationError, NotionFailure, NotionGateway, RemoteConflict, UnknownWriteResult, require_notion_settings
from app.notion.databases import TITLES, SchemaMismatch, initialize_databases, verify_notion_schema
from app.notion.properties import knowledge_properties, rich, split_rich_text_content
from app.api.sync_routes import import_status, retry_import
from app.database.session import get_session
from app.main import app
from app.services.commit_service import PreviewMismatch, commit_import
from app.services.import_service import preview_import
from app.workers.sync_worker import SyncWorker


class FakeNotion:
    def __init__(self):
        self.settings = Settings(_env_file=None, notion_token="mock", notion_parent_page_id="parent")
        self.pages = {}
        self.blocks = {}
        self.creates = 0
        self.fail_once = None
        self.remote_duplicates = False

    def query_data_source(self, data_source_id, **kwargs):
        external_id = kwargs["filter"]["rich_text"]["equals"]
        pages = [p for p in self.pages.values() if p["data_source_id"] == data_source_id and p["external_id"] == external_id]
        if self.remote_duplicates and pages:
            pages = pages * 2
        return {"results": pages, "has_more": False}

    def create_page(self, parent, properties):
        if self.fail_once:
            failure = self.fail_once
            self.fail_once = None
            raise failure
        self.creates += 1
        page_id = f"page-{self.creates}"
        external_id = properties["External ID"]["rich_text"][0]["text"]["content"]
        page = {"id": page_id, "external_id": external_id, "data_source_id": parent["data_source_id"]}
        self.pages[page_id] = page
        return page

    def retrieve_page(self, page_id):
        return self.pages[page_id]

    def list_children(self, block_id, **kwargs):
        return {"results": self.blocks.get(block_id, []), "has_more": False}

    def append_children(self, block_id, children):
        result = []
        for child in children:
            new = {**child, "id": f"block-{sum(map(len, self.blocks.values())) + 1}"}
            self.blocks.setdefault(block_id, []).append(new)
            result.append(new)
        return {"results": result}


class FakeSchemaNotion(FakeNotion):
    def __init__(self):
        super().__init__()
        self.databases = {}
        self.sources = {}
        self.database_creates = 0
        self.next_property = 0

    def _property(self, name, definition):
        self.next_property += 1
        kind = next(iter(definition))
        return {"id": f"property-{self.next_property}", "name": name, "type": kind,
                kind: definition[kind]}

    def create_database(self, parent, title, initial_data_source):
        self.database_creates += 1
        database_id = f"db-{self.database_creates}"
        source_id = f"ds-{self.database_creates}"
        name = title[0]["text"]["content"]
        properties = {label: self._property(label, definition)
                      for label, definition in initial_data_source["properties"].items()}
        self.sources[source_id] = {"id": source_id, "properties": properties}
        self.databases[database_id] = {"id": database_id, "data_sources": [{"id": source_id}], "title": name}
        return self.databases[database_id]

    def retrieve_database(self, database_id):
        return self.databases[database_id]

    def retrieve_data_source(self, data_source_id):
        return self.sources[data_source_id]

    def list_children(self, block_id, **kwargs):
        if block_id == "parent":
            return {"results": [{"id": db["id"], "type": "child_database",
                                 "child_database": {"title": db["title"]}}
                                for db in self.databases.values()], "has_more": False}
        return super().list_children(block_id, **kwargs)

    def retrieve_page(self, page_id):
        return {"id": "parent"} if page_id == "parent" else super().retrieve_page(page_id)

    def update_data_source(self, data_source_id, properties):
        source = self.sources[data_source_id]["properties"]
        for label, definition in properties.items():
            if "name" in definition and label.startswith("property-"):
                target = next(p for p in source.values() if p["id"] == label)
                del source[target["name"]]
                target["name"] = definition["name"]
                source[target["name"]] = target
                continue
            relation = definition["relation"]
            target_id = relation["data_source_id"]
            value = self._property(label, {"relation": relation.copy()})
            if relation["type"] == "dual_property":
                reverse = self._property("temporary reverse", {"relation": {
                    "data_source_id": data_source_id, "type": "dual_property",
                    "dual_property": {"synced_property_id": value["id"]}}})
                self.sources[target_id]["properties"][reverse["name"]] = reverse
                value["relation"]["dual_property"] = {"synced_property_id": reverse["id"]}
            source[label] = value
        return self.sources[data_source_id]


@pytest.fixture
def queue_db(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'queue.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        for name in TITLES:
            session.add(NotionDatabase(logical_name=name, database_id=f"db-{name}",
                                       data_source_id=f"ds-{name}", init_step="completed",
                                       property_ids_json={}))
    yield factory
    engine.dispose()


def committed(factory, sample_json):
    with factory.begin() as session:
        preview_hash = preview_import(session, sample_json)["preview_hash"]
        return commit_import(session, sample_json, preview_hash).id


def test_notion_config_missing():
    with pytest.raises(NotionConfigurationError):
        require_notion_settings(Settings(_env_file=None, notion_token=""))


def test_notion_database_init(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'init.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    fake = FakeSchemaNotion()
    rows = initialize_databases(factory, fake)
    assert set(rows) == set(TITLES)
    assert fake.database_creates == 4
    engine.dispose()


def test_notion_database_init_idempotent(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'init2.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    fake = FakeSchemaNotion()
    initialize_databases(factory, fake)
    initialize_databases(factory, fake)
    assert fake.database_creates == 4
    engine.dispose()


def test_notion_schema_verify(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'verify.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    fake = FakeSchemaNotion()
    initialize_databases(factory, fake)
    fake.sources["ds-1"]["properties"].pop("External ID")
    with pytest.raises(SchemaMismatch, match="External ID"):
        verify_notion_schema(factory, fake)
    engine.dispose()


def test_relation_mapping(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'relations.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    fake = FakeSchemaNotion()
    rows = initialize_databases(factory, fake)
    notes = fake.sources[rows["notes"].data_source_id]["properties"]
    tasks = fake.sources[rows["daily_tasks"].data_source_id]["properties"]
    assert notes["Related Task"]["relation"]["dual_property"]["synced_property_id"] == tasks["Notes"]["id"]
    engine.dispose()


def test_long_rich_text_split():
    parts = split_rich_text_content("a" * 4501)
    assert list(map(len, parts)) == [1800, 1800, 901]
    assert all(len(x["text"]["content"]) <= 2000 for x in rich("a" * 4501)["rich_text"])


def test_property_payload(queue_db, sample_json):
    committed(queue_db, sample_json)
    with queue_db() as session:
        node = session.scalar(select(KnowledgeNode).order_by(KnowledgeNode.id))
        props = knowledge_properties(node, None)
        assert props["External ID"]["rich_text"][0]["text"]["content"] == node.node_key
        assert props["Parent"] == {"relation": []}


def test_note_blocks():
    blocks = note_blocks(SimpleNamespace(content_json={"summary": "hello", "key_concepts": ["one"]}))
    assert any(b["type"] == "bulleted_list_item" for b in blocks)
    assert block_batches(blocks, "hash")[0][0]["paragraph"]["rich_text"][0]["text"]["content"].startswith("PKOS:BATCH:")


def test_task_blocks():
    blocks = task_blocks(SimpleNamespace(learning_goal="goal", action_steps_json=["step"], output_required="output"), ["AI"])
    assert any(b["type"] == "bulleted_list_item" for b in blocks)


def test_commit_creates_sync_operations(queue_db, sample_json):
    import_id = committed(queue_db, sample_json)
    with queue_db() as session:
        assert session.get(ImportRecord, import_id).status == "pending"
        steps = [op.step for op in session.scalars(select(SyncOperation).order_by(SyncOperation.id))]
        assert steps == ["CREATE_KNOWLEDGE_PAGE"] * 4 + ["CREATE_TASK_PAGE", "WRITE_TASK_BLOCKS",
                                                     "CREATE_NOTE_PAGE", "WRITE_NOTE_BLOCKS", "CREATE_REVIEW_PAGE", "VERIFY_OBJECT"]


def test_commit_bad_hash(queue_db, sample_json):
    with queue_db.begin() as session:
        with pytest.raises(PreviewMismatch):
            commit_import(session, sample_json, "0" * 64)


def test_commit_api_queues_without_notion(queue_db, sample_json):
    def override():
        with queue_db() as session:
            yield session
    app.dependency_overrides[get_session] = override
    try:
        client = TestClient(app)
        preview = client.post("/import/preview", json={"raw_text": sample_json})
        assert preview.status_code == 200
        commit = client.post("/import/commit", json={"raw_text": sample_json,
                                                       "preview_hash": preview.json()["preview_hash"]})
        assert commit.status_code == 202
        assert client.get(f"/imports/{commit.json()['import_id']}").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_worker_dependency_order(queue_db, sample_json):
    committed(queue_db, sample_json)
    fake = FakeNotion()
    worker = SyncWorker(queue_db, fake, check_schema=False)
    assert worker.run_once(20) == 10
    with queue_db() as session:
        assert all(op.status == "completed" for op in session.scalars(select(SyncOperation)))
    assert fake.creates == 7


def test_worker_completed_not_repeated(queue_db, sample_json):
    committed(queue_db, sample_json)
    fake = FakeNotion()
    worker = SyncWorker(queue_db, fake, check_schema=False)
    worker.run_once(20)
    assert worker.run_once(20) == 0
    assert fake.creates == 7


def test_worker_retry(queue_db, sample_json):
    committed(queue_db, sample_json)
    fake = FakeNotion()
    fake.fail_once = NotionFailure("rate_limited", status=429)
    worker = SyncWorker(queue_db, fake, check_schema=False)
    worker.run_once(1)
    with queue_db() as session:
        op = session.scalar(select(SyncOperation).order_by(SyncOperation.id))
        assert op.status == "pending" and op.attempts == 1 and op.next_attempt_at


def test_worker_permanent_failure(queue_db, sample_json):
    committed(queue_db, sample_json)
    fake = FakeNotion()
    fake.fail_once = NotionFailure("permission", status=403)
    SyncWorker(queue_db, fake, check_schema=False).run_once(1)
    with queue_db() as session:
        assert session.scalar(select(SyncOperation).order_by(SyncOperation.id)).status == "failed"


def test_worker_unknown_create_result(queue_db, sample_json):
    committed(queue_db, sample_json)
    fake = FakeNotion()
    fake.fail_once = UnknownWriteResult("transport")
    SyncWorker(queue_db, fake, check_schema=False).run_once(1)
    with queue_db() as session:
        op = session.scalar(select(SyncOperation).order_by(SyncOperation.id))
        assert op.status == "pending" and op.result_json == {"uncertain_checks": 1}
    assert fake.creates == 0


def test_remote_external_id_recovery(queue_db, sample_json):
    committed(queue_db, sample_json)
    with queue_db() as session:
        op = session.scalar(select(SyncOperation).order_by(SyncOperation.id))
        external = session.get(__import__("app.models", fromlist=["KnowledgeNode"]).KnowledgeNode, op.local_id).node_key
    fake = FakeNotion()
    fake.pages["existing"] = {"id": "existing", "data_source_id": "ds-knowledge_tree", "external_id": external}
    SyncWorker(queue_db, fake, check_schema=False).run_once(1)
    with queue_db() as session:
        mapping = session.scalar(select(NotionObject).where(NotionObject.local_id == op.local_id))
        assert mapping.notion_page_id == "existing"
    assert fake.creates == 0


def test_duplicate_external_id_remote_conflict(queue_db, sample_json):
    committed(queue_db, sample_json)
    with queue_db() as session:
        op = session.scalar(select(SyncOperation).order_by(SyncOperation.id))
        external = session.get(__import__("app.models", fromlist=["KnowledgeNode"]).KnowledgeNode, op.local_id).node_key
    fake = FakeNotion()
    fake.pages["existing"] = {"id": "existing", "data_source_id": "ds-knowledge_tree", "external_id": external}
    fake.remote_duplicates = True
    SyncWorker(queue_db, fake, check_schema=False).run_once(1)
    with queue_db() as session:
        assert session.get(SyncOperation, op.id).status == "failed"


def test_import_retry(queue_db, sample_json):
    import_id = committed(queue_db, sample_json)
    with queue_db.begin() as session:
        op = session.scalar(select(SyncOperation).order_by(SyncOperation.id))
        op.status = "failed"
        op.last_error = "Notion transport"
    with queue_db() as session:
        response = retry_import(import_id, session)
    assert response["requeued"] == 1
    with queue_db() as session:
        assert import_status(import_id, session)["items"][0]["notion_sync_status"] == "pending"


def test_token_not_logged(caplog):
    token = "secret-test-token"
    class ExplodingPages:
        def retrieve(self, **kwargs):
            raise RuntimeError(token)
    gateway = NotionGateway(Settings(_env_file=None, notion_token=token, notion_max_retries=0),
                           sdk=SimpleNamespace(pages=ExplodingPages()))
    with pytest.raises(NotionFailure):
        gateway.retrieve_page("test")
    assert token not in caplog.text
