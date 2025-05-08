"""
Integration tests for the RVC2API application.

These tests use the FastAPI TestClient to send HTTP requests to the API
endpoints and verify their responses and side effects. They are designed
to test the interaction between different components of the application,
from the API routers down to the core logic, with appropriate mocking
for external dependencies like actual CAN bus communication.
"""

from fastapi.testclient import TestClient

# Assuming your FastAPI app instance is created in `core_daemon.main.app`
# If it's elsewhere, adjust the import path accordingly.
from core_daemon.main import app

client = TestClient(app)


def test_healthz_endpoint():
    """Test /healthz endpoint for API responsiveness and expected status."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# Add more integration tests below, for example:
# def test_get_entities_unauthenticated_or_empty():
#     response = client.get("/entities")
#     assert response.status_code == 200 # or 401/403 if auth is implemented
#     # Add more assertions based on expected behavior for an empty or unauthenticated state

# def test_control_light_flow():
#     # This would be a more complex test involving:
#     # 1. Ensuring a light entity exists (perhaps by mocking app_state or pre-populating)
#     # 2. Sending a control command
#     # 3. Verifying the optimistic update via another API call or checking mocks
#     # 4. Verifying CAN command was "sent" (mocking can_manager)
#     pass

# Remember to mock external dependencies like CAN communication or actual hardware state
# for reliable and isolated integration tests.
