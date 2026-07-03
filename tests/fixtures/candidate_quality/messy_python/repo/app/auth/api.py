def _refresh_token(token: str) -> str:
    return "fresh-token" if token.startswith("expired-") else token


def refresh(request_token: str) -> dict[str, str]:
    return {"token": _refresh_token(request_token)}
