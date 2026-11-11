import importlib.util
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api(tmp_path, monkeypatch):
    """Запуск PetHome с отдельной временной базой."""
    database = tmp_path / "test_pethome.db"
    uploads = tmp_path / "uploads"

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.setenv("PETHOME_SECRET_KEY", "lab10-test-secret-not-for-production")
    monkeypatch.setenv("UPLOAD_DIR", str(uploads))

    path = Path(__file__).resolve().parents[1] / "backend" / "main.py"
    spec = importlib.util.spec_from_file_location("pethome_test_app", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module

    try:
        spec.loader.exec_module(module)
        with TestClient(module.app) as client:
            yield client, module
    finally:
        module.engine.dispose()
        sys.modules.pop(spec.name, None)


def register(client, email="student@example.com"):
    return client.post(
        "/auth/register",
        json={"email": email, "password": "TestPass123!"},
    )


def login(client, email="student@example.com", password="TestPass123!"):
    return client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )


def auth_headers(client):
    response = login(client)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_health(api):
    client, _ = api
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_animals_initially_empty(api):
    client, _ = api
    response = client.get("/animals")
    assert response.status_code == 200
    assert response.json() == []


def test_register_success(api):
    client, _ = api
    response = register(client)
    assert response.status_code == 201


def test_register_duplicate(api):
    client, _ = api
    assert register(client).status_code == 201
    assert register(client).status_code == 409


def test_register_invalid_email(api):
    client, _ = api
    response = register(client, "invalid-email")
    assert response.status_code == 422


def test_register_short_password(api):
    client, _ = api
    response = client.post(
        "/auth/register",
        json={"email": "student@example.com", "password": "123"},
    )
    assert response.status_code == 422


def test_login_success(api):
    client, _ = api
    register(client)
    response = login(client)
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_wrong_password(api):
    client, _ = api
    register(client)
    assert login(client, password="WrongPass123!").status_code == 401


def test_login_unknown_user(api):
    client, _ = api
    assert login(client).status_code == 401


def test_me_without_token(api):
    client, _ = api
    assert client.get("/auth/me").status_code == 401


def test_me_invalid_token(api):
    client, _ = api
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


def test_me_with_token(api):
    client, _ = api
    register(client)
    response = client.get("/auth/me", headers=auth_headers(client))
    assert response.status_code == 200
    assert response.json()["role"] == "user"


def test_application_requires_login(api):
    client, _ = api
    response = client.post(
        "/applications",
        json={
            "animal_id": 1,
            "full_name": "Test Student",
            "phone": "87001234567",
            "comment": "Test",
        },
    )
    assert response.status_code == 401


def test_application_unknown_animal(api):
    client, _ = api
    register(client)
    response = client.post(
        "/applications",
        headers=auth_headers(client),
        json={
            "animal_id": 999,
            "full_name": "Test Student",
            "phone": "87001234567",
            "comment": "Test",
        },
    )
    assert response.status_code == 404


def test_my_applications_empty(api):
    client, _ = api
    register(client)
    response = client.get(
        "/applications/me",
        headers=auth_headers(client),
    )
    assert response.status_code == 200
    assert response.json() == []


def test_admin_access_denied_to_user(api):
    client, _ = api
    register(client)
    response = client.get(
        "/admin/users",
        headers=auth_headers(client),
    )
    assert response.status_code == 403


def test_admin_requires_login(api):
    client, _ = api
    assert client.get("/admin/animals").status_code == 401


def test_available_animals_only(api):
    client, module = api

    with module.SessionLocal() as session:
        session.add_all([
            module.Animal(
                name="Barsik",
                type="cat",
                age="2",
                city="Astana",
                description="Friendly",
                image_url="",
                status="available",
            ),
            module.Animal(
                name="Rex",
                type="dog",
                age="3",
                city="Astana",
                description="Friendly",
                image_url="",
                status="archived",
            ),
        ])
        session.commit()

    response = client.get("/animals")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Barsik"
