"""Auth flow tests — run with: pytest"""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db

REGISTER_PAYLOAD = {
    "first_name": "Wanjiku",
    "last_name": "Kamau",
    "email": "wanjiku@example.com",
    "password": "Str0ng-Passw0rd!",
    "password_confirm": "Str0ng-Passw0rd!",
}


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def customer(db):
    return User.objects.create_user(
        email="customer@example.com",
        password="Str0ng-Passw0rd!",
        first_name="Test",
        last_name="Customer",
    )


class TestRegistration:
    def test_register_creates_customer(self, client):
        res = client.post(reverse("auth-register"), REGISTER_PAYLOAD)
        assert res.status_code == 201
        user = User.objects.get(email=REGISTER_PAYLOAD["email"])
        assert user.role == Role.CUSTOMER
        assert not user.email_verified

    def test_register_rejects_duplicate_email(self, client):
        client.post(reverse("auth-register"), REGISTER_PAYLOAD)
        res = client.post(reverse("auth-register"), REGISTER_PAYLOAD)
        assert res.status_code in (400, 422)

    def test_register_rejects_mismatched_passwords(self, client):
        payload = {**REGISTER_PAYLOAD, "password_confirm": "different"}
        res = client.post(reverse("auth-register"), payload)
        assert res.status_code in (400, 422)


class TestLogin:
    def test_login_returns_tokens_and_profile(self, client, customer):
        res = client.post(
            reverse("auth-login"),
            {"email": customer.email, "password": "Str0ng-Passw0rd!"},
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert "access" in data and "refresh" in data
        assert data["user"]["email"] == customer.email

    def test_login_rejects_bad_credentials(self, client, customer):
        res = client.post(reverse("auth-login"), {"email": customer.email, "password": "wrong"})
        assert res.status_code == 401

    def test_suspended_account_cannot_login(self, client, customer):
        customer.account_status = "suspended"
        customer.save()
        res = client.post(
            reverse("auth-login"),
            {"email": customer.email, "password": "Str0ng-Passw0rd!"},
        )
        assert res.status_code in (400, 401)


class TestProtectedEndpoints:
    def test_me_requires_auth(self, client):
        assert client.get(reverse("users-me")).status_code == 401

    def test_me_returns_profile(self, client, customer):
        client.force_authenticate(customer)
        res = client.get(reverse("users-me"))
        assert res.status_code == 200
        assert res.json()["data"]["email"] == customer.email

    def test_customer_cannot_access_admin_users(self, client, customer):
        client.force_authenticate(customer)
        res = client.get("/api/v1/admin/users/")
        assert res.status_code == 403


class TestRBAC:
    def test_admin_can_list_users(self, client, customer):
        admin = User.objects.create_user(
            email="admin@example.com",
            password="Str0ng-Passw0rd!",
            first_name="Admin",
            last_name="User",
            role=Role.ADMIN,
        )
        client.force_authenticate(admin)
        assert client.get("/api/v1/admin/users/").status_code == 200

    def test_admin_cannot_grant_super_admin(self, client, customer):
        admin = User.objects.create_user(
            email="admin2@example.com",
            password="Str0ng-Passw0rd!",
            first_name="Admin",
            last_name="Two",
            role=Role.ADMIN,
        )
        client.force_authenticate(admin)
        res = client.patch(
            f"/api/v1/admin/users/{customer.id}/",
            {"role": "super_admin"},
            format="json",
        )
        assert res.status_code in (400, 422)
