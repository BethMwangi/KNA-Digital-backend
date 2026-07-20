from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.assets.models import AssetVariant, DigitalAsset
from apps.commerce.models import License, Order, ShoppingCart
from apps.downloads.models import Download

User = get_user_model()


class CommerceAndDownloadsFlowTests(APITestCase):
    def setUp(self):
        # 1. Create a user
        self.user = User.objects.create_user(
            email="buyer@test.com", password="Pass1234!", first_name="Test", last_name="Buyer"
        )
        # Verify email so user is active (custom auth rules might require it)
        self.user.email_verified = True
        self.user.save()

        # 2. Create an asset with price
        self.asset = DigitalAsset.objects.create(
            title="Test Asset 1",
            asset_number="TEST/001",
            price=Decimal("1500.00"),
            status=DigitalAsset.Status.PUBLISHED,
        )

        # 3. Create a variant for the asset so download works
        self.variant = AssetVariant.objects.create(
            asset=self.asset,
            variant_name="High Resolution",
            storage_path="test/file.jpg",
            mime_type="image/jpeg",
            file_size=1024,
        )

        # 4. Create a license
        self.license = License.objects.create(
            name="Commercial", slug="commercial", allows_commercial=True
        )

        # 5. Authenticate user
        self.client.force_authenticate(user=self.user)

    def test_full_checkout_and_download_flow(self):
        """
        Tests the entire flow:
        - Add item to cart
        - Checkout (creates a PENDING order, empties cart) — no
          entitlement yet, an unpaid order buys nothing
        - Simulate a successful mock payment (apps.payments) — THIS is
          what grants the Download record, matching a real gateway
        - User can request download link
        """

        # --- STEP 1: ADD TO CART ---
        add_url = reverse("cart")
        response = self.client.post(
            add_url, {"asset_id": str(self.asset.id), "license_id": str(self.license.id)}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["item_count"], 1)

        # Ensure shopping cart exists
        cart = ShoppingCart.objects.get(user=self.user)
        self.assertEqual(cart.items.count(), 1)

        # --- STEP 2: CHECKOUT ---
        checkout_url = reverse("checkout")
        response = self.client.post(checkout_url, {"notes": "Test checkout"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order_id = response.data["data"]["id"]

        # Ensure order is created, PENDING (not yet paid)
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Order.objects.get(id=order_id).status, Order.Status.PENDING)

        # Ensure cart is emptied
        self.assertEqual(cart.items.count(), 0)

        # An unpaid order grants nothing yet.
        self.assertEqual(Download.objects.filter(user=self.user).count(), 0)

        # --- STEP 3: PAY (mock gateway simulation) ---
        response = self.client.post(
            reverse("payment-initiate"), {"order_id": order_id, "provider": "mock"}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payment_id = response.data["data"]["id"]

        response = self.client.post(
            reverse("payment-simulate", kwargs={"pk": payment_id}), {"outcome": "success"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["status"], "completed")

        # --- STEP 4: VERIFY PAYMENT GRANTED THE DOWNLOAD ---
        self.assertEqual(Order.objects.get(id=order_id).status, Order.Status.PAID)
        downloads = Download.objects.filter(user=self.user)
        self.assertEqual(downloads.count(), 1)
        download = downloads.first()
        self.assertEqual(download.asset, self.asset)
        self.assertEqual(download.license, self.license)
        self.assertEqual(download.download_count, 0)
        self.assertEqual(download.max_downloads, 5)

        # --- STEP 5: GET DOWNLOAD LINK ---
        # Get the list of downloads
        list_url = reverse("download-list")
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["results"]), 1)

        # Request a signed link
        link_url = reverse("download-link", kwargs={"pk": download.id})
        response = self.client.get(link_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data["data"]
        self.assertIn("download_url", data)
        self.assertIn("file_name", data)
        self.assertEqual(data["downloads_remaining"], 4)  # one download consumed

        # Ensure the DB was updated
        download.refresh_from_db()
        self.assertEqual(download.download_count, 1)
