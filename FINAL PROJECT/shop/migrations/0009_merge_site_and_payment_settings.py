from django.db import migrations, models


def move_payment_settings(apps, schema_editor):
    SiteSettings = apps.get_model("shop", "SiteSettings")
    PaymentSettings = apps.get_model("shop", "PaymentSettings")
    database = schema_editor.connection.alias

    payment_settings = (
        PaymentSettings.objects.using(database).order_by("pk").first()
    )
    if not payment_settings:
        return

    site_settings = (
        SiteSettings.objects.using(database).order_by("pk").first()
    )
    if not site_settings:
        site_settings = SiteSettings.objects.using(database).create()

    site_settings.payment_method = (
        "paystack"
        if payment_settings.payment_method == "paystack"
        else "contact"
    )
    site_settings.paystack_public_key = payment_settings.paystack_public_key
    site_settings.paystack_test_mode = payment_settings.paystack_test_mode
    site_settings.currency = payment_settings.currency
    site_settings.save(
        using=database,
        update_fields=(
            "payment_method",
            "paystack_public_key",
            "paystack_test_mode",
            "currency",
        ),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0008_alter_paymentsettings_payment_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("contact", "WhatsApp / Telegram"),
                    ("paystack", "Paystack"),
                ],
                default="contact",
                max_length=20,
                verbose_name="How customers order/pay",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="paystack_public_key",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="paystack_test_mode",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="currency",
            field=models.CharField(default="NGN", max_length=10),
        ),
        migrations.AlterModelOptions(
            name="sitesettings",
            options={
                "verbose_name": "Site & Order Settings",
                "verbose_name_plural": "Site & Order Settings",
            },
        ),
        migrations.RunPython(
            move_payment_settings,
            migrations.RunPython.noop,
        ),
        migrations.DeleteModel(
            name="PaymentSettings",
        ),
    ]
