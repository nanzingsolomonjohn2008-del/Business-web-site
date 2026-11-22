
from django.contrib.auth.views import PasswordChangeView
from django.urls import path, reverse_lazy

from .views import (
    home,
    create_order,
    submit_review,
    account_login,
    account_register,
    account_orders,
    account_logout,
    account_password_reset,
    account_password_reset_confirm,
    paystack_callback,
)


urlpatterns = [

    path(
        "",
        home,
        name="home"
    ),

    path(
        "create-order/",
        create_order,
        name="create_order"
    ),

    path(
        "reviews/submit/",
        submit_review,
        name="submit_review",
    ),

    path(
        "account/login/",
        account_login,
        name="account_login",
    ),

    path(
        "account/register/",
        account_register,
        name="account_register",
    ),

    path(
        "account/password-reset/",
        account_password_reset,
        name="account_password_reset",
    ),

    path(
        "account/password-reset/confirm/",
        account_password_reset_confirm,
        name="account_password_reset_confirm",
    ),

    path(
        "account/orders/",
        account_orders,
        name="account_orders",
    ),

    path(
        "account/password/",
        PasswordChangeView.as_view(
            template_name="shop/account_password_change.html",
            success_url=reverse_lazy("account_orders"),
        ),
        name="account_password_change",
    ),

    path(
        "account/logout/",
        account_logout,
        name="account_logout",
    ),

    path(
        "paystack/callback/",
        paystack_callback,
        name="paystack_callback"
    ),

]
