# Frontend and Backend Cooperation Guide

This document describes how the frontend and backend work together in Tatami Plus. It records the current Django contracts; it is not a request to rebuild the frontend or to add a separate API.

## Architecture

Tatami Plus is a server-rendered Django application. Django owns URLs, authentication and sessions, form validation, permissions, database access, and business rules. Templates render pages; CSS and small JavaScript enhancements are served as static assets. There is currently no JSON API, CORS setup, or client-side authentication contract.

The manager's layered direction applies to how we organize and deliver work: data and constraints, application rules and permissions, page/forms integration, then workflow verification. Keep the existing modular Django apps (`accounts`, `coaches`, `store`) rather than creating duplicate frontend services or moving to a frontend framework.

## Ownership

**Frontend developer**

- Own page markup, visual styling, responsive behavior, and browser-side enhancements.
- Work in Django templates and `static/`; preserve the existing user journeys and Persian RTL design.
- Keep form field names, methods, actions, and CSRF tokens aligned with the contracts below.
- Show Django validation errors and success/error messages returned by the server.

**Backend developer**

- Own models, migrations, URL routing, forms, views, authorization, admin workflows, sessions, and server-side validation.
- Recalculate prices and check inventory on the server. Never trust values supplied by the browser.
- Confirm business rules before adding workflows that are not already specified.

Both developers should agree on route, field, or workflow changes before one side changes the contract. Prefer named Django URLs in templates over hard-coded paths.

## Template and Asset Conventions

- Shared layout: `templates/base.html`.
- Page templates: `templates/accounts/`, `templates/coaches/`, `templates/store/`, and `templates/pages/`.
- Shared CSS: `static/css/styles.css`. Put additional static files under `static/` and reference them with Django's `{% static %}` tag.
- Product uploads use `MEDIA_ROOT` and are served locally only while `DEBUG=True`. Do not use the public media route for private coach certificates; those are served through a staff-protected download view.
- Preserve `<html lang="fa" dir="rtl">`. User-facing copy should be Persian. Use logical CSS properties such as `margin-inline-start` so RTL and any future LTR content remain predictable.
- Django controls the timezone (`Asia/Tehran`) and Jalali date formatting. Do not convert business dates independently in JavaScript. Keep submitted numeric form values parseable by Django; Persian display digits are presentation only.

## Current Routes and Contracts

| Page or action | Route | Contract |
| --- | --- | --- |
| Home | `GET /` | Server-rendered page. |
| Account | `GET /account/` | Shows signed-in role or links to student/coach registration. Gym is visual-only. |
| Login / signup (step 1) | `GET, POST /auth/login/` | There is no separate registration page. Entering a phone number signs in an existing account, and creates a new one after the code is verified. POST fields: `phone` (any Iranian format; the server normalizes it to `09xxxxxxxxx`), `role` (`student` or `coach`; used only when the account is created), and optional hidden `_next`. On success the server sends an OTP and redirects to `/auth/otp/verify/`. Errors: a field error on `phone` for an invalid number or a rate limit, and a non-field error when SMS delivery is not configured. |
| Resend OTP | `POST /auth/otp/send/` | Include `{% csrf_token %}`. Only valid after step 1, because the phone number is held in the session. Resends the code and returns to `/auth/otp/verify/`. A 60-second cooldown and an hourly cap apply, so disable the button or show a countdown instead of letting the user click into the error. |
| Verify OTP (step 2) | `GET, POST /auth/otp/verify/` | POST field: `code`, exactly five digits (Persian and Arabic digits are accepted). A correct code logs the user in and redirects to `/auth/complete-profile/` when the profile is incomplete, otherwise to the stored `next` target or `/account/`. A wrong code re-renders this page with a field error. Codes expire after 120 seconds and are invalidated after five wrong attempts. |
| Complete profile | `GET, POST /auth/complete-profile/` | Login required. POST fields: `name`, `city`, `role` (`student` or `coach`). Marks the profile complete, then redirects to the stored `next` target or `/account/`. Users who already completed it are redirected to `/account/`. |
| Legacy register link | `GET /accounts/register/` | 302 redirect to `/auth/login/`. `?role=coach` preselects the coach option; a safe local `?next=` value is preserved. |
| Legacy login link | `GET /accounts/login/` | 302 redirect to `/auth/login/`. Kept for old bookmarks and templates. |
| Logout | `POST /accounts/logout/` | Include `{% csrf_token %}`. Logout is not a GET link. Redirects to `/`. |
| Coach directory | `GET /coaches/` | Lists only profiles whose application is approved and whose profile is published by the team. |
| Coach profile | `GET /coaches/<profile_id>/` | Public only while both approval and publication conditions hold. |
| Coach application | `GET, POST /coaches/apply/` | Login required; coach role required. Multipart POST fields: `coaching_level`, `specializations`, `years_experience`, `club_name`, `certificate_details`, `certificate_document`. Certificate accepts PDF/JPG/JPEG/PNG up to 10 MB. Submission creates one pending application per coach. |
| Application status | `GET /coaches/application/` | Login required; shows the current user's application and its pending/approved/rejected state. |
| Certificate download | `GET /coaches/applications/<application_id>/certificate/` | Staff-only download for application review. The certificate file is private and is never served as a public media URL. |
| Shop catalog | `GET /store/` | Optional query parameters: `query`, `category`, `size`, `color`, `training_level`, `min_price`, `max_price`, `sort`, `page`. Sorting values: `price_asc`, `price_desc`, `name`; category and choice values should come from rendered Django form controls. |
| Product detail / add to cart | `GET, POST /store/<slug>/` | POST fields: `variant` (database variant ID), `quantity` (positive integer). Include CSRF. Server validates variant/product state and stock. Success redirects to `/store/cart/`; validation errors re-render the detail page. |
| Cart | `GET /store/cart/` | Supports guests through the Django session and signed-in users through their account. A guest cart is merged into the user's cart after login. |
| Update cart line | `POST /store/cart/items/<item_id>/update/` | POST field: `quantity`. Include CSRF. Server validates availability and stock, then redirects to cart. |
| Remove cart line | `POST /store/cart/items/<item_id>/remove/` | Include CSRF. Redirects to cart. |
| Django Admin | `GET /admin/` | Admin/staff workflows for coach review, profile publication, and catalog maintenance. Not a public frontend route. |
| Call-center leads | `GET /admin/accounts/signuplead/` | Staff-only. Visible only to superusers and members of the `call_center` group. A `SignupLead` with status `new` is created automatically for each new coach account; operators update status, note, and assignment inline. Authorized users also receive `new_coach_leads_count` in every template's context. |

Accounts are created without a usable password, so members have no password login. Staff sign in at `/admin/login/` using their phone number in the username field; legacy username-only staff accounts still authenticate that way.

For all Django forms, retain the submitted values and render field and non-field errors when the server returns an invalid form. Product prices and cart totals are presentation data from the server; do not submit an authoritative price or total.

## Implemented and Not Yet Implemented

Implemented: phone + OTP sign-in (one flow for login and signup), persisted student/coach role, profile completion, call-center leads for new coach accounts, coach application submission, admin approval/rejection, team-managed profile publication, public approved-coach pages, product/category/variant/image models, catalog search/filter/sort, and guest/user carts with stock validation.

Not implemented: a verified student-to-coach relationship, student/coach dashboards, class schedules, reviews, checkout, orders/order history, shipping, payment, the virtual club and course videos, the gem ledger, and club geo search. Do not design a frontend flow that implies these are available. The catalog is currently empty because the product catalog and image-mapping files have not been added to the workspace. Currency is also unconfirmed. The `frontend/` directory is still empty, so every template in `templates/` is backend-authored and has not yet been reconciled with the frontend developer's markup.

The backend must not infer that a student is a coach's student merely because they have an account or viewed a profile. Before building relationship-dependent screens or reviews, agree on whether a relationship is admin-assigned, invitation-and-acceptance, or student-request-and-approval.

## Joint Verification

1. Start the Django site with `python manage.py runserver` and review the Persian pages at desktop and mobile widths.
2. Verify the phone flow end to end: a new number receives a code, is created, and is sent to profile completion; an existing number is not; a wrong code and a rapid resend are both blocked. Verify POST logout.
3. Verify that students cannot open coach-only application routes, pending coaches do not appear publicly, and rejected/unpublished profiles remain hidden.
4. Verify catalog filters, product variant selection, guest cart persistence, cart merge after login, quantity updates, and stock errors.
5. Before merging frontend changes, run `python manage.py test` and `python manage.py check`. If routes or fields changed, update this document and the relevant tests in the same change.

## Working Agreement for Changes

When a screen needs a new data field or action, the frontend developer should note the required user interaction and proposed field name. The backend developer confirms the model/form/permission contract before the frontend depends on it. For changes to an existing contract, coordinate the template and backend change together so neither side ships a broken form or route.