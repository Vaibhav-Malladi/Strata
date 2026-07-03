def _token_is_expired(token: str) -> bool:
    return token.startswith("expired-")


def refresh_token(token: str) -> str:
    return "fresh-token" if _token_is_expired(token) else token
