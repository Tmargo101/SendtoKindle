from __future__ import annotations

import hashlib
import hmac
from typing import Dict

from send_to_kindle.models import UserRecord


class AuthenticationError(Exception):
    pass


class UserRegistry:
    def __init__(self, users: Dict[str, UserRecord]):
        self._users = users

    def get_user_for_token(self, token: str) -> UserRecord:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        for user in self._users.values():
            if hmac.compare_digest(user.token_hash, token_hash):
                return user
        raise AuthenticationError("Invalid API token")

    def get_user_by_id(self, user_id: str) -> UserRecord:
        user = self._users.get(user_id)
        if user is None:
            raise AuthenticationError(f"Unknown user_id {user_id}")
        return user

    def is_empty(self) -> bool:
        return not self._users
