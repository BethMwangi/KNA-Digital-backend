from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.assets.models import DigitalAsset
from apps.commerce.models import License, Order
from apps.payments.models import Payment

from .models import Download
from .urithi import sync_download_link

User = get_user_model()


class UrithiDownloadLinkTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="buyer@test.com",
            password="Pass1234!",
            first_name="Test",
            last_name="Buyer",
            email_verified=True,
        )
        self.asset = DigitalAsset.objects.create(
            title="Test Asset",
            asset_number="8",
            price=Decimal("1500.00"),
            status=DigitalAsset.Status.PUBLISHED,
        )
        self.license = License.objects.create(name="Commercial", slug="commercial")
        self.order = Order.objects.create(
            order_number="KNA-TEST",
            user=self.user,
            status=Order.Status.PAID,
            subtotal=Decimal("1500.00"),
            total=Decimal("1500.00"),
            currency="KES",
        )
        self.payment = Payment.objects.create(
            order=self.order,
            provider=Payment.Provider.PESAFLOW,
            status=Payment.Status.COMPLETED,
            amount=Decimal("1500.00"),
            currency="KES",
            transaction_id="TXN-TEST",
            provider_response={
                "payment_channel": "MPESA",
                "payment_reference": "PESA-REF",
                "payment_status": "SUCCESS",
            },
        )
        self.download = Download.objects.create(
            user=self.user,
            order=self.order,
            asset=self.asset,
            license=self.license,
        )
        self.client.force_authenticate(self.user)

    @patch("apps.downloads.urithi.requests.post")
    def test_sync_download_link_stores_urithi_response(self, post):
        post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "status": "valid",
                "download_link": "https://urithi.kenyanews.go.ke/dl/8/test-token",
                "max_downloads": 5,
                "download_counts": 0,
            },
        )

        sync_download_link(self.download, self.payment)

        post.assert_called_once()
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["image_id"], "8")
        self.assertEqual(payload["payment_channel"], "MPESA")
        self.assertEqual(payload["payment_reference"], "PESA-REF")
        self.assertEqual(payload["client_invoice_ref"], "TXN-TEST")

        self.download.refresh_from_db()
        self.assertEqual(self.download.external_download_status, "valid")
        self.assertEqual(
            self.download.external_download_link,
            "https://urithi.kenyanews.go.ke/dl/8/test-token",
        )
        self.assertEqual(self.download.external_download_counts, 0)

    def test_download_link_endpoint_returns_stored_urithi_link(self):
        self.download.external_download_status = "valid"
        self.download.external_download_link = "https://urithi.kenyanews.go.ke/dl/8/test-token"
        self.download.save(
            update_fields=["external_download_status", "external_download_link", "updated_at"]
        )

        response = self.client.get(reverse("download-link", kwargs={"pk": self.download.id}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(data["url"], "https://urithi.kenyanews.go.ke/dl/8/test-token")
        self.assertEqual(
            data["download_url"],
            "https://urithi.kenyanews.go.ke/dl/8/test-token",
        )
