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

Run `python manage.py createsuperuser` once if an admin account has not already been created. It asks for a phone number instead of a username, and that phone number is what you type in the username field on `/admin/login/`.

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

The `accounts.User` model extends Django's `AbstractUser` and uses a unique `phone` number as `USERNAME_FIELD`, normalized to `09xxxxxxxxx` by `accounts/phone.py`. It carries a `student` or `coach` role and an `is_profile_complete` flag. It must remain the configured user model before the first database migration. Django settings use `python-decouple` to read environment variables or `.env`.

Members sign in at `/auth/login/` with a phone number and a five-digit code; there is no password login for them. Accounts are only created after a valid code, with an unusable password, and new users are sent to `/auth/complete-profile/`. In development the code is printed to the `runserver` console by `accounts.sms.ConsoleSMSBackend`. Set `SMS_BACKEND` to a real backend before `DJANGO_DEBUG=0`. Codes expire after 120 seconds, allow five attempts, and are rate-limited through Django's cache; configure a shared `CACHES` backend before running multiple workers.

## Implemented

- Server-rendered Persian home, coach directory, shop catalog, product detail, cart, and account pages.
- Phone + OTP authentication under `/auth/` (login and signup in one flow), profile completion, and student/coach roles.
- Call-center signup leads for new coach accounts, visible only to superusers and the `call_center` group.
- Coach applications with pending, approved, and rejected states in Django Admin.
- Private coach certificate uploads, staff-only downloads, and public profiles gated by both approval and team publication.
- Admin-managed product categories, products, local images, size/color variants, prices, and stock.
- Catalog search, category/price/size/color/level filters, sorting, guest session carts, and user carts that merge after login.
- Server-side price totals and stock checks when adding or updating cart items.
- Saved addresses and a checkout flow (address → review → payment) that recalculates prices, shipping, and stock on the server.
- A `Payment` ledger with an idempotent gateway callback, plus order history and admin order management.
- A mock payment gateway (`orders/gateways/mock.py`) that follows the real request/verify protocol so a provider can be swapped in later.
- A virtual club: published courses with coach/level/search filters, a free first episode, paid episodes behind an `Enrollment`, and a coach panel where new courses wait for admin review.
- Private course videos served only by an access-checked view, with no public URL and an optional Nginx `X-Accel-Redirect` handoff.

The product catalog JSON and local image mapping are not currently in the workspace, so the catalog is empty and no product data has been invented. The currency is Toman. `SHIPPING_FLAT_RATE` defaults to a placeholder 50,000 until the real flat price is confirmed. There is no real payment provider yet: `PAYMENT_GATEWAY` points at the mock, which refuses to run unless `PAYMENT_ALLOW_MOCK` is enabled. Coach revenue share and payouts, the gem ledger, and club geo search are not implemented.

For frontend/backend route, form, template, and collaboration conventions, see [FRONTEND_BACKEND_HANDOFF.md](FRONTEND_BACKEND_HANDOFF.md).