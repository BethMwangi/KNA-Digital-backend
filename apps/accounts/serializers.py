"""Accounts serializers — validation lives here, views stay thin."""

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import AccountStatus, Role, User
from .tokens import decode_uid, password_reset_token


class UserSerializer(serializers.ModelSerializer):
    """
    Public representation of a user (never exposes
    password_hash).
    """

    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone_number",
            "role",
            "account_status",
            "email_verified",
            "last_login",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "email",
            "role",
            "account_status",
            "email_verified",
            "last_login",
            "created_at",
        ]


class RegisterSerializer(serializers.ModelSerializer):
    """
    Public self-registration — always creates a CUSTOMER
    (SDD §17.3). Staff accounts are created only by admins
    via AdminUserSerializer.
    """

    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "password",
            "password_confirm",
        ]

    def validate_email(self, value: str) -> str:
        if User.all_objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        user_temp = User(
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
            email=attrs.get("email", ""),
        )
        validate_password(attrs["password"], user=user_temp)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(role=Role.CUSTOMER, password=password, **validated_data)


class LoginSerializer(TokenObtainPairSerializer):
    """
    JWT login. Extends simplejwt to:
    - embed role claims in the access token,
    - block suspended accounts,
    - return the user profile alongside tokens
      (SDD §16.5).
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["email"] = user.email
        token["full_name"] = user.full_name
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        if self.user.is_suspended:
            raise serializers.ValidationError("This account has been suspended.")
        data["user"] = UserSerializer(self.user).data
        return data


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate(self, attrs):
        user = decode_uid(attrs["uid"])
        if user is None or not password_reset_token.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": "Invalid or expired reset link."})
        validate_password(attrs["new_password"], user=user)
        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user


class EmailVerifySerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()


class AdminUserSerializer(serializers.ModelSerializer):
    """
    Used by /admin/users endpoints — admins create staff
    (Content Editors who handle images, other Admins) and
    can suspend/reactivate accounts.
    """

    password = serializers.CharField(
        write_only=True, required=False, validators=[validate_password]
    )

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "role",
            "account_status",
            "email_verified",
            "password",
            "last_login",
            "created_at",
        ]
        read_only_fields = ["id", "last_login", "created_at"]

    def validate_role(self, value):
        requester = self.context["request"].user
        # Only a Super Admin can grant admin/super-admin
        # roles (SDD §17.4).
        if value in {Role.ADMIN, Role.SUPER_ADMIN} and not requester.is_super_admin:
            raise serializers.ValidationError("Only a Super Administrator can assign this role.")
        return value

    def validate_account_status(self, value):
        return value if value in AccountStatus.values else AccountStatus.ACTIVE

    def create(self, validated_data):
        from django.utils.crypto import get_random_string

        password = validated_data.pop("password", None)
        user = User.objects.create_user(
            password=password or get_random_string(32), **validated_data
        )
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password", "updated_at"])
        return user
