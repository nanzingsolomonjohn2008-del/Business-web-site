from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0011_passwordresetcode"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="developer_name",
            field=models.CharField(
                blank=True,
                default="",
                max_length=150,
                verbose_name="Developer name",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="developer_url",
            field=models.URLField(blank=True, verbose_name="Developer website"),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="developer_email",
            field=models.EmailField(blank=True, verbose_name="Developer email"),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="developer_whatsapp",
            field=models.CharField(
                blank=True,
                max_length=30,
                verbose_name="Developer WhatsApp number",
            ),
        ),
    ]
