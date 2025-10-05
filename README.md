# Lojinha — Checkout + Catálogo (Django) com Link Mágico/OTP

## Como rodar local (PyCharm ou terminal)
1. Crie um virtualenv e instale dependências:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Crie o projeto Django:
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```
3. Acesse http://127.0.0.1:8000/

## Mercado Pago
Configure a variável `MERCADO_PAGO_ACCESS_TOKEN` no ambiente para criar preferences de checkout.
