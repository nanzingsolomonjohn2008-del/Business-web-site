
import secrets
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urlsplit

from PIL import Image, ImageOps

from django.core.files.base import ContentFile
from django.db import models
from django.conf import settings


MAX_IMAGE_SIZE = 300 * 1024
MAX_IMAGE_DIMENSION = 1600


def _compress_uploaded_image(uploaded_image):
    if uploaded_image is None or getattr(uploaded_image, "_committed", True):
        return uploaded_image

    with Image.open(uploaded_image) as source:
        image = ImageOps.exif_transpose(source)
        image.load()
        has_transparency = (
            image.mode in {"RGBA", "LA"}
            or "transparency" in image.info
        )
        if has_transparency:
            image = image.convert("RGBA")
            image_format = "PNG"
            extension = ".png"
        else:
            image = image.convert("RGB")
            image_format = "JPEG"
            extension = ".jpg"

        image.thumbnail(
            (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
            Image.Resampling.LANCZOS,
        )
        quality = 85
        while True:
            buffer = BytesIO()
            options = {"optimize": True}
            if image_format == "JPEG":
                options.update(quality=quality, progressive=True)
            image.save(buffer, format=image_format, **options)

            if buffer.tell() <= MAX_IMAGE_SIZE:
                break

            if image_format == "JPEG" and quality > 45:
                quality -= 10
                continue

            width, height = image.size
            if width == 1 and height == 1:
                break
            image = image.resize(
                (max(1, int(width * 0.8)), max(1, int(height * 0.8))),
                Image.Resampling.LANCZOS,
            )
            quality = 85

    name = f"{Path(uploaded_image.name).stem}{extension}"
    return ContentFile(buffer.getvalue(), name=name)


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="categories/",
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images"
    )
    image = models.ImageField(upload_to="products/")
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]

    def save(self, *args, **kwargs):
        if self.image:
            self.image = _compress_uploaded_image(self.image)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} - Image {self.display_order}"


class Customer(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_profile",
    )
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class PasswordResetCode(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_code",
    )
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)


class Review(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews"
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviews"
    )
    name = models.CharField(max_length=150)
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField()
    is_approved = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.product.name} ({self.rating}/5)"


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("processing", "Processing"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="orders"
    )
    checkout_key = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )
    verification_code = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
    )
    is_delivered = models.BooleanField(default=False)
    additional_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.id} - {self.customer.name}"

    def generate_verification_code(self):
        while True:
            code = f"PICK-{secrets.randbelow(1_000_000):06d}"
            if not Order.objects.filter(verification_code=code).exists():
                self.verification_code = code
                return code

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        status_will_be_saved = (
            update_fields is None or "status" in update_fields
        )

        if status_will_be_saved and self.status == "confirmed":
            if self._state.adding:
                status_was_confirmed = False
            else:
                status_was_confirmed = (
                    Order.objects.filter(
                        pk=self.pk,
                        status="confirmed",
                    ).exists()
                )

            if not status_was_confirmed and not self.verification_code:
                self.generate_verification_code()
                if update_fields is not None:
                    kwargs["update_fields"] = set(update_fields) | {
                        "verification_code"
                    }

        super().save(*args, **kwargs)


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="order_items"
    )
    product_name = models.CharField(max_length=200)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["id"]

    @property
    def subtotal(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"


class SiteSettings(models.Model):
    ORDER_METHOD_CHOICES = [
        ("contact", "WhatsApp / Telegram"),
        ("paystack", "Paystack"),
    ]

    business_name = models.CharField(
        max_length=200,
        default="ANNELSA LUXURY"
    )
    logo = models.ImageField(
        upload_to="site/",
        blank=True,
    )
    tagline = models.CharField(
        max_length=255,
        blank=True,
        default="Premium luxury products for modern lifestyle."
    )

    whatsapp_number = models.CharField(
        max_length=30,
        blank=True
    )
    telegram_username = models.CharField(
        max_length=100,
        blank=True
    )

    whatsapp_enabled = models.BooleanField(default=True)
    telegram_enabled = models.BooleanField(default=True)

    payment_method = models.CharField(
        "How customers order/pay",
        max_length=20,
        choices=ORDER_METHOD_CHOICES,
        default="contact",
    )
    paystack_public_key = models.CharField(max_length=255, blank=True)
    paystack_test_mode = models.BooleanField(default=True)
    currency = models.CharField(max_length=10, default="NGN")

    developer_name = models.CharField(
        "Developer name",
        max_length=150,
        blank=True,
        default="",
    )
    developer_url = models.URLField(
        "Developer website",
        blank=True,
    )
    developer_email = models.EmailField(
        "Developer email",
        blank=True,
    )
    developer_whatsapp = models.CharField(
        "Developer WhatsApp number",
        max_length=30,
        blank=True,
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site & Order Settings"
        verbose_name_plural = "Site & Order Settings"

    def __str__(self):
        return self.business_name

    def save(self, *args, **kwargs):
        if self.logo:
            self.logo = _compress_uploaded_image(self.logo)
        super().save(*args, **kwargs)

    @property
    def developer_whatsapp_url(self):
        value = self.developer_whatsapp.strip()
        if value.lower().startswith(("http://", "https://")):
            parsed_url = urlsplit(value)
            if parsed_url.hostname not in {"wa.me", "www.wa.me"}:
                return ""
            value = parsed_url.path.strip("/").split("/", 1)[0]

        digits = "".join(character for character in value if character.isdigit())
        if not digits:
            return ""
        greeting = "Hello, I saw the website you built"
        return f"https://wa.me/{digits}?text={quote(greeting)}"

    @property
    def whatsapp_url(self):
        digits = "".join(
            character
            for character in self.whatsapp_number
            if character.isdigit()
        )
        return f"https://wa.me/{digits}" if digits else ""

    @property
    def telegram_url(self):
        username = self.telegram_username.strip().lstrip("@")
        if not username:
            return ""
        return f"https://t.me/{username}"


class SocialMediaLink(models.Model):
    PLATFORM_CHOICES = [
        ("instagram", "Instagram"),
        ("tiktok", "TikTok"),
        ("facebook", "Facebook"),
        ("youtube", "YouTube"),
        ("twitter", "X / Twitter"),
        ("snapchat", "Snapchat"),
        ("other", "Other"),
    ]

    platform = models.CharField(
        max_length=20,
        choices=PLATFORM_CHOICES
    )
    name = models.CharField(max_length=100)
    url = models.URLField()
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Footer Social Media Link"
        verbose_name_plural = "Footer Social Media Links"
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class PaymentTransaction(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("abandoned", "Abandoned"),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="payment_transactions"
    )

    reference = models.CharField(
        max_length=100,
        unique=True
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    currency = models.CharField(
        max_length=10,
        default="NGN"
    )

    paystack_test_mode = models.BooleanField(
        default=True,
        help_text="Whether this transaction was initialized in test mode.",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    gateway_response = models.TextField(
        blank=True
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} - {self.status}"
