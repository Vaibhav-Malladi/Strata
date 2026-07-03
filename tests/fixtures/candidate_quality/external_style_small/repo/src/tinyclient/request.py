def _normalize_timeout(value: float) -> float:
    return max(0.1, value)


def request(path: str, timeout: float) -> tuple[str, float]:
    return path, _normalize_timeout(timeout)
