"""Server-side client for Neshan's geocoding services (PRD item 6, API only).

Two calls, both `GET` with the Service Key in the `Api-Key` header — the key
lives only in `.env`/settings and never reaches the browser (the PRD's Web Key
for front-end maps is a separate, domain-restricted key, not used here):

- address → coordinates:  /v6/geocoding?address=...
- coordinates → address:  /v5/reverse?lat=...&lng=...

Endpoint versions were taken from Neshan's latest docs (they bump the path
version when the contract changes — the old2020 client used /v2/reverse), so
re-check `platform.neshan.org/docs/api/search-category/` if calls start
404ing. Nothing in this module writes to the database; callers decide what to
do with the result.
"""
import json
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

BASE_URL = 'https://api.neshan.org'
GEOCODING_PATH = '/v6/geocoding'
REVERSE_PATH = '/v5/reverse'
REQUEST_TIMEOUT = 10

# The Gym model stores coordinates as Decimal(9, 6); Neshan returns full
# float precision, so quantize on the way out to fit the column.
COORD_PRECISION = Decimal('0.000001')


class GeocodingError(Exception):
	"""No key configured, the service refused, or it could not be reached."""


def geocode(address):
	"""Written address → `{'lat': Decimal, 'lng': Decimal}` (6 decimal places).

	Raises `GeocodingError` for an empty address, a missing key, or any
	service failure; there is no silent-None path, so callers can't mistake
	"failed" for "no match".
	"""
	address = (address or '').strip()
	if not address:
		raise GeocodingError('آدرس خالی است.')

	payload = _get_json(GEOCODING_PATH, {'address': address})
	location = payload.get('location') or {}
	try:
		return {
			'lat': Decimal(str(location['y'])).quantize(COORD_PRECISION),
			'lng': Decimal(str(location['x'])).quantize(COORD_PRECISION),
		}
	except (KeyError, InvalidOperation, ValueError) as exc:
		raise GeocodingError('پاسخ سرویس نشان مختصات معتبری نداشت.') from exc


def reverse_geocode(lat, lng):
	"""Coordinates → Neshan's location payload (`formatted_address`, `city`,
	`state`, `neighbourhood`, traffic-zone flags, …). Raises `GeocodingError`
	like `geocode`."""
	return _get_json(REVERSE_PATH, {'lat': lat, 'lng': lng})


def _get_json(path, params):
	if not settings.NESHAN_API_KEY:
		raise GeocodingError(
			'کلید سرویس نشان (NESHAN_API_KEY) پیکربندی نشده است.'
		)

	request = Request(
		f'{BASE_URL}{path}?{urlencode(params)}',
		headers={'Api-Key': settings.NESHAN_API_KEY},
	)
	try:
		body = urlopen(request, timeout=REQUEST_TIMEOUT).read()
	except HTTPError as exc:
		# Neshan answers errors with an HTTP status plus a JSON body that
		# names the reason (LimitExceeded, RateExceeded, KeyNotFound, …).
		raise GeocodingError(_describe_error(exc)) from exc
	except (URLError, TimeoutError, OSError) as exc:
		raise GeocodingError(f'دسترسی به سرویس نشان ممکن نشد: {exc}') from exc

	try:
		payload = json.loads(body)
	except ValueError as exc:
		raise GeocodingError('پاسخ نامعتبر از سرویس نشان.') from exc

	if not isinstance(payload, dict) or payload.get('status') != 'OK':
		status = payload.get('status') if isinstance(payload, dict) else None
		raise GeocodingError(f'سرویس نشان خطا داد: {status or "نامشخص"}')
	return payload


def _describe_error(exc):
	try:
		status = json.loads(exc.read()).get('status')
	except ValueError:
		status = None
	return f'سرویس نشان خطا داد: {status or "نامشخص"} (HTTP {exc.code})'
