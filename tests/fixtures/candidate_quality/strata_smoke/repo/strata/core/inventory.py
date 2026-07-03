def inventory_limit(limit: int | None) -> int | None:
    return None if limit is None else limit + 1
