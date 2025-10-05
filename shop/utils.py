import os
import hmac
import base64
import random
import string
from hashlib import sha256
from datetime import timedelta
from django.utils import timezone

_SECRET = os.getenv("PUBLIC_TOKEN_SECRET", "change-me")

def gen_public_token() -> str:
    msg = f"{timezone.now().timestamp()}:{random.random()}".encode()
    dig = hmac.new(_SECRET.encode(), msg, sha256).digest()
    return base64.urlsafe_b64encode(dig).decode().strip("=")[:40]

def gen_short_code(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))

def gen_otp(n: int = 6) -> str:
    return "".join(random.choices(string.digits, k=n))

def otp_expiry(minutes: int = 10):
    return timezone.now() + timedelta(minutes=minutes)
