def parse_positive_int_ids(values: list[object] | tuple[object, ...] | None) -> list[int]:
    ids: list[int] = []
    for value in values or []:
        try:
            num = int(value)
        except Exception:
            continue
        if num > 0:
            ids.append(num)
    return ids
