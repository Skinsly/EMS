from collections.abc import Mapping


def stripped_text(value: object) -> str:
    return f"{value or ''}".strip()


def normalized_lower(value: object) -> str:
    return stripped_text(value).lower()


def payload_text(payload: Mapping[str, object], key: str, default: str = "") -> str:
    return stripped_text(payload.get(key, default))
