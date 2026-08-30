from __future__ import annotations

import pytest

from app.domain.services.password_policy import PasswordPolicy, PasswordPolicyError


@pytest.mark.parametrize(
    "password",
    [
        "short",
        "nocaps123!",
        "NOLOWER123!",
        "NoDigits!",
        "NoSpecial123",
    ],
)
def test_password_policy_rejects_invalid(password):
    policy = PasswordPolicy()
    with pytest.raises(PasswordPolicyError):
        policy.validate(password)


def test_password_policy_accepts_valid():
    policy = PasswordPolicy()
    policy.validate("ValidPass123!")


def test_password_policy_custom_rules():
    policy = PasswordPolicy(
        min_length=8,
        require_uppercase=False,
        require_lowercase=True,
        require_digit=False,
        require_special=False,
    )
    policy.validate("validpass")


def test_password_policy_custom_length():
    policy = PasswordPolicy(
        min_length=4,
        require_uppercase=False,
        require_digit=False,
        require_special=False,
    )
    policy.validate("abcd")


def test_password_policy_no_special_required():
    policy = PasswordPolicy(
        require_uppercase=True,
        require_lowercase=True,
        require_digit=True,
        require_special=False,
    )
    policy.validate("ValidPass123")
