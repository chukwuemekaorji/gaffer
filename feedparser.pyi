from typing import Any

class FeedParserDict(dict[str, Any]):
    entries: list[dict[str, Any]]


def parse(data: Any) -> FeedParserDict: ...
