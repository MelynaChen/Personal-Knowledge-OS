"""The only module that imports and calls notion-client."""
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from app.config.settings import Settings, get_settings

log = logging.getLogger(__name__)


class NotionConfigurationError(RuntimeError):
    pass


@dataclass
class NotionFailure(RuntimeError):
    kind: str
    status: int | None = None
    code: str | None = None
    request_id: str | None = None
    retry_after: float | None = None

    def __str__(self) -> str:
        return f"Notion {self.kind} (status={self.status}, code={self.code}, request_id={self.request_id})"


class UnknownWriteResult(NotionFailure):
    pass


class RemoteConflict(NotionFailure):
    pass


def require_notion_settings(settings: Settings, *, parent: bool = False) -> None:
    if not settings.notion_token:
        raise NotionConfigurationError("NOTION_TOKEN is required for Notion operations")
    if parent and not settings.notion_parent_page_id:
        raise NotionConfigurationError("NOTION_PARENT_PAGE_ID is required for Notion initialization")


class NotionGateway:
    def __init__(self, settings: Settings | None = None, sdk: Any | None = None):
        self.settings = settings or get_settings()
        require_notion_settings(self.settings)
        if sdk is None:
            try:
                from notion_client import Client
            except ImportError as exc:
                raise NotionConfigurationError("notion-client is not installed") from exc
            sdk = Client(auth=self.settings.notion_token, notion_version="2025-09-03",
                         timeout_ms=int(self.settings.notion_api_timeout * 1000), retry=False,
                         log_level=logging.WARNING)
        self.sdk = sdk
        self._lock = threading.Lock()
        self._next_at = 0.0

    def _rate_limit(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_at - now)
            self._next_at = max(now, self._next_at) + 1.0 / self.settings.notion_rate_limit_per_second
        if delay:
            time.sleep(delay)

    def _call(self, endpoint: str, method: str, *, write: bool = False, **kwargs) -> dict:
        function = self.sdk
        for part in f"{endpoint}.{method}".split("."):
            function = getattr(function, part)
        for attempt in range(self.settings.notion_max_retries + 1):
            self._rate_limit()
            try:
                return function(**kwargs)
            except Exception as exc:
                status = getattr(exc, "status", None)
                code = getattr(exc, "code", None)
                headers = getattr(exc, "headers", None) or {}
                request_id = getattr(exc, "request_id", None) or (headers.get("x-request-id") if hasattr(headers, "get") else None)
                retry_header = headers.get("retry-after") if hasattr(headers, "get") else None
                retry_after = float(retry_header) if retry_header and str(retry_header).replace(".", "", 1).isdigit() else None
                kind = ("rate_limited" if status == 429 else "permission" if status in (401, 403) else
                        "not_found" if status == 404 else "remote_conflict" if status == 409 else
                        "validation" if status == 400 else
                        "server" if status in (500, 502, 503, 504, 529) else "transport")
                failure = NotionFailure(kind, status, str(code) if code else None, request_id, retry_after)
                log.warning("notion request failed method=%s endpoint=%s attempt=%s status=%s code=%s request_id=%s",
                            method, endpoint, attempt + 1, status, code, request_id)
                if write and kind in ("server", "transport"):
                    raise UnknownWriteResult(**failure.__dict__) from None
                retryable = kind == "rate_limited" or (not write and kind in ("server", "transport"))
                if not retryable or attempt >= self.settings.notion_max_retries:
                    raise failure from None
                time.sleep(retry_after if retry_after is not None else min(2 ** attempt, 30))
        raise AssertionError("unreachable")

    def retrieve_page(self, page_id: str) -> dict:
        return self._call("pages", "retrieve", page_id=page_id)

    def retrieve_database(self, database_id: str) -> dict:
        return self._call("databases", "retrieve", database_id=database_id)

    def retrieve_data_source(self, data_source_id: str) -> dict:
        return self._call("data_sources", "retrieve", data_source_id=data_source_id)

    def create_database(self, **payload) -> dict:
        return self._call("databases", "create", write=True, **payload)

    def update_data_source(self, data_source_id: str, properties: dict) -> dict:
        return self._call("data_sources", "update", write=True, data_source_id=data_source_id, properties=properties)

    def query_data_source(self, data_source_id: str, **kwargs) -> dict:
        return self._call("data_sources", "query", data_source_id=data_source_id, **kwargs)

    def create_page(self, **payload) -> dict:
        return self._call("pages", "create", write=True, **payload)

    def append_children(self, block_id: str, children: list[dict]) -> dict:
        return self._call("blocks", "children.append", write=True, block_id=block_id, children=children)

    def list_children(self, block_id: str, **kwargs) -> dict:
        return self._call("blocks.children", "list", block_id=block_id, **kwargs)

    def retrieve_block(self, block_id: str) -> dict:
        return self._call("blocks", "retrieve", block_id=block_id)
