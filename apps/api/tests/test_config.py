import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_password_is_not_in_repr(settings):
    assert "synthetic-test-password" not in repr(settings)
    assert "***" in repr(settings)


@pytest.mark.parametrize("value", ["", "short", "REPLACE_WITH_GENERATED_PASSWORD"])
def test_password_rejects_placeholders(value):
    with pytest.raises(ValidationError):
        Settings(db_password=value)


def test_url_handles_reserved_password_characters():
    settings = Settings(db_password="synthetic:/@#%password-value")
    assert settings.database_url().password == "synthetic:/@#%password-value"
    assert "synthetic" not in str(settings.database_url())


@pytest.mark.parametrize("name", ["has space", "name;DROP TABLE", "UpperCase", "1starts_with_number"])
def test_database_identifiers_are_bounded(name):
    with pytest.raises(ValidationError):
        Settings(db_password="synthetic-test-password", db_name=name)


def test_wildcard_host_is_rejected():
    with pytest.raises(ValidationError):
        Settings(db_password="synthetic-test-password", allowed_hosts=["*"])


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_unsafe_deployment_is_refused(settings, environment):
    from app.main import create_app
    changed = settings.model_copy(update={"environment": environment})
    with pytest.raises(ValueError, match="local pilot"):
        create_app(changed)


def test_validation_error_does_not_echo_input():
    with pytest.raises(ValidationError) as caught:
        Settings(db_password="private-value")
    assert "private-value" not in str(caught.value)
