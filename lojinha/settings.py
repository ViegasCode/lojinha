from pathlib import Path
import os

# __file__ may be missing in some environments (e.g., notebooks/sandboxes)
if '__file__' in globals():
    BASE_DIR = Path(__file__).resolve().parent.parent
else:
    cwd = Path().resolve()
    candidates = [cwd, *cwd.parents]
    base_guess = None
    for p in candidates:
        if (p / 'manage.py').exists() or (p.name == 'lojinha' and (p / 'lojinha').exists()):
            base_guess = p
            break
    BASE_DIR = base_guess or cwd

# Parcelamento (sem juros)
INSTALLMENTS_MAX = 6                 # máximo de parcelas
INSTALLMENTS_MIN_PER_CENTS = 1000    # parcela mínima em centavos (R$ 10,00)
# Token do Mercado Pago (use seu TEST/PROD)
MERCADO_PAGO_ACCESS_TOKEN = os.getenv("MERCADO_PAGO_ACCESS_TOKEN", "")

# Habilite MOCK para desenvolver sem token real
PAYMENTS_MOCK = os.getenv("PAYMENTS_MOCK", "").lower() in ("1", "true", "yes")

SECRET_KEY = "troque-por-uma-chave-segura"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "shop",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "lojinha.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ]},
    }
]
WSGI_APPLICATION = "lojinha.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

STATIC_URL = "static/"

TIME_ZONE = "America/Sao_Paulo"
USE_TZ = True

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@sualoja.com")

MERCADO_PAGO_ACCESS_TOKEN = os.getenv("MERCADO_PAGO_ACCESS_TOKEN", "")
MERCADO_PAGO_WEBHOOK_SECRET = os.getenv("MERCADO_PAGO_WEBHOOK_SECRET", "")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_URL = "/static/"
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static")
]



LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'painel:lista_produtos'
LOGOUT_REDIRECT_URL = '/'