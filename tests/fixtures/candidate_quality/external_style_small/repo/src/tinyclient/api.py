def fetch_user(timeout: float) -> tuple[str, float]:
    return "/user", max(0.1, timeout)
