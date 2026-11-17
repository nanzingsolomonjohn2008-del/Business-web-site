# ANNELSA LUXURY setup and deployment

## Local development

Use the existing Python environment on Windows:

```powershell
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env.local
```

Django does not load `.env.local` automatically. Set the environment variables
in the terminal or in your editor's run configuration. Keep `DJANGO_DEBUG=true`
for local work. Generate a new local key with:

```powershell
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Install declared packages and start the development server:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

The site is available at `http://127.0.0.1:8000/`; the Django admin is at
`http://127.0.0.1:8000/admin/`. Do not use `runserver` for production.

## Production checklist

1. Choose a Django-compatible host and configure a PostgreSQL database.
2. Set `DJANGO_DEBUG=false`, a unique `DJANGO_SECRET_KEY`, the exact
   `DJANGO_ALLOWED_HOSTS`, and the HTTPS `DJANGO_CSRF_TRUSTED_ORIGINS`.
3. Set `DATABASE_ENGINE=django.db.backends.postgresql` and the database
   connection variables. Keep the database password outside source control.
4. Configure SMTP environment variables if password-reset email is needed.
5. In Django admin, open **Site & Order Settings** to choose either
   WhatsApp/Telegram ordering or Paystack. For contact ordering, enable and
   enter the channels customers can choose from. For Paystack, choose test
   mode and configure the test key in the host environment. Only switch to
   live mode after the provider account and live secret are approved and
   configured.
6. Back up the database and media before deployment. Deploy the code, run
   `manage.py migrate`, then run `manage.py collectstatic --noinput`.
7. Configure the host's supported WSGI/ASGI process, HTTPS, persistent media
   storage, logs, and scheduled database/media backups.
8. Run `manage.py check --deploy` against the production environment, then
   test the site and provider in test mode before accepting live orders.

Do not upload `.env.local`, secret keys, database backups, customer exports, or
uploaded media backups to a public repository. Database migrations do not
replace backups; retain a tested restore copy before applying migrations.
