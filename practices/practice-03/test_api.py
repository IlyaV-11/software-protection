"""Проверки граничных случаев и отказов HTTP-интеграций."""
from datetime import datetime, timedelta, timezone
import secrets

from fastapi.testclient import TestClient
import httpx
import jwt
import pytest

import main


@pytest.fixture
def client():
    main.users_db.clear()
    main.accounts_db.clear()
    main.next_user_id = 1
    with TestClient(main.app) as api:
        async def response(request):
            if request.method == "POST":
                return httpx.Response(200, json={"status": "sent"})
            return httpx.Response(200, json=[{"userId": 1, "id": 1, "title": "Post"}])
        original = main.app.state.http
        mock = httpx.AsyncClient(transport=httpx.MockTransport(response))
        main.app.state.http = mock
        yield api
        main.app.state.http = original


def authorized(client):
    credentials = {"email": "student@example.com", "password": secrets.token_urlsafe(16)}
    assert client.post("/signup", json=credentials).status_code == 201
    login = client.post("/login", json=credentials)
    assert login.status_code == 200
    return {"Authorization": "Bearer " + login.json()["access_token"]}


def create(client, name="John Doe", email="john@example.com", age=25):
    return client.post("/users/", json={"name": name, "email": email, "age": age})


def test_crud_and_double_delete(client):
    headers = authorized(client)
    response = create(client)
    assert response.status_code == 201
    assert response.json()["id"] == 1
    assert client.get("/users/1").json()["name"] == "John Doe"
    assert len(client.get("/users/").json()) == 1
    updated = {"name": "John Updated", "email": "john.updated@example.com", "age": 30}
    assert client.put("/users/1", json=updated, headers=headers).json()["age"] == 30
    assert client.delete("/users/1", headers=headers).status_code == 200
    assert client.delete("/users/1", headers=headers).status_code == 404


@pytest.mark.parametrize("method", ["put", "delete"])
def test_write_requires_token(client, method):
    create(client)
    kwargs = {"json": {"name": "John", "email": "john@example.com", "age": 30}} if method == "put" else {}
    assert getattr(client, method)("/users/1", **kwargs).status_code == 401
    assert getattr(client, method)("/users/1", headers={"Authorization": "Bearer broken"}, **kwargs).status_code == 401


def test_expired_jwt(client):
    headers = authorized(client)
    create(client)
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": "student@example.com", "iat": now - timedelta(hours=1),
                        "exp": now - timedelta(minutes=1)}, main.SECRET_KEY, algorithm="HS256")
    assert client.delete("/users/1", headers={"Authorization": "Bearer " + token}).status_code == 401
    assert client.get("/users/1").status_code == 200


def test_filter_strict_boundary_and_pagination(client):
    create(client, age=25)
    create(client, "Older", "older@example.com", 30)
    create(client, "Unknown", "unknown@example.com", None)
    result = client.get("/users/?min_age=25").json()
    assert [x["age"] for x in result] == [30]
    assert client.get("/users/?min_age=0&skip=1&limit=1").json()[0]["age"] == 30


def test_validation_and_duplicate_email_on_update(client):
    headers = authorized(client)
    create(client)
    create(client, "Other", "other@example.com", 30)
    assert create(client).status_code == 400
    assert create(client, email="invalid-email").status_code == 422
    assert create(client, email="badage@example.com", age=-1).status_code == 422
    assert client.get("/users/?limit=-1").status_code == 422
    data = {"name": "Other", "email": "john@example.com", "age": 30}
    assert client.put("/users/2", json=data, headers=headers).status_code == 400


@pytest.mark.parametrize("failure", ["connection", "http500"])
def test_notification_failure_does_not_lose_user(client, failure):
    async def fail(request):
        if failure == "connection":
            raise httpx.ConnectError("Notification service is down", request=request)
        return httpx.Response(500, json={"detail": "Unavailable"})
    main.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(fail))
    assert create(client).status_code == 201
    assert client.get("/users/1").status_code == 200


@pytest.mark.parametrize("failure,expected", [("http503", 502), ("timeout", 504), ("invalid", 502)])
def test_external_posts_failures(client, failure, expected):
    create(client)
    async def fail(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("Timed out", request=request)
        if failure == "invalid":
            return httpx.Response(200, text="not JSON")
        return httpx.Response(503, json={"detail": "Unavailable"})
    main.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(fail))
    assert client.get("/users/1/posts").status_code == expected


def test_external_posts_success_and_missing_user(client):
    create(client)
    assert client.get("/users/1/posts").json()[0]["userId"] == 1
    assert client.get("/users/999/posts").status_code == 404
