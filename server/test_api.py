from datetime import date, timedelta

from fastapi.testclient import TestClient

from server.app import create_app


def auth(client: TestClient) -> dict[str, str]:
    register = client.post("/auth/register", json={"email": "maya@example.com", "display_name": "Maya", "password": "safe-pass-123"})
    assert register.status_code == 201
    login = client.post("/auth/login", json={"email": "maya@example.com", "password": "safe-pass-123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['token']}"}


def test_auth_transaction_dashboard_and_prediction(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    headers = auth(client)
    current = date.today().replace(day=1)
    for offset, amount in ((3, 100), (2, 200), (1, 300)):
        month = current
        for _ in range(offset):
            month = (month - timedelta(days=1)).replace(day=1)
        response = client.post("/transactions", headers=headers, json={"amount": amount, "date": month.isoformat(), "note": "test expense"})
        assert response.status_code == 201
    dashboard = client.get("/dashboard", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["summary"]["total"] == 0.0
    prediction = client.get("/prediction", headers=headers)
    assert prediction.status_code == 200
    assert prediction.json()["forecast"] == 200.0
    listing = client.get("/transactions", headers=headers)
    assert len(listing.json()) == 3


def test_wrong_password_is_rejected(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    auth(client)
    response = client.post("/auth/login", json={"email": "maya@example.com", "password": "incorrect-password"})
    assert response.status_code == 401


def test_ping_is_public_and_returns_pong(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"message": "pong"}
