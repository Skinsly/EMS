from collections.abc import Sequence


def parse_positive_int_ids(values: Sequence[object] | None) -> list[int]:
    ids: list[int] = []
    for value in values or []:
        try:
            num = int(str(value))
        except Exception:
            continue
        if num > 0:
            ids.append(num)
    return ids
