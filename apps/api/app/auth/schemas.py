import re
from typing import Annotated
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, AfterValidator, SecretStr, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def email_address(value: str) -> str:
    value = value.strip().lower()
    # The invited pilot supports ordinary ASCII email addresses; no claim of
    # mailbox verification. The invitation must be delivered to the intended owner.
    if len(value) > 254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value):
        raise ValueError("Enter an ordinary email address.")
    if ".." in value:
        raise ValueError("Email address contains consecutive dots.")
    return value


def clean_name(value: str) -> str:
    value = value.strip()
    if not 2 <= len(value) <= 120 or any(ord(ch) < 32 for ch in value):
        raise ValueError("Use 2 to 120 printable characters.")
    return value


def timezone_name(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("Use an installed IANA timezone, such as UTC or America/Puerto_Rico.") from None
    return value


Email = Annotated[str, AfterValidator(email_address)]
Name = Annotated[str, AfterValidator(clean_name)]
Timezone = Annotated[str, Field(max_length=80), AfterValidator(timezone_name)]
def clean_reason(value: str) -> str:
    value = value.strip()
    if not 8 <= len(value) <= 500 or any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
        raise ValueError("Give an explanation of 8 to 500 printable characters.")
    return value


Reason = Annotated[str, Field(min_length=8, max_length=500), AfterValidator(clean_reason)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class PasswordInput(Input):
    password: SecretStr

    @field_validator("password")
    @classmethod
    def password_policy(cls, value: SecretStr) -> SecretStr:
        text = value.get_secret_value()
        if not 15 <= len(text) <= 128 or not text.strip():
            raise ValueError("Use a password or passphrase of 15 to 128 characters.")
        return value


class LoginInput(Input):
    email: Email
    password: SecretStr

    @field_validator("password")
    @classmethod
    def bounded_password(cls, value: SecretStr) -> SecretStr:
        if not 1 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Invalid password length.")
        return value


class BootstrapInput(PasswordInput):
    token: str = Field(min_length=43, max_length=43, repr=False)
    email: Email
    display_name: Name
    workspace_name: Name
    project_name: Name
    timezone: Timezone = "UTC"


class TokenInput(Input):
    token: str = Field(min_length=43, max_length=43, repr=False)


class RecoveryInput(PasswordInput):
    token: str = Field(min_length=43, max_length=43, repr=False)


class PasswordChangeInput(PasswordInput):
    current_password: SecretStr

    @field_validator("current_password")
    @classmethod
    def current_bounded(cls, value: SecretStr) -> SecretStr:
        if not 1 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Invalid password length.")
        return value


class InviteAcceptInput(Input):
    token: str = Field(min_length=43, max_length=43, repr=False)
    display_name: Name | None = None
    password: SecretStr | None = None

    @field_validator("password")
    @classmethod
    def new_password(cls, value: SecretStr | None) -> SecretStr | None:
        return PasswordInput.password_policy(value) if value is not None else None


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    display_name: str
