import json
import os
import tempfile
import uuid
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import Mock, patch
from urllib.parse import unquote

import requests
from PIL import Image

from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .admin import OrderAdmin
from .models import (
    Category,
    Customer,
    Order,
    OrderItem,
    PaymentTransaction,
    PasswordResetCode,
    Product,
    Review,
    SiteSettings,
    SocialMediaLink,
)


User = get_user_model()


class ShopTestCase(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Accessories")
        self.product = Product.objects.create(
            category=self.category,
            name="Leather Bag",
            description="Hand-finished leather bag",
            price=Decimal("1250.00"),
            stock=10,
        )
        self.site_settings = SiteSettings.objects.create(
            whatsapp_number="+234 801-234-5678",
            whatsapp_enabled=True,
            telegram_username="@annelsa_store",
            telegram_enabled=True,
            payment_method="contact",
            paystack_test_mode=True,
            currency="NGN",
        )
        self.checkout_key = uuid.uuid4().hex
        self.order_payload = {
            "customer_name": "Test Buyer",
            "phone": "+2348012345678",
            "email": "buyer@example.com",
            "location": "Lagos",
            "address": "10 Test Street",
            "cart_data": json.dumps(
                [{"id": self.product.id, "quantity": 2, "price": "0.01"}]
            ),
            "checkout_key": self.checkout_key,
            "contact_method": "whatsapp",
        }


class CatalogTests(ShopTestCase):
    def test_home_displays_product_details_and_real_category_id(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leather Bag")
        self.assertContains(response, "Hand-finished leather bag")
        self.assertContains(
            response,
            f"data-product-category=\"{self.category.id}\"",
        )
        self.assertContains(response, "10 in stock")

    def test_home_offers_both_configured_contact_channels(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'value="whatsapp">WhatsApp</option>')
        self.assertContains(response, 'value="telegram">Telegram</option>')

    def test_footer_shows_active_social_media_links(self):
        social_link = SocialMediaLink.objects.create(
            platform="instagram",
            name="Instagram",
            url="https://instagram.com/example",
            is_active=True,
        )

        response = self.client.get(reverse("home"))

        self.assertContains(response, social_link.url)
        self.assertContains(response, social_link.name)

    def test_footer_shows_only_configured_site_social_links(self):
        self.site_settings.instagram_url = "https://instagram.com/example"
        self.site_settings.tiktok_url = "https://tiktok.com/@example"
        self.site_settings.twitter_url = "https://x.com/example"
        self.site_settings.save()

        response = self.client.get(reverse("home"))

        for url in (
            self.site_settings.instagram_url,
            self.site_settings.tiktok_url,
            self.site_settings.twitter_url,
        ):
            self.assertContains(response, f'href="{url}"')
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener"')
        self.assertNotContains(response, "Facebook")

    def test_footer_shows_configured_developer_links(self):
        self.site_settings.developer_name = "Example Developer"
        self.site_settings.developer_url = "https://example.com"
        self.site_settings.developer_email = "developer@example.com"
        self.site_settings.developer_whatsapp = "+234 801 234 5678"
        self.site_settings.instagram_url = "https://instagram.com/example"
        self.site_settings.save()

        response = self.client.get(reverse("home"))
        page = response.content.decode()

        self.assertContains(response, "Built by")
        self.assertContains(response, "Example Developer")
        self.assertContains(response, "mailto:developer@example.com")
        self.assertContains(
            response,
            "https://wa.me/2348012345678?text=Hello%2C%20I%20saw%20the%20website%20you%20built",
        )
        self.assertLess(
            page.index(self.site_settings.instagram_url),
            page.index('class="copyright"'),
        )
        self.assertLess(
            page.index('class="copyright"'),
            page.index('class="developer-credit"'),
        )

    def test_developer_whatsapp_accepts_a_full_wa_me_url(self):
        self.site_settings.developer_name = "Example Developer"
        self.site_settings.developer_whatsapp = (
            "https://wa.me/2348012345678?text=Call%201234"
        )
        self.site_settings.save()

        response = self.client.get(reverse("home"))

        self.assertContains(
            response,
            "https://wa.me/2348012345678?text=Hello%2C%20I%20saw%20the%20website%20you%20built",
        )

    def test_search_empty_state_is_available_for_empty_catalog(self):
        Product.objects.all().delete()

        response = self.client.get(reverse("home"))

        self.assertContains(response, 'id="productSearchEmptyState"')
        self.assertContains(
            response,
            "No products found matching your search. Please try another keyword!",
        )

    def test_empty_catalog_message_requires_a_search_query(self):
        Product.objects.all().delete()
        empty_block_marker = (
            '<div class="glass-card product-card empty-products">'
        )

        homepage_response = self.client.get(reverse("home"))
        homepage_empty_block = (
            homepage_response.content.decode()
            .split(empty_block_marker, 1)[1]
            .split("</div>", 1)[0]
        )
        self.assertEqual(homepage_response.context["query"], "")
        self.assertNotIn(
            "No products found matching your search.",
            homepage_empty_block,
        )

        search_response = self.client.get(reverse("home"), {"q": "missing"})
        search_empty_block = (
            search_response.content.decode()
            .split(empty_block_marker, 1)[1]
            .split("</div>", 1)[0]
        )
        self.assertEqual(search_response.context["query"], "missing")
        self.assertIn(
            "No products found matching your search. Please try another keyword!",
            search_empty_block,
        )

    def test_admin_registers_product_category_orders_and_reviews(self):
        from django.contrib import admin

        for model in (Product, Category, Order, Review):
            self.assertIn(model, admin.site._registry)
        settings_admin = admin.site._registry[SiteSettings]
        self.assertIn(
            "payment_method",
            [
                field
                for _, options in settings_admin.fieldsets
                for field in options["fields"]
            ],
        )
        self.assertIn(
            "logo",
            [
                field
                for _, options in settings_admin.fieldsets
                for field in options["fields"]
            ],
        )
        settings_fields = [
            field
            for _, options in settings_admin.fieldsets
            for field in options["fields"]
        ]
        for field in (
            "instagram_url",
            "tiktok_url",
            "facebook_url",
            "twitter_url",
        ):
            self.assertIn(field, settings_fields)
        social_admin = admin.site._registry[SocialMediaLink]
        self.assertIn("footer", social_admin.fieldsets[0][0].lower())

    def test_logo_replaces_header_business_name(self):
        image_buffer = BytesIO()
        Image.new("RGB", (4, 4), "white").save(image_buffer, format="PNG")
        self.site_settings.logo = SimpleUploadedFile(
            "brand.png",
            image_buffer.getvalue(),
            content_type="image/png",
        )
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.site_settings.save()
                response = self.client.get(reverse("home"))

        self.assertContains(response, self.site_settings.logo.url)
        header = response.content.decode().split("<header>", 1)[1].split(
            "</header>",
            1,
        )[0]
        heading = header.split("<h1", 1)[1].split("</h1>", 1)[0]
        self.assertIn('class="brand-logo"', heading)
        self.assertNotIn(">ANNELSA LUXURY<", heading)

    def test_product_and_logo_uploads_are_resized_and_compressed(self):
        image_buffer = BytesIO()
        Image.effect_noise((2400, 1800), 100).convert("RGB").save(
            image_buffer,
            format="PNG",
        )
        upload = image_buffer.getvalue()

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.site_settings.logo = SimpleUploadedFile(
                    "large-logo.png",
                    upload,
                    content_type="image/png",
                )
                self.site_settings.save()
                product_image = self.product.images.create(
                    image=SimpleUploadedFile(
                        "large-product.png",
                        upload,
                        content_type="image/png",
                    )
                )

                for saved_image in (
                    self.site_settings.logo,
                    product_image.image,
                ):
                    with Image.open(saved_image) as compressed:
                        self.assertLessEqual(max(compressed.size), 1600)
                    self.assertLessEqual(saved_image.size, 300 * 1024)


class OrderPickupVerificationTests(ShopTestCase):
    def test_paid_order_transition_generates_unique_pickup_code(self):
        order = Order.objects.create(
            customer=Customer.objects.create(name="Pickup Customer"),
            total=Decimal("100.00"),
        )
        self.assertIsNone(order.verification_code)
        self.assertFalse(order.is_delivered)

        order.status = "confirmed"
        order.save(update_fields=["status", "updated_at"])
        order.refresh_from_db()

        self.assertRegex(order.verification_code, r"^PICK-\d{6}$")
        self.assertEqual(
            Order.objects.filter(
                verification_code=order.verification_code,
            ).count(),
            1,
        )

    def test_already_paid_order_without_status_transition_gets_no_new_code(self):
        order = Order.objects.create(
            customer=Customer.objects.create(name="Pickup Customer"),
            total=Decimal("100.00"),
            status="confirmed",
        )
        code = order.verification_code

        order.additional_note = "Customer requested gift wrapping."
        order.save(update_fields=["additional_note"])
        order.refresh_from_db()

        self.assertEqual(order.verification_code, code)
        self.assertRegex(order.verification_code, r"^PICK-\d{6}$")


class CheckoutTests(ShopTestCase):
    def test_whatsapp_checkout_creates_order_and_decrements_stock(self):
        response = self.client.post(
            reverse("create_order"),
            self.order_payload,
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "redirect")
        self.assertIn("wa.me/2348012345678", data["redirect_url"])
        self.assertIn("Order%20ID", data["redirect_url"])
        self.assertIn("Test%20Buyer", data["redirect_url"])
        message = unquote(data["redirect_url"].split("?text=", 1)[1])
        self.assertIn("Phone: +2348012345678", message)
        self.assertIn("Address: 10 Test Street", message)
        self.assertIn("Leather Bag x 2 @ ₦1,250.00 each", message)
        self.assertIn("TOTAL: ₦2,500.00", message)

        order = Order.objects.get(pk=data["order_id"])
        item = order.items.get()
        self.product.refresh_from_db()
        self.assertEqual(order.total, Decimal("2500.00"))
        self.assertEqual(item.price, Decimal("1250.00"))
        self.assertEqual(item.quantity, 2)
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(order.customer.email, "buyer@example.com")

    def test_telegram_checkout_redirects_to_saved_username_with_receipt(self):
        self.order_payload["contact_method"] = "telegram"

        response = self.client.post(
            reverse("create_order"),
            self.order_payload,
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "redirect")
        self.assertTrue(
            data["redirect_url"].startswith("https://t.me/annelsa_store?")
        )
        self.assertIn("Test%20Buyer", data["redirect_url"])
        self.assertIn("Leather%20Bag", data["redirect_url"])
        self.assertIn("TOTAL: ₦2,500.00", unquote(data["redirect_url"]))

    def test_checkout_rejects_disabled_contact_channel(self):
        self.site_settings.telegram_enabled = False
        self.site_settings.save(update_fields=["telegram_enabled"])
        self.order_payload["contact_method"] = "telegram"

        response = self.client.post(
            reverse("create_order"),
            self.order_payload,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_duplicate_cart_lines_are_aggregated_before_stock_check(self):
        self.product.stock = 4
        self.product.save(update_fields=["stock"])
        self.order_payload["cart_data"] = json.dumps(
            [
                {"id": self.product.id, "quantity": 3},
                {"id": self.product.id, "quantity": 2},
            ]
        )

        response = self.client.post(
            reverse("create_order"),
            self.order_payload,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Only 4 unit(s)", response.json()["message"])
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)

    def test_repeated_checkout_key_does_not_create_second_order(self):
        first = self.client.post(
            reverse("create_order"),
            self.order_payload,
        )
        second = self.client.post(
            reverse("create_order"),
            self.order_payload,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Order.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)

    def test_checkout_rejects_invalid_cart_without_creating_order(self):
        self.order_payload["cart_data"] = "not-json"

        response = self.client.post(
            reverse("create_order"),
            self.order_payload,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_missing_messaging_configuration_does_not_reserve_stock(self):
        self.site_settings.whatsapp_enabled = False
        self.site_settings.whatsapp_number = ""
        self.site_settings.save()

        response = self.client.post(
            reverse("create_order"),
            self.order_payload,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_checkout_requires_post(self):
        response = self.client.get(reverse("create_order"))
        self.assertEqual(response.status_code, 405)

    def test_checkout_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(
            reverse("create_order"),
            self.order_payload,
        )
        self.assertEqual(response.status_code, 403)

    @patch.dict(os.environ, {"PAYSTACK_TEST_SECRET_KEY": "sk_test_example"})
    @patch("shop.views.requests.post")
    def test_paystack_initialization_uses_mode_secret_and_server_total(
        self,
        post_request,
    ):
        self.site_settings.payment_method = "paystack"
        self.site_settings.save()
        second_product = Product.objects.create(
            category=self.category,
            name="Canvas Tote",
            description="A durable canvas tote",
            price=Decimal("300.00"),
            stock=5,
        )
        self.order_payload["cart_data"] = json.dumps(
            [
                {"id": self.product.id, "quantity": 2, "price": "0.01"},
                {"id": second_product.id, "quantity": 1, "price": "0.01"},
            ]
        )
        gateway_response = Mock()
        gateway_response.json.return_value = {
            "status": True,
            "data": {"authorization_url": "https://checkout.example/authorize"},
        }
        post_request.return_value = gateway_response

        response = self.client.post(
            reverse("create_order"),
            self.order_payload,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "paystack")
        post_request.assert_called_once()
        self.assertEqual(
            post_request.call_args.kwargs["headers"]["Authorization"],
            "Bearer sk_test_example",
        )
        self.assertEqual(
            post_request.call_args.kwargs["json"]["amount"],
            280000,
        )
        self.assertEqual(
            post_request.call_args.kwargs["json"]["metadata"]["custom_fields"],
            [
                {
                    "display_name": "Item 1",
                    "variable_name": "item_1",
                    "value": "Leather Bag x 2",
                },
                {
                    "display_name": "Item 2",
                    "variable_name": "item_2",
                    "value": "Canvas Tote x 1",
                },
            ],
        )
        payment = PaymentTransaction.objects.get()
        self.assertEqual(payment.amount, Decimal("2800.00"))
        self.assertTrue(payment.paystack_test_mode)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)

    @patch.dict(os.environ, {}, clear=True)
    def test_paystack_missing_secret_does_not_create_order(self):
        self.site_settings.payment_method = "paystack"
        self.site_settings.save()

        response = self.client.post(
            reverse("create_order"),
            self.order_payload,
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    @patch.dict(os.environ, {"PAYSTACK_TEST_SECRET_KEY": "sk_test_example"})
    @patch("shop.views.requests.post")
    def test_paystack_initialization_failure_cancels_order_and_restores_stock(
        self,
        post_request,
    ):
        self.site_settings.payment_method = "paystack"
        self.site_settings.save()
        post_request.side_effect = requests.Timeout("gateway timeout")

        response = self.client.post(
            reverse("create_order"),
            self.order_payload,
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(PaymentTransaction.objects.get().status, "failed")
        self.assertEqual(Order.objects.get().status, "cancelled")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    @patch.dict(os.environ, {"PAYSTACK_TEST_SECRET_KEY": "sk_test_example"})
    @patch("shop.views.requests.get")
    def test_payment_callback_verifies_and_is_idempotent(self, get_request):
        order, payment = self.create_pending_paystack_order()
        get_request.return_value = self.gateway_verification(
            payment,
            status="success",
        )

        first = self.client.get(
            reverse("paystack_callback"),
            {"reference": payment.reference},
        )
        second = self.client.get(
            reverse("paystack_callback"),
            {"reference": payment.reference},
        )

        self.assertEqual(first.status_code, 200)
        self.assertContains(first, f"Order #{order.id} is confirmed.")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(get_request.call_count, 1)
        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, "success")
        self.assertEqual(order.status, "confirmed")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)

    @patch.dict(os.environ, {"PAYSTACK_TEST_SECRET_KEY": "sk_test_example"})
    @patch("shop.views.requests.get")
    def test_payment_mismatch_fails_and_restores_reserved_stock(self, get_request):
        order, payment = self.create_pending_paystack_order()
        get_request.return_value = self.gateway_verification(
            payment,
            status="success",
            amount=1,
        )

        response = self.client.get(
            reverse("paystack_callback"),
            {"reference": payment.reference},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payment could not be verified")
        payment.refresh_from_db()
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(payment.status, "failed")
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(self.product.stock, 10)

    @patch.dict(
        os.environ,
        {
            "PAYSTACK_TEST_SECRET_KEY": "sk_test_example",
            "PAYSTACK_LIVE_SECRET_KEY": "sk_live_example",
        },
    )
    @patch("shop.views.requests.get")
    def test_callback_uses_the_transaction_initialization_mode(
        self,
        get_request,
    ):
        order, payment = self.create_pending_paystack_order()
        self.site_settings.paystack_test_mode = False
        self.site_settings.save(update_fields=["paystack_test_mode"])
        get_request.return_value = self.gateway_verification(
            payment,
            status="success",
        )

        response = self.client.get(
            reverse("paystack_callback"),
            {"reference": payment.reference},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            get_request.call_args.kwargs["headers"]["Authorization"],
            "Bearer sk_test_example",
        )
        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, "success")
        self.assertEqual(order.status, "confirmed")

    def create_pending_paystack_order(self):
        order = Order.objects.create(
            customer=Customer.objects.create(
                name="Test Buyer",
                phone="2348012345678",
                email="buyer@example.com",
                address="10 Test Street",
                city="Lagos",
            ),
            total=Decimal("2500.00"),
            status="pending",
        )
        self.product.stock = 8
        self.product.save(update_fields=["stock"])
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            price=Decimal("1250.00"),
            quantity=2,
        )
        payment = PaymentTransaction.objects.create(
            order=order,
            reference="ANL-TEST-REFERENCE",
            amount=Decimal("2500.00"),
            currency="NGN",
            status="pending",
        )
        self.site_settings.payment_method = "paystack"
        self.site_settings.save()
        return order, payment

    @staticmethod
    def gateway_verification(payment, status, amount=None):
        response = Mock()
        response.json.return_value = {
            "status": True,
            "data": {
                "status": status,
                "reference": payment.reference,
                "amount": amount if amount is not None else 250000,
                "currency": "NGN",
            },
        }
        return response


class ReviewTests(ShopTestCase):
    def test_public_review_is_saved_for_admin_moderation(self):
        response = self.client.post(
            reverse("submit_review"),
            {
                "product_id": self.product.id,
                "name": "Reviewer",
                "rating": "5",
                "comment": "A lovely product.",
            },
        )

        self.assertEqual(response.status_code, 200)
        review = Review.objects.get()
        self.assertFalse(review.is_approved)
        self.assertFalse(review.is_featured)
        self.assertEqual(review.product, self.product)

    def test_review_rejects_invalid_rating(self):
        response = self.client.post(
            reverse("submit_review"),
            {
                "product_id": self.product.id,
                "name": "Reviewer",
                "rating": "6",
                "comment": "A lovely product.",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Review.objects.count(), 0)


class AccountTests(ShopTestCase):
    def test_login_form_renders_without_social_sign_in_options(self):
        response = self.client.get(reverse("account_login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="submit">Sign In</button>')
        self.assertContains(response, reverse("account_password_reset"))
        self.assertNotContains(response, "Continue with Google")
        self.assertNotContains(response, "Continue with Facebook")

    def test_account_pages_render_without_social_sign_in_options(self):
        login_response = self.client.get(reverse("account_login"))
        self.assertContains(login_response, "AS")
        self.assertContains(login_response, "ANNELSA LUXURY")
        self.assertNotContains(login_response, "Continue with Google")
        self.assertNotContains(login_response, "Continue with Facebook")

        register_response = self.client.get(reverse("account_register"))
        self.assertContains(register_response, "AS")
        self.assertContains(register_response, "Create your account")
        self.assertContains(register_response, reverse("account_login"))
        self.assertNotContains(register_response, "Continue with Google")
        self.assertNotContains(register_response, "Continue with Facebook")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_code_resets_password_and_allows_login(self):
        user = User.objects.create_user(
            username="reset@example.com",
            email="reset@example.com",
            password="OriginalPassword-123!",
        )

        response = self.client.post(
            reverse("account_password_reset"),
            {"email": user.email},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an account exists for that address")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])

        code = mail.outbox[0].body.split("code is ", 1)[1][:6]
        reset_record = PasswordResetCode.objects.get(user=user)
        self.assertNotEqual(reset_record.code_hash, code)

        response = self.client.post(
            reverse("account_password_reset_confirm"),
            {
                "email": user.email,
                "code": code,
                "new_password1": "FreshPassword-981!",
                "new_password2": "FreshPassword-981!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Password updated")
        self.assertFalse(PasswordResetCode.objects.filter(user=user).exists())
        user.refresh_from_db()
        self.assertTrue(user.check_password("FreshPassword-981!"))

        login_response = self.client.post(
            reverse("account_login"),
            {"email": user.email, "password": "FreshPassword-981!"},
        )
        self.assertEqual(login_response.json()["status"], "success")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_does_not_disclose_unknown_email(self):
        response = self.client.post(
            reverse("account_password_reset"),
            {"email": "unknown@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an account exists for that address")
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_code_expires_and_locks_after_five_wrong_attempts(self):
        user = User.objects.create_user(
            username="attempts@example.com",
            email="attempts@example.com",
            password="OriginalPassword-123!",
        )
        self.client.post(
            reverse("account_password_reset"),
            {"email": user.email},
        )
        code = mail.outbox[0].body.split("code is ", 1)[1][:6]

        for _ in range(5):
            response = self.client.post(
                reverse("account_password_reset_confirm"),
                {"email": user.email, "code": "invalid"},
            )
            self.assertEqual(response.status_code, 400)

        response = self.client.post(
            reverse("account_password_reset_confirm"),
            {
                "email": user.email,
                "code": code,
                "new_password1": "FreshPassword-981!",
                "new_password2": "FreshPassword-981!",
            },
        )
        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.check_password("FreshPassword-981!"))

        reset_record = PasswordResetCode.objects.get(user=user)
        reset_record.attempts = 0
        reset_record.expires_at = timezone.now() - timedelta(seconds=1)
        reset_record.save(update_fields=["attempts", "expires_at"])
        response = self.client.post(
            reverse("account_password_reset_confirm"),
            {
                "email": user.email,
                "code": code,
                "new_password1": "FreshPassword-981!",
                "new_password2": "FreshPassword-981!",
            },
        )
        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.check_password("FreshPassword-981!"))

    def test_registration_rejects_invalid_email_and_password_mismatch(self):
        invalid_email_response = self.client.post(
            reverse("account_register"),
            {
                "email": "not-an-email",
                "password1": "SecurePassword-123!",
                "password2": "SecurePassword-123!",
            },
        )
        self.assertEqual(invalid_email_response.status_code, 200)
        self.assertIn("email", invalid_email_response.context["form"].errors)
        self.assertEqual(User.objects.count(), 0)

        mismatch_response = self.client.post(
            reverse("account_register"),
            {
                "email": "customer@example.com",
                "password1": "SecurePassword-123!",
                "password2": "DifferentPassword-456!",
            },
        )
        self.assertEqual(mismatch_response.status_code, 200)
        self.assertIn("password2", mismatch_response.context["form"].errors)
        self.assertEqual(User.objects.count(), 0)

    def test_registration_login_and_private_order_history(self):
        response = self.client.post(
            reverse("account_register"),
            {
                "email": "customer@example.com",
                "password1": "SecurePassword-123!",
                "password2": "SecurePassword-123!",
            },
        )
        self.assertRedirects(response, reverse("account_orders"))
        customer_user = User.objects.get(email="customer@example.com")
        self.assertNotEqual(customer_user.password, "SecurePassword-123!")
        self.assertTrue(customer_user.check_password("SecurePassword-123!"))
        customer = Customer.objects.create(
            user=customer_user,
            name="Customer",
            phone="12345",
        )
        own_order = Order.objects.create(
            customer=customer,
            total=Decimal("25.00"),
        )
        other_customer = Customer.objects.create(
            name="Other Customer",
            phone="54321",
        )
        Order.objects.create(customer=other_customer, total=Decimal("50.00"))

        self.client.logout()
        login_response = self.client.post(
            reverse("account_login"),
            {
                "email": "customer@example.com",
                "password": "SecurePassword-123!",
            },
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.json()["status"], "success")
        orders_response = self.client.get(reverse("account_orders"))
        self.assertContains(orders_response, f"Order #{own_order.id}")
        self.assertNotContains(
            orders_response,
            f"Order #{own_order.id + 1}",
        )

    def test_order_history_requires_login(self):
        response = self.client.get(reverse("account_orders"))
        self.assertRedirects(
            response,
            f"{reverse('account_login')}?next={reverse('account_orders')}",
        )

    def test_account_dashboard_shows_profile_and_security_sections(self):
        user = User.objects.create_user(
            username="dashboard@example.com",
            email="dashboard@example.com",
            password="SecurePassword-123!",
        )
        Customer.objects.create(
            user=user,
            name="Dashboard Customer",
            phone="12345",
            email="buyer@example.com",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("account_orders"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profile details")
        self.assertContains(response, "Dashboard Customer")
        self.assertContains(response, "buyer@example.com")
        self.assertContains(response, "Order history")
        self.assertContains(response, reverse("account_password_change"))

    def test_password_change_requires_login_and_updates_password(self):
        password_change_url = reverse("account_password_change")
        anonymous_response = self.client.get(password_change_url)
        self.assertRedirects(
            anonymous_response,
            f"{reverse('account_login')}?next={password_change_url}",
        )

        user = User.objects.create_user(
            username="password@example.com",
            email="password@example.com",
            password="SecurePassword-123!",
        )
        self.client.force_login(user)
        response = self.client.post(
            password_change_url,
            {
                "old_password": "SecurePassword-123!",
                "new_password1": "AnotherSecurePassword-456!",
                "new_password2": "AnotherSecurePassword-456!",
            },
        )

        self.assertRedirects(response, reverse("account_orders"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("AnotherSecurePassword-456!"))


class AdminInventoryTests(ShopTestCase):
    def test_cancelling_order_restores_reserved_stock(self):
        customer = Customer.objects.create(
            name="Test Buyer",
            phone="12345",
        )
        self.product.stock = 8
        self.product.save(update_fields=["stock"])
        order = Order.objects.create(
            customer=customer,
            total=Decimal("2500.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            price=self.product.price,
            quantity=2,
        )

        order.status = "cancelled"
        OrderAdmin(Order, AdminSite()).save_model(
            RequestFactory().post("/admin/shop/order/"),
            order,
            form=None,
            change=True,
        )

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
