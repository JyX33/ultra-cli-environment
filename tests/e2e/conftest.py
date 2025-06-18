# ABOUTME: Pytest fixtures for E2E testing with real Docker containers
# ABOUTME: Manages Docker services for integration testing with actual API services

from collections.abc import Generator
from pathlib import Path
import time

import httpx
import pytest
from testcontainers.compose import DockerCompose  # type: ignore[import-untyped]


@pytest.fixture(scope="session")
def docker_compose_services() -> Generator[DockerCompose, None, None]:
    """Start Docker Compose services for E2E testing."""
    # Get the project root directory
    project_root = Path(__file__).parent.parent.parent

    # Ensure test environment file exists
    env_test_path = project_root / "tests" / "e2e" / ".env.test"
    if not env_test_path.exists():
        pytest.skip(
            "E2E test environment file not found. Create tests/e2e/.env.test with real API credentials."
        )

    # Start Docker Compose services (without waiting for health checks)
    compose = DockerCompose(
        context=str(project_root),
        compose_file_name="docker-compose.test.yml",
        wait=False,  # Don't wait for health checks, we'll do our own
    )

    with compose:
        # Wait for services to be healthy with longer timeout
        # Docker services take time to build and start
        _wait_for_service_health("http://localhost:8000/", timeout=180)
        _wait_for_service_health("http://localhost:8001/", timeout=180)

        yield compose


@pytest.fixture(scope="session")
def standard_api_url(docker_compose_services: DockerCompose) -> str:
    """URL for the standard API server."""
    return "http://localhost:8000"


@pytest.fixture(scope="session")
def optimized_api_url(docker_compose_services: DockerCompose) -> str:
    """URL for the optimized API server."""
    return "http://localhost:8001"


@pytest.fixture(scope="function")
def http_client() -> Generator[httpx.Client, None, None]:
    """HTTP client for making API requests."""
    with httpx.Client(timeout=60.0) as client:
        yield client


@pytest.fixture(scope="session")
def test_subreddit() -> str:
    """Test subreddit name for E2E tests."""
    return "ClaudeAI"


@pytest.fixture(scope="session")
def test_topic() -> str:
    """Test topic for E2E tests."""
    return "Claude Code"


def _wait_for_service_health(url: str, timeout: int = 60) -> None:
    """Wait for a service to become healthy."""
    start_time = time.time()
    last_error = None

    print(f"Waiting for service at {url} to become healthy...")

    while time.time() - start_time < timeout:
        try:
            with httpx.Client() as client:
                response = client.get(url, timeout=10.0)
                if response.status_code == 200:
                    print(f"Service at {url} is healthy!")
                    return
                else:
                    last_error = f"HTTP {response.status_code}"
        except (httpx.RequestError, httpx.TimeoutException) as e:
            last_error = str(e)

        elapsed = int(time.time() - start_time)
        print(f"  Still waiting... ({elapsed}s elapsed, last error: {last_error})")
        time.sleep(3)

    raise TimeoutError(
        f"Service at {url} did not become healthy within {timeout} seconds. Last error: {last_error}"
    )


@pytest.fixture(scope="session")
def clean_database(
    docker_compose_services: DockerCompose,
) -> Generator[None, None, None]:
    """Clean the database before and after each test."""
    # Clean before test
    _clean_test_database(docker_compose_services)

    yield

    # Clean after test
    _clean_test_database(docker_compose_services)


def _clean_test_database(compose: DockerCompose) -> None:
    """Clean test database by removing test data but keeping schema."""
    try:
        # Execute database cleanup command with proper command format
        cleanup_cmd = "psql -U testuser -d testdb -c 'TRUNCATE TABLE reddit_posts, comments, check_runs, post_snapshots CASCADE;'"
        result = compose.exec_in_container("postgres", ["sh", "-c", cleanup_cmd])
        print(f"Database cleanup result: {result}")
    except Exception as e:
        # If cleanup fails, it's not critical for test execution
        print(f"Database cleanup warning: {e}")


@pytest.fixture(scope="function")
def api_rate_limit_delay() -> Generator[None, None, None]:
    """Add delay between tests to respect API rate limits."""
    yield
    # Wait 2 seconds between tests to respect Reddit API rate limits
    time.sleep(2)
