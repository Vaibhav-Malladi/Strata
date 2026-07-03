def _request(path: str, timeout: float) -> tuple[str, float]:
    return path, max(0.1, timeout)


def test_timeout_is_normalized():
    assert _request("/health", 0)[1] == 0.1
