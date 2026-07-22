from tests.conftest import AuthTestContext
from tests.test_treatments import admin_headers


def test_user_management_update_password_archive_and_reuse_username(
    auth_context: AuthTestContext,
) -> None:
    client = auth_context.client
    admin = admin_headers(auth_context)
    roles = client.get("/v1/roles", headers=admin)
    assert roles.status_code == 200
    by_name = {role["name"]: role for role in roles.json()}

    created = client.post(
        "/v1/users",
        headers=admin,
        json={
            "username": "ancien-login",
            "password": "Temporary!Password42",
            "role_ids": [by_name["Traitant"]["id"]],
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]

    updated = client.patch(
        f"/v1/users/{user_id}",
        headers=admin,
        json={
            "username": "login-reutilisable",
            "role_ids": [by_name["Audit"]["id"]],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["username"] == "login-reutilisable"
    assert [role["name"] for role in updated.json()["roles"]] == ["Audit"]

    password = client.patch(
        f"/v1/users/{user_id}/password",
        headers=admin,
        json={"password": "Replacement!Password42"},
    )
    assert password.status_code == 200
    assert (
        client.post(
            "/v1/auth/login",
            json={"username": "login-reutilisable", "password": "Temporary!Password42"},
        ).status_code
        == 401
    )
    replacement_login = client.post(
        "/v1/auth/login",
        json={"username": "login-reutilisable", "password": "Replacement!Password42"},
    )
    assert replacement_login.status_code == 200
    assert replacement_login.json()["user"]["must_change_password"] is True

    archived = client.delete(f"/v1/users/{user_id}", headers=admin)
    assert archived.status_code == 204
    assert (
        client.post(
            "/v1/auth/login",
            json={"username": "login-reutilisable", "password": "Replacement!Password42"},
        ).status_code
        == 401
    )
    assert all(user["id"] != user_id for user in client.get("/v1/users", headers=admin).json())

    reused = client.post(
        "/v1/users",
        headers=admin,
        json={
            "username": "login-reutilisable",
            "password": "Another!Password42",
            "role_ids": [by_name["Traitant"]["id"]],
        },
    )
    assert reused.status_code == 201
    assert reused.json()["id"] != user_id


def test_administrator_can_be_assigned_a_vulnerability(auth_context: AuthTestContext) -> None:
    client = auth_context.client
    admin = admin_headers(auth_context)
    admin_user = next(
        user
        for user in client.get("/v1/users", headers=admin).json()
        if user["username"] == "admin"
    )

    assignees = client.get("/v1/treatment-assignees", headers=admin)
    assert assignees.status_code == 200
    assert admin_user["id"] in {user["id"] for user in assignees.json()}

    platform = client.post(
        "/v1/platforms",
        headers=admin,
        json={"name": "Plateforme administrateur", "target_type": "none"},
    )
    service = client.post(
        f"/v1/platforms/{platform.json()['id']}/services/bulk",
        headers=admin,
        json={"items": [{"name": "Nginx", "version": "1.0", "category_id": None}]},
    )
    service_id = service.json()[0]["id"]
    vulnerability = client.post(
        f"/v1/services/{service_id}/vulnerabilities/manual",
        headers=admin,
        json={"identifier": "CVE-TEST-ADMIN", "description": "Test administrateur"},
    )
    assert vulnerability.status_code == 201
    assigned = client.post(
        "/v1/treatments",
        headers=admin,
        json={
            "service_id": service_id,
            "assigned_to_id": admin_user["id"],
        },
    )
    assert assigned.status_code == 201
    assert assigned.json()["assignee"]["id"] == admin_user["id"]
