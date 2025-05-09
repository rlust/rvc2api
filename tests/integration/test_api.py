"""
Integration tests for the RVC2API application.

These tests use the FastAPI TestClient to send HTTP requests to the API
endpoints and verify their responses and side effects. They are designed
to test the interaction between different components of the application,
from the API routers down to the core logic, with appropriate mocking
for external dependencies like actual CAN bus communication.
"""

# No longer need these, client fixture handles it
# from fastapi.testclient import TestClient
# from core_daemon.main import app

# client = TestClient(app) # Replaced by fixture


def test_healthz_endpoint(client):  # Inject client fixture
    """Test /healthz endpoint for API responsiveness and expected status."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# Add more integration tests below, for example:
# def test_get_entities_unauthenticated_or_empty(client, mock_app_state): # Example with mocks
#     # mock_app_state.get_all_entities.return_value = []
#     response = client.get("/entities")
#     assert response.status_code == 200 # or 401/403 if auth is implemented
#     # Add more assertions based on expected behavior for an empty or unauthenticated state

# async def test_control_light_flow(async_client, mock_app_state, mock_can_manager): # Example async
#     # This would be a more complex test involving:
#     # 1. Ensuring a light entity exists (perhaps by mocking app_state or pre-populating)
#     # mock_app_state.get_entity.return_value = YourLightEntity(...)
#     # 2. Sending a control command
#     response = await async_client.post("/lights/1/control", json={"state": "on"})
#     # 3. Verifying the optimistic update via another API call or checking mocks
#     assert response.status_code == 200
#     # 4. Verifying CAN command was "sent" (mocking can_manager)
#     # mock_can_manager.send_can_message_async.assert_called_once_with(...)
#     pass

# Remember to mock external dependencies like CAN communication or actual hardware state
# for reliable and isolated integration tests using fixtures like mock_app_state
# and mock_can_manager.
