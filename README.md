# Tatami Plus

Tatami Plus is a Django monolith with server-rendered templates. The original HTML/CSS preview is integrated into the Django project. The interface and admin use Persian; Django stores timezone-aware dates and uses Jalali fields/widgets for business timestamps.

## Local setup

Python 3.13 and Django 5.2 are currently available in the development environment.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py check
python manage.py migrate
python manage.py runserver
```

Run `python manage.py createsuperuser` once if an admin account has not already been created.

The default database is SQLite so the project can run before PostgreSQL is installed. Django settings are read with `python-decouple` from environment variables or `.env`. To use PostgreSQL, install and start a PostgreSQL server, then set these variables in `.env`:

```dotenv
DB_ENGINE=postgresql
DB_NAME=tatami_plus
DB_USER=postgres
DB_PASSWORD=your-local-database-password
DB_HOST=localhost
DB_PORT=5432
```

For deployment, set `DJANGO_DEBUG=0`, provide a strong `DJANGO_SECRET_KEY`, and set `DJANGO_ALLOWED_HOSTS` to the site's hostnames. The development secret fallback must not be used in production.

The `accounts.User` model extends Django's `AbstractUser` and adds `student` and `coach` roles. It must remain the configured user model before the first database migration. Django settings use `python-decouple` to read environment variables or `.env`.

## Implemented

- Server-rendered Persian home, coach directory, shop catalog, product detail, cart, and account pages.
- Basic registration, login, logout, and student/coach role selection under `/accounts/`.
- Coach applications with pending, approved, and rejected states in Django Admin.
- Private coach certificate uploads, staff-only downloads, and public profiles gated by both approval and team publication.
- Admin-managed product categories, products, local images, size/color variants, prices, and stock.
- Catalog search, category/price/size/color/level filters, sorting, guest session carts, and user carts that merge after login.
- Server-side price totals and stock checks when adding or updating cart items.

The product catalog JSON and local image mapping are not currently in the workspace, so the catalog is empty and no product data has been invented. The price currency is not confirmed. Checkout, order history, and payment integration are not implemented; shipping methods/costs and the payment provider need decisions before those workflows are added.

For frontend/backend route, form, template, and collaboration conventions, see [FRONTEND_BACKEND_HANDOFF.md](FRONTEND_BACKEND_HANDOFF.md).