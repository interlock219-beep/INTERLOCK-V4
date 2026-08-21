from __future__ import annotations

import re


class PasswordPolicyError(Exception):
    """Raised when a password does not meet policy requirements."""


class PasswordPolicy:
    """Validates passwords against configurable policy rules."""

    def __init__(
        self,
        min_length: int = 12,
        require_uppercase: bool = True,
        require_lowercase: bool = True,
        require_digit: bool = True,
        require_special: bool = True,
    ) -> None:
        self._min_length = min_length
        self._require_uppercase = require_uppercase
        self._require_lowercase = require_lowercase
        self._require_digit = require_digit
        self._require_special = require_special

    def validate(self, password: str) -> None:
        if len(password) < self._min_length:
            raise PasswordPolicyError(
                f"Password must be at least {self._min_length} characters."
            )
        if self._require_uppercase and not re.search(r"[A-Z]", password):
            raise PasswordPolicyError("Password must contain at least one uppercase letter.")
        if self._require_lowercase and not re.search(r"[a-z]", password):
            raise PasswordPolicyError("Password must contain at least one lowercase letter.")
        if self._require_digit and not re.search(r"[0-9]", password):
            raise PasswordPolicyError("Password must contain at least one digit.")
        if self._require_special and not re.search(r"[^A-Za-z0-9]", password):
            raise PasswordPolicyError("Password must contain at least one special character.")
