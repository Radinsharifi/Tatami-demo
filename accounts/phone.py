import re


_DIGIT_TRANSLATION = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def _to_national(value):
	"""Fold digits and strip formatting, then convert +98/0098/98 to 0…"""
	phone = ''.join(str(value).translate(_DIGIT_TRANSLATION).split())
	phone = re.sub(r'[()\-]', '', phone)
	if phone.startswith('+98'):
		phone = '0' + phone[3:]
	elif phone.startswith('0098'):
		phone = '0' + phone[4:]
	elif phone.startswith('98') and len(phone) == 12:
		phone = '0' + phone[2:]
	return phone


def normalize_iranian_phone(value):
	phone = _to_national(value)
	if not re.fullmatch(r'09\d{9}', phone):
		raise ValueError('شمارهٔ همراه باید با قالب 09xxxxxxxxx وارد شود.')
	return phone


def normalize_gym_phone(value):
	"""Club contact numbers may be landlines (021…) as well as mobiles (09…)."""
	phone = _to_national(value)
	if not re.fullmatch(r'0\d{10}', phone):
		raise ValueError('شمارهٔ باشگاه باید ۱۱ رقم و با قالب 0xxxxxxxxx وارد شود.')
	return phone