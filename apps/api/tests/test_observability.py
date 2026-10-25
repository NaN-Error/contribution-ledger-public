import json
import logging
from app.core.observability import SafeJsonFormatter


def test_logs_only_contain_allowed_fields():
    record = logging.LogRecord("example", logging.ERROR, "test", 1, "SECRET-PASSWORD", (), None)
    record.event = "database_check_failed"
    record.error_type = "RuntimeError"
    record.password = "SECRET-PASSWORD"
    result = SafeJsonFormatter().format(record)
    assert "SECRET-PASSWORD" not in result
    assert "password" not in result
    assert json.loads(result)["error_type"] == "RuntimeError"


def test_uvicorn_error_handler_does_not_render_original_exception():
    from app.core.observability import configure_logging
    configure_logging()
    logger = logging.getLogger("uvicorn.error")
    record = logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 1,
        "private_database_password", (), (RuntimeError, RuntimeError("secret DSN"), None))
    assert logger.propagate is False
    for handler in logger.handlers:
        rendered = handler.format(record)
        assert "private_database_password" not in rendered
        assert "secret DSN" not in rendered
        assert "ERROR" in rendered
