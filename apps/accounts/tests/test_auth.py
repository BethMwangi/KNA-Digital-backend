"""Auth flow tests — run with: pytest"""

import pytest
from django.core import mail
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.accounts.tokens import email_verification_token, encode_uid, password_reset_token

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


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


REGISTER_PAYLOAD = {
    "first_name": "Wanjiku",
    "last_name": "Kamau",
    "email": "wanjiku@example.com",
    "password": "Str0ng-Passw0rd!",
    "password_confirm": "Str0ng-Passw0rd!",
}


class TestRegistration:
    def test_register_creates_customer(self, client):
        # AUTH-REG-001 & AUTH-REG-015
        res = client.post(reverse("auth-register"), REGISTER_PAYLOAD)
        assert res.status_code == 201
        user = User.objects.get(email=REGISTER_PAYLOAD["email"])
        assert user.role == Role.CUSTOMER
        assert not user.email_verified
        # Verification email sent
        assert len(mail.outbox) == 1
        assert "Verify your Kenya News Agency Archive account" in mail.outbox[0].subject

    def test_register_rejects_duplicate_email(self, client):
        # AUTH-REG-002
        client.post(reverse("auth-register"), REGISTER_PAYLOAD)
        res = client.post(reverse("auth-register"), REGISTER_PAYLOAD)
        assert res.status_code in (400, 422)

    def test_register_rejects_soft_deleted_email(self, client, customer):
        # AUTH-REG-003
        customer.delete()  # soft delete
        payload = {**REGISTER_PAYLOAD, "email": customer.email}
        res = client.post(reverse("auth-register"), payload)
        assert res.status_code in (400, 422)

    def test_register_rejects_mismatched_passwords(self, client):
        payload = {**REGISTER_PAYLOAD, "password_confirm": "different"}
        res = client.post(reverse("auth-register"), payload)
        assert res.status_code in (400, 422)

    def test_register_rejects_common_password(self, client):
        # AUTH-REG-007
        payload = {
            **REGISTER_PAYLOAD,
            "email": "common@test.com",
            "password": "password123",
            "password_confirm": "password123",
        }
        res = client.post(reverse("auth-register"), payload)
        assert res.status_code in (400, 422)

    def test_register_rejects_user_attribute_similarity_password(self, client):
        # AUTH-REG-008
        payload = {
            **REGISTER_PAYLOAD,
            "email": "wanjiku.kamau@test.com",
            "first_name": "Wanjiku",
            "last_name": "Kamau",
            "password": "Wanjiku123",
            "password_confirm": "Wanjiku123",
        }
        res = client.post(reverse("auth-register"), payload)
        assert res.status_code in (400, 422)

    def test_register_ignores_privilege_escalation_role(self, client):
        # AUTH-REG-014
        payload = {**REGISTER_PAYLOAD, "email": "hacker@test.com", "role": "admin"}
        res = client.post(reverse("auth-register"), payload)
        assert res.status_code == 201
        user = User.objects.get(email="hacker@test.com")
        assert user.role == Role.CUSTOMER


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

    def test_login_unverified_account_allowed(self, client, customer):
        # AUTH-LOGIN-004
        assert not customer.email_verified
        res = client.post(
            reverse("auth-login"),
            {"email": customer.email, "password": "Str0ng-Passw0rd!"},
        )
        assert res.status_code == 200

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


class TestPasswordReset:
    def test_forgot_password_sends_email(self, client, customer):
        # AUTH-PWD-001
        res = client.post(reverse("auth-forgot-password"), {"email": customer.email})
        assert res.status_code == 200
        assert len(mail.outbox) == 1
        assert "Reset your password" in mail.outbox[0].subject

    def test_reset_password_confirm_strength_validation(self, client, customer):
        # AUTH-PWD-007
        uid = encode_uid(customer)
        token = password_reset_token.make_token(customer)
        res = client.post(
            reverse("auth-reset-password"),
            {"uid": uid, "token": token, "new_password": "short"},
        )
        assert res.status_code in (400, 422)


class TestEmailVerification:
    def test_verify_email_success(self, client, customer):
        # AUTH-EMAIL-001
        uid = encode_uid(customer)
        token = email_verification_token.make_token(customer)
        res = client.post(reverse("auth-verify-email"), {"uid": uid, "token": token})
        assert res.status_code == 200
        customer.refresh_from_db()
        assert customer.email_verified

    def test_verify_email_invalid_token(self, client, customer):
        # AUTH-EMAIL-002
        uid = encode_uid(customer)
        res = client.post(reverse("auth-verify-email"), {"uid": uid, "token": "invalidtoken"})
        assert res.status_code == 400

    def test_verify_email_reused_token(self, client, customer):
        # AUTH-EMAIL-003
        uid = encode_uid(customer)
        token = email_verification_token.make_token(customer)
        res1 = client.post(reverse("auth-verify-email"), {"uid": uid, "token": token})
        assert res1.status_code == 200
        # Reusing the token
        res2 = client.post(reverse("auth-verify-email"), {"uid": uid, "token": token})
        assert res2.status_code == 400


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
