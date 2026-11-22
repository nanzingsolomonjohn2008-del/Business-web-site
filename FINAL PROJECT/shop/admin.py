
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from .models import (
    Category,
    Product,
    ProductImage,
    Customer,
    Review,
    Order,
    OrderItem,
    SiteSettings,
    SocialMediaLink,
    PaymentTransaction,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):

    list_display = ("name", "created_at")
    search_fields = ("name",)


class ProductImageInline(admin.TabularInline):

    model = ProductImage
    extra = 3


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "category",
        "price",
        "stock",
        "is_active",
        "created_at",
    )

    list_filter = ("category", "is_active")
    search_fields = ("name", "description")
    inlines = [ProductImageInline]


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):

    list_display = ("product", "display_order")
    list_filter = ("product",)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "phone",
        "email",
        "city",
        "created_at",
    )

    search_fields = (
        "name",
        "phone",
        "email",
    )


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "product",
        "rating",
        "is_approved",
        "is_featured",
        "created_at",
    )

    list_filter = (
        "rating",
        "is_approved",
        "is_featured",
    )

    search_fields = (
        "name",
        "comment",
        "product__name",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "customer",
        "total",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "customer__name",
        "customer__phone",
    )

    def save_model(self, request, obj, form, change):
        previous_status = None
        if change:
            previous_status = Order.objects.values_list(
                "status", flat=True
            ).get(pk=obj.pk)

        with transaction.atomic():
            if previous_status != "cancelled" and obj.status == "cancelled":
                super().save_model(request, obj, form, change)
                for item in obj.items.all():
                    Product.objects.filter(pk=item.product_id).update(
                        stock=F("stock") + item.quantity
                    )
                return

            if previous_status == "cancelled" and obj.status != "cancelled":
                for item in obj.items.all():
                    updated = Product.objects.filter(
                        pk=item.product_id,
                        stock__gte=item.quantity,
                    ).update(stock=F("stock") - item.quantity)
                    if not updated:
                        raise ValidationError(
                            f"Not enough stock to reopen order #{obj.pk}."
                        )

            super().save_model(request, obj, form, change)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):

    list_display = (
        "order",
        "product_name",
        "price",
        "quantity",
        "subtotal",
    )

    search_fields = (
        "product_name",
    )


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):

    list_display = (
        "business_name",
        "payment_method",
        "whatsapp_enabled",
        "telegram_enabled",
        "updated_at",
    )
    fieldsets = (
        ("Site details", {"fields": ("business_name", "tagline", "logo")}),
        (
            "Developer credit",
            {
                "fields": (
                    "developer_name",
                    "developer_url",
                    "developer_email",
                    "developer_whatsapp",
                ),
                "description": (
                    "Enter the developer name and a WhatsApp phone number "
                    "in 234... format or a full wa.me URL. The name links to "
                    "WhatsApp at the end of the website."
                ),
            },
        ),
        (
            "WhatsApp / Telegram orders",
            {
                "fields": (
                    "whatsapp_enabled",
                    "whatsapp_number",
                    "telegram_enabled",
                    "telegram_username",
                ),
                "description": (
                    "Enable and enter the contact channels customers may "
                    "choose when contact ordering is selected."
                ),
            },
        ),
        (
            "Order and payment method",
            {
                "fields": ("payment_method",),
                "description": (
                    "Choose contact ordering (WhatsApp or Telegram) or "
                    "Paystack checkout."
                ),
            },
        ),
        (
            "Paystack",
            {
                "fields": (
                    "paystack_test_mode",
                    "currency",
                    "paystack_public_key",
                ),
            },
        ),
    )

@admin.register(SocialMediaLink)
class SocialMediaLinkAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "platform",
        "url",
        "is_active",
        "display_order",
    )

    list_filter = (
        "platform",
        "is_active",
    )

    search_fields = (
        "name",
    )
    fieldsets = (
        (
            "Link shown in the website footer",
            {
                "fields": (
                    "platform",
                    "name",
                    "url",
                    "is_active",
                    "display_order",
                ),
                "description": (
                    "Add the full URL to your public social media profile. "
                    "Active links appear in the website footer."
                ),
            },
        ),
    )


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):

    list_display = (
        "reference",
        "order",
        "amount",
        "currency",
        "status",
        "paid_at",
        "created_at",
    )

    list_filter = (
        "status",
        "currency",
        "created_at",
    )

    search_fields = (
        "reference",
        "order__customer__name",
        "order__customer__phone",
    )

    readonly_fields = (
        "reference",
        "order",
        "amount",
        "currency",
        "status",
        "gateway_response",
        "paid_at",
        "created_at",
        "updated_at",
    )
