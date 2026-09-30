from typing import Callable, Iterator


def paginated(call: Callable[..., dict], **kwargs) -> Iterator[dict]:
    cursor = None
    while True:
        payload = dict(kwargs)
        payload["page_size"] = 100
        if cursor:
            payload["start_cursor"] = cursor
        response = call(**payload)
        yield from response.get("results", [])
        if not response.get("has_more"):
            return
        cursor = response.get("next_cursor")
        if not cursor:
            raise ValueError("Notion returned has_more without next_cursor")
