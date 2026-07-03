def truncation_metadata(records_count: int, limit: int | None) -> bool:
    return limit is not None and records_count > limit
