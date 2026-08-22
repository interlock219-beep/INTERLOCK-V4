from dataclasses import dataclass


@dataclass
class PasswordResetRequest:
    email: str


@dataclass
class PasswordResetConfirm:
    token: str
    new_password: str


@dataclass
class EmailVerificationRequest:
    email: str


@dataclass
class EmailVerificationConfirm:
    token: str
