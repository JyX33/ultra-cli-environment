
import pytest


def test_config_loads_environment_variables(monkeypatch):
    """Test that the Config class correctly loads environment variables."""
    # Set mock environment variables
    monkeypatch.setenv("REDDIT_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_client_secret")
    monkeypatch.setenv("REDDIT_USER_AGENT", "test_user_agent")
    monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")

    # Import config after setting environment variables
    from app.core.config import Config

    # Assert that the configuration loaded the mocked environment variables
    assert Config.REDDIT_CLIENT_ID == "test_client_id"
    assert Config.REDDIT_CLIENT_SECRET == "test_client_secret"
    assert Config.REDDIT_USER_AGENT == "test_user_agent"
    assert Config.OPENAI_API_KEY == "test_openai_key"


def test_config_validation_success(monkeypatch):
    """Test that config validation passes when all variables are set."""
    # Set all required environment variables
    monkeypatch.setenv("REDDIT_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_client_secret")
    monkeypatch.setenv("REDDIT_USER_AGENT", "test_user_agent")
    monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")

    from app.core.config import Config

    # Validation should pass without raising an exception
    assert Config.validate_config() is True


def test_config_validation_failure_missing_variables(monkeypatch):
    """Test that config validation fails when required variables are missing."""
    # Clear all environment variables
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("REDDIT_USER_AGENT", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.core.config import Config

    # Validation should raise ValueError for missing variables
    with pytest.raises(ValueError) as exc_info:
        Config.validate_config()

    assert "Missing required environment variables" in str(exc_info.value)
    assert "REDDIT_CLIENT_ID" in str(exc_info.value)
    assert "REDDIT_CLIENT_SECRET" in str(exc_info.value)
    assert "REDDIT_USER_AGENT" in str(exc_info.value)
    assert "OPENAI_API_KEY" in str(exc_info.value)


def test_config_validation_partial_missing_variables(monkeypatch):
    """Test that config validation fails when some variables are missing."""
    # Set only some environment variables
    monkeypatch.setenv("REDDIT_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("REDDIT_USER_AGENT", "test_user_agent")
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.core.config import Config

    # Validation should raise ValueError for missing variables
    with pytest.raises(ValueError) as exc_info:
        Config.validate_config()

    error_message = str(exc_info.value)
    assert "Missing required environment variables" in error_message
    assert "REDDIT_CLIENT_SECRET" in error_message
    assert "OPENAI_API_KEY" in error_message
    # These should not be in the error message since they are set
    assert "REDDIT_CLIENT_ID" not in error_message.split(": ")[1]
    assert "REDDIT_USER_AGENT" not in error_message.split(": ")[1]
