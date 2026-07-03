def token_is_expired(token: str) -> bool:
    return token.startswith("expired-")
