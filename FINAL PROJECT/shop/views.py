
import json
import logging
import os
import re
import secrets
import smtplib
import uuid
from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote

import requests

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Avg, F, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import (
    Product,
    Category,
    Review,
    SiteSettings,
    SocialMediaLink,
    Customer,
    Order,
    OrderItem,
    PaymentTransaction,
    PasswordResetCode,
)
from .forms import AccountCreationForm, PasswordResetRequestForm

logger = logging.getLogger(__name__)
User = get_user_model()


class StockUnavailable(Exception):
    def __init__(self, product_name, available):
        self.product_name = product_name
        self.available = available
        super().__init__(product_name, available)


def _restore_order_stock(order):
    for item in order.items.all():
        Product.objects.filter(pk=item.product_id).update(
            stock=F("stock") + item.quantity
        )


def _paystack_secret_key(site_settings, test_mode=None):
    if test_mode is None:
        test_mode = site_settings.paystack_test_mode
    variable = (
        "PAYSTACK_TEST_SECRET_KEY"
        if test_mode
        else "PAYSTACK_LIVE_SECRET_KEY"
    )
    return os.environ.get(variable, "").strip()


def _home_context(**extra):
    products = (
        Product.objects
        .filter(is_active=True)
        .select_related("category")
        .prefetch_related("images", "reviews")
        .annotate(
            average_rating=Avg(
                "reviews__rating",
                filter=Q(reviews__is_approved=True),
            )
        )
    )

    categories = Category.objects.all()

    reviews = (
        Review.objects
        .filter(is_approved=True, is_featured=True)
        .select_related("product")
    )[:5]

    site_settings = SiteSettings.objects.first()

    social_links = SocialMediaLink.objects.filter(is_active=True)

    return {
        "products": products,
        "categories": categories,
        "reviews": reviews,
        "site_settings": site_settings,
        "social_links": social_links,
        "checkout_key": uuid.uuid4().hex,
        **extra,
    }


def home(request):
    context = _home_context(query=request.GET.get("q", "").strip())
    return render(request, "shop/index.html", context)


def _payment_result(request, **context):
    return render(
        request,
        "shop/index.html",
        _home_context(query=request.GET.get("q", "").strip(), **context),
    )


@require_POST
def create_order(request):
    try:
        site_settings = SiteSettings.objects.first()

        if not site_settings:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Site and order settings have not been configured.",
                },
                status=500,
            )

        payment_method = site_settings.payment_method
        if payment_method not in {"contact", "paystack"}:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "The configured payment method is invalid.",
                },
                status=500,
            )

        whatsapp_number = ""
        telegram_username = ""
        contact_method = request.POST.get("contact_method", "").strip()
        if payment_method == "contact":
            whatsapp_number = (
                re.sub(r"\D", "", site_settings.whatsapp_number)
                if site_settings.whatsapp_enabled
                else ""
            )
            telegram_username = (
                site_settings.telegram_username.strip().lstrip("@")
                if site_settings.telegram_enabled
                else ""
            )
            if contact_method == "whatsapp" and not whatsapp_number:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            "WhatsApp is not configured in Site & Order Settings."
                        ),
                    },
                    status=400,
                )
            if contact_method == "telegram" and not re.fullmatch(
                r"[A-Za-z0-9_]{5,32}", telegram_username
            ):
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            "Telegram is not configured in Site & Order Settings."
                        ),
                    },
                    status=400,
                )
            if contact_method not in {"whatsapp", "telegram"}:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Choose WhatsApp or Telegram for your order.",
                    },
                    status=400,
                )

        customer_name = request.POST.get("customer_name", "").strip()
        phone = request.POST.get("phone", "").strip()
        location = request.POST.get("location", "").strip()
        address = request.POST.get("address", "").strip()
        additional_information = request.POST.get(
            "additional_information",
            ""
        ).strip()

        cart_data = request.POST.get("cart_data", "")

        if not customer_name:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Please enter your full name."
                },
                status=400
            )

        if not phone:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Please enter your phone number."
                },
                status=400
            )

        if not location:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Please enter your location."
                },
                status=400
            )

        if not address:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Please enter your delivery address."
                },
                status=400
            )

        if not cart_data:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Your cart is empty."
                },
                status=400
            )

        try:
            cart = json.loads(cart_data)
        except json.JSONDecodeError:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Invalid cart data."
                },
                status=400
            )

        if not isinstance(cart, list) or not cart:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Your cart is empty."
                },
                status=400
            )

        quantities = {}
        for item in cart:
            if not isinstance(item, dict):
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Invalid product information.",
                    },
                    status=400,
                )
            try:
                product_id = int(item.get("id"))
                quantity = int(item.get("quantity", 1))
            except (TypeError, ValueError):
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Invalid product information."
                    },
                    status=400
                )

            if product_id < 1 or quantity < 1:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Invalid product quantity."
                    },
                    status=400
                )

            quantities[product_id] = (
                quantities.get(product_id, 0) + quantity
            )

        validated_items = []
        total = Decimal("0.00")

        for product_id, quantity in quantities.items():
            product = Product.objects.filter(
                id=product_id,
                is_active=True,
            ).first()

            if not product:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            "One of the products in your cart "
                            "is no longer available."
                        )
                    },
                    status=400
                )

            if product.stock < quantity:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            f"Only {product.stock} unit(s) of "
                            f"{product.name} are available."
                        )
                    },
                    status=400
                )

            subtotal = product.price * quantity

            validated_items.append(
                {
                    "product": product,
                    "quantity": quantity,
                    "subtotal": subtotal,
                }
            )

            total += subtotal

        email = request.POST.get("email", "").strip()
        secret_key = ""
        if email:
            try:
                validate_email(email)
            except ValidationError:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Please enter a valid email address.",
                    },
                    status=400,
                )
        if payment_method == "paystack":
            if not email:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            "Email address is required for Paystack payment."
                        ),
                    },
                    status=400,
                )
            secret_key = _paystack_secret_key(site_settings)
            if not secret_key:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            "The Paystack secret key for the selected "
                            "test/live mode is not configured on the server."
                        ),
                    },
                    status=500,
                )

        checkout_key = request.POST.get("checkout_key", "").strip()
        if checkout_key and not re.fullmatch(
            r"[A-Fa-f0-9-]{32,64}", checkout_key
        ):
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        "Invalid checkout request. Please refresh and try again."
                    ),
                },
                status=400,
            )
        if checkout_key and Order.objects.filter(
            checkout_key=checkout_key
        ).exists():
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        "This checkout was already submitted. "
                        "Please do not submit it again."
                    ),
                },
                status=409,
            )

        with transaction.atomic():
            for item in validated_items:
                updated = Product.objects.filter(
                    pk=item["product"].pk,
                    is_active=True,
                    stock__gte=item["quantity"],
                ).update(stock=F("stock") - item["quantity"])
                if not updated:
                    current_stock = Product.objects.filter(
                        pk=item["product"].pk
                    ).values_list("stock", flat=True).first()
                    raise StockUnavailable(
                        item["product"].name,
                        current_stock or 0,
                    )

            customer_data = {
                "name": customer_name,
                "phone": phone,
                "email": email,
                "address": address,
                "city": location,
            }
            if request.user.is_authenticated:
                customer, _ = Customer.objects.update_or_create(
                    user=request.user,
                    defaults=customer_data,
                )
            else:
                customer = Customer.objects.create(**customer_data)

            order = Order.objects.create(
                customer=customer,
                total=total,
                status="pending",
                additional_note=additional_information,
                checkout_key=checkout_key or None,
            )

            for item in validated_items:
                product = item["product"]

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    product_name=product.name,
                    price=product.price,
                    quantity=item["quantity"],
                )

            # -------------------------------------------------
            # WHATSAPP / TELEGRAM
            # -------------------------------------------------

            if payment_method == "contact":

                order_message = build_order_message(
                    order=order,
                    customer=customer,
                    validated_items=validated_items,
                )

                if contact_method == "whatsapp":
                    redirect_url = (
                        "https://wa.me/"
                        f"{whatsapp_number}"
                        "?text="
                        f"{quote(order_message, safe='')}"
                    )
                else:
                    redirect_url = (
                        f"https://t.me/{telegram_username}"
                        f"?text={quote(order_message, safe='')}"
                    )

                return JsonResponse(
                    {
                        "status": "redirect",
                        "order_id": order.id,
                        "total": str(total),
                        "redirect_url": redirect_url,
                    }
                )

            # -------------------------------------------------
            # PAYSTACK
            # -------------------------------------------------

            if payment_method == "paystack":
                reference = (
                    f"ANL-{order.id}-"
                    f"{uuid.uuid4().hex[:12].upper()}"
                )

                amount_in_kobo = int(
                    total * Decimal("100")
                )

                payment_transaction = PaymentTransaction.objects.create(
                    order=order,
                    reference=reference,
                    amount=total,
                    currency=site_settings.currency,
                    paystack_test_mode=site_settings.paystack_test_mode,
                    status="pending",
                )

                callback_url = request.build_absolute_uri(
                    reverse("paystack_callback")
                )

                payload = {
                    "email": email,
                    "amount": amount_in_kobo,
                    "currency": site_settings.currency,
                    "reference": reference,
                    "callback_url": callback_url,
                    "metadata": {
                        "order_id": order.id,
                        "order_reference": reference,
                        "customer_id": customer.id,
                        "customer_name": customer.name,
                        "customer_phone": customer.phone,
                        "custom_fields": [
                            {
                                "display_name": f"Item {index}",
                                "variable_name": f"item_{index}",
                                "value": (
                                    f"{item.product_name} x {item.quantity}"
                                ),
                            }
                            for index, item in enumerate(
                                order.items.all(),
                                start=1,
                            )
                        ],
                    },
                }

                headers = {
                    "Authorization": f"Bearer {secret_key}",
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                }

                try:
                    headers["Authorization"] = f"Bearer {secret_key}"
                    response = requests.post(
                        "https://api.paystack.co/transaction/initialize",
                        json=payload,
                        headers=headers,
                        timeout=30,
                    )
                    response.raise_for_status()
                    response_data = response.json()

                except (requests.RequestException, ValueError) as exc:
                    payment_transaction.status = "failed"
                    payment_transaction.gateway_response = str(exc)
                    payment_transaction.save(
                        update_fields=[
                            "status",
                            "gateway_response",
                            "updated_at",
                        ]
                    )
                    _restore_order_stock(order)
                    order.status = "cancelled"
                    order.save(update_fields=["status", "updated_at"])

                    return JsonResponse(
                        {
                            "status": "error",
                            "message": (
                                "Unable to connect to Paystack."
                            ),
                        },
                        status=502
                    )

                payment_transaction.gateway_response = json.dumps(
                    response_data
                )

                if (
                    not response_data.get("status")
                    or not response_data.get("data")
                    or not response_data["data"].get(
                        "authorization_url"
                    )
                ):
                    payment_transaction.status = "failed"
                    payment_transaction.save(
                        update_fields=[
                            "status",
                            "gateway_response",
                            "updated_at",
                        ]
                    )
                    _restore_order_stock(order)
                    order.status = "cancelled"
                    order.save(update_fields=["status", "updated_at"])

                    return JsonResponse(
                        {
                            "status": "error",
                            "message": (
                                response_data.get(
                                    "message",
                                    "Paystack initialization failed."
                                )
                            ),
                        },
                        status=502
                    )

                payment_transaction.save(
                    update_fields=[
                        "gateway_response",
                        "updated_at",
                    ]
                )

                return JsonResponse(
                    {
                        "status": "paystack",
                        "order_id": order.id,
                        "reference": reference,
                        "authorization_url": (
                            response_data["data"]["authorization_url"]
                        ),
                    }
                )

        return JsonResponse(
            {
                "status": "error",
                "message": "Invalid payment method."
            },
            status=400
        )

    except IntegrityError:
        if checkout_key and Order.objects.filter(
            checkout_key=checkout_key
        ).exists():
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        "This checkout was already submitted. "
                        "Please do not submit it again."
                    ),
                },
                status=409,
            )
        logger.exception("Database error while creating an order")
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Unable to save your order. Please try again."
                ),
            },
            status=500,
        )
    except StockUnavailable as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    f"Only {exc.available} unit(s) of {exc.product_name} "
                    "remain in stock. Please update your cart."
                ),
            },
            status=400,
        )
    except Exception:
        logger.exception("Unexpected error while creating an order")
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "An unexpected error occurred while "
                    "creating your order."
                ),
            },
            status=500
        )


@require_POST
def submit_review(request):
    product_id = request.POST.get("product_id", "").strip()
    name = request.POST.get("name", "").strip()
    comment = request.POST.get("comment", "").strip()
    try:
        rating = int(request.POST.get("rating", ""))
        product_id = int(product_id)
    except (TypeError, ValueError):
        return JsonResponse(
            {"status": "error", "message": "Choose a product and rating."},
            status=400,
        )

    if not name or len(name) > 150:
        return JsonResponse(
            {
                "status": "error",
                "message": "Enter a name of 150 characters or fewer.",
            },
            status=400,
        )
    if not comment or len(comment) > 5000:
        return JsonResponse(
            {
                "status": "error",
                "message": "Write a review of 5,000 characters or fewer.",
            },
            status=400,
        )
    if rating < 1 or rating > 5:
        return JsonResponse(
            {"status": "error", "message": "Rating must be between 1 and 5."},
            status=400,
        )

    product = Product.objects.filter(
        pk=product_id,
        is_active=True,
    ).first()
    if not product:
        return JsonResponse(
            {
                "status": "error",
                "message": "That product is no longer available.",
            },
            status=404,
        )

    customer = Customer.objects.filter(user=request.user).first() if (
        request.user.is_authenticated
    ) else None
    Review.objects.create(
        product=product,
        customer=customer,
        name=name,
        rating=rating,
        comment=comment,
    )
    return JsonResponse(
        {
            "status": "success",
            "message": "Thank you. Your review will appear after approval.",
        }
    )


@require_http_methods(["GET", "POST"])
def account_login(request):
    if request.method == "GET":
        return render(request, "shop/account_login.html")

    email_or_username = request.POST.get("email", "").strip()
    password = request.POST.get("password", "")
    if not email_or_username or not password:
        return JsonResponse(
            {
                "status": "error",
                "message": "Enter your email address and password.",
            },
            status=400,
        )

    user_record = User.objects.filter(
        Q(email__iexact=email_or_username)
        | Q(username__iexact=email_or_username)
    ).first()
    user = authenticate(
        request,
        username=user_record.get_username() if user_record else email_or_username,
        password=password,
    )
    if not user:
        return JsonResponse(
            {
                "status": "error",
                "message": "Email/username or password is incorrect.",
            },
            status=400,
        )

    login(request, user)
    return JsonResponse(
        {"status": "success", "redirect_url": reverse("account_orders")}
    )


@require_http_methods(["GET", "POST"])
def account_register(request):
    if request.method == "POST":
        form = AccountCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("account_orders")
    else:
        form = AccountCreationForm()

    return render(request, "shop/account_register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def account_password_reset(request):
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        reset_code = None
        code = None
        with transaction.atomic():
            user = (
                User.objects
                .select_for_update()
                .filter(email__iexact=email, is_active=True)
                .first()
            )
            if user:
                now = timezone.now()
                reset_code = PasswordResetCode.objects.filter(user=user).first()
                cooldown = timedelta(minutes=1)
                if not reset_code or now - reset_code.created_at >= cooldown:
                    code = f"{secrets.randbelow(1_000_000):06d}"
                    reset_code, _ = PasswordResetCode.objects.update_or_create(
                        user=user,
                        defaults={
                            "code_hash": make_password(code),
                            "created_at": now,
                            "expires_at": now + timedelta(minutes=10),
                            "attempts": 0,
                        },
                    )

        if user and reset_code and code:
            try:
                sent_count = send_mail(
                    "Your password reset confirmation code",
                    (
                        f"Your password reset code is {code}. "
                        "It expires in 10 minutes. If you did not request "
                        "a password reset, you can ignore this email."
                    ),
                    None,
                    [user.email],
                    fail_silently=False,
                )
            except (OSError, smtplib.SMTPException):
                logger.exception(
                    "Password reset email delivery failed for user_id=%s",
                    user.pk,
                )
                reset_code.delete()
            else:
                if sent_count != 1:
                    logger.error(
                        "Password reset email was not sent for user_id=%s",
                        user.pk,
                    )
                    reset_code.delete()

        return render(
            request,
            "shop/account_password_reset_confirm.html",
            {"email": email, "password_form": None},
        )

    return render(
        request,
        "shop/account_password_reset.html",
        {"form": form},
    )


@require_http_methods(["GET", "POST"])
def account_password_reset_confirm(request):
    email = (
        request.POST.get("email", "")
        if request.method == "POST"
        else request.GET.get("email", "")
    ).strip().lower()
    context = {
        "email": email,
        "password_form": None,
        "error": "",
    }

    if request.method == "GET":
        return render(
            request,
            "shop/account_password_reset_confirm.html",
            context,
        )

    code = request.POST.get("code", "").strip()
    with transaction.atomic():
        reset_code = (
            PasswordResetCode.objects
            .select_for_update()
            .filter(user__email__iexact=email, user__is_active=True)
            .first()
        )
        now = timezone.now()
        if (
            not reset_code
            or reset_code.expires_at <= now
            or reset_code.attempts >= 5
        ):
            context["error"] = (
                "That code is invalid or expired. Request a new code."
            )
            return render(
                request,
                "shop/account_password_reset_confirm.html",
                context,
                status=400,
            )

        if not code.isdecimal() or len(code) != 6 or not check_password(
            code,
            reset_code.code_hash,
        ):
            reset_code.attempts += 1
            reset_code.save(update_fields=["attempts"])
            context["error"] = (
                "That code is invalid or expired. Request a new code."
            )
            return render(
                request,
                "shop/account_password_reset_confirm.html",
                context,
                status=400,
            )

        password_form = SetPasswordForm(reset_code.user, request.POST)
        context["password_form"] = password_form
        if not password_form.is_valid():
            return render(
                request,
                "shop/account_password_reset_confirm.html",
                context,
                status=400,
            )

        password_form.save()
        reset_code.delete()
        context["complete"] = True

    return render(
        request,
        "shop/account_password_reset_confirm.html",
        context,
    )


@login_required
def account_orders(request):
    customer = Customer.objects.filter(user=request.user).first()
    orders = (
        Order.objects
        .filter(customer=customer)
        .prefetch_related("items")
        if customer
        else Order.objects.none()
    )
    return render(
        request,
        "shop/account_orders.html",
        {"customer": customer, "orders": orders},
    )


@require_POST
def account_logout(request):
    logout(request)
    return redirect("home")


@require_GET
def paystack_callback(request):
    reference = request.GET.get(
        "reference",
        ""
    ).strip()

    if not reference:
        return _payment_result(
            request,
            payment_error="No Paystack payment reference was provided.",
        )

    payment_transaction = (
        PaymentTransaction.objects
        .select_related(
            "order",
            "order__customer"
        )
        .filter(reference=reference)
        .first()
    )

    if not payment_transaction:
        return _payment_result(
            request,
            payment_error="Payment transaction could not be found.",
        )

    if payment_transaction.status == "success":
        return _payment_result(
            request,
            payment_success=True,
            order_id=payment_transaction.order_id,
            payment_reference=reference,
        )
    if payment_transaction.status != "pending":
        return _payment_result(
            request,
            payment_error="This payment was already marked unsuccessful.",
        )

    site_settings = SiteSettings.objects.first()
    secret_key = (
        _paystack_secret_key(
            site_settings,
            payment_transaction.paystack_test_mode,
        )
        if site_settings
        else ""
    )

    if not secret_key:
        return _payment_result(
            request,
            payment_error=(
                "The Paystack secret key for the selected mode "
                "is not configured."
            ),
        )

    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
    }

    try:
        headers["Authorization"] = f"Bearer {secret_key}"
        response = requests.get(
            (
                "https://api.paystack.co/transaction/verify/"
                f"{quote(reference)}"
            ),
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        response_data = response.json()

    except (requests.RequestException, ValueError):
        logger.exception(
            "Unable to verify Paystack transaction %s", reference
        )
        return _payment_result(
            request,
            payment_error=(
                "Unable to verify the payment with Paystack. "
                "Please contact us before trying again."
            ),
        )

    payment_transaction.gateway_response = json.dumps(
        response_data
    )

    data = response_data.get("data") or {}

    payment_successful = (
        response_data.get("status") is True
        and data.get("status") == "success"
        and data.get("reference") == reference
        and payment_transaction.amount == payment_transaction.order.total
    )

    expected_amount = int(
        payment_transaction.amount * Decimal("100")
    )

    try:
        paid_amount = int(data.get("amount"))
    except (TypeError, ValueError):
        paid_amount = None

    expected_currency = (
        payment_transaction.currency or "NGN"
    )

    received_currency = data.get(
        "currency",
        ""
    )

    amount_matches = (
        paid_amount == expected_amount
    )

    currency_matches = (
        str(received_currency).upper()
        == expected_currency.upper()
    )

    with transaction.atomic():
        payment_transaction = (
            PaymentTransaction.objects
            .select_for_update()
            .select_related("order")
            .get(pk=payment_transaction.pk)
        )
        if payment_transaction.status == "pending":
            payment_transaction.gateway_response = json.dumps(response_data)
            if payment_successful and amount_matches and currency_matches:
                payment_transaction.status = "success"
                payment_transaction.paid_at = timezone.now()
                payment_transaction.order.status = "confirmed"
            else:
                payment_transaction.status = "failed"
                _restore_order_stock(payment_transaction.order)
                payment_transaction.order.status = "cancelled"
            payment_transaction.save(
                update_fields=[
                    "status",
                    "paid_at",
                    "gateway_response",
                    "updated_at",
                ]
            )
            payment_transaction.order.save(
                update_fields=["status", "updated_at"]
            )

    if payment_transaction.status == "success":
        return _payment_result(
            request,
            payment_success=True,
            order_id=payment_transaction.order_id,
            payment_reference=reference,
        )
    return _payment_result(
        request,
        payment_error="Payment could not be verified successfully.",
    )


def build_order_message(
    order,
    customer,
    validated_items,
):
    lines = [
        "ANNELSA LUXURY ORDER",
        "",
        f"Order ID: #{order.id}",
        f"Customer: {customer.name}",
        f"Phone: {customer.phone}",
        f"Location: {customer.city}",
        f"Address: {customer.address}",
        "",
        "PRODUCTS:",
    ]

    for item in validated_items:
        product = item["product"]
        quantity = item["quantity"]
        subtotal = item["subtotal"]

        lines.append(
            f"- {product.name} x {quantity} @ "
            f"₦{product.price:,.2f} each = ₦{subtotal:,.2f}"
        )

    lines.extend(
        [
            "",
            f"TOTAL: ₦{order.total:,.2f}",
        ]
    )

    if order.additional_note:
        lines.extend(
            [
                "",
                "Additional Information:",
                order.additional_note,
            ]
        )

    return "\n".join(lines)
