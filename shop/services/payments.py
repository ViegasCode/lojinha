import os
import json
import requests
from django.conf import settings

MP_BASE = "https://api.mercadopago.com"

class PaymentError(Exception):
    pass

def _get_mp_token() -> str:
    # Prioriza settings; cai para variável de ambiente por compatibilidade
    token = getattr(settings, "MERCADO_PAGO_ACCESS_TOKEN", "") or os.getenv("MERCADO_PAGO_ACCESS_TOKEN", "")
    return token.strip()

def _mock_enabled() -> bool:
    # Ativa mock explicitamente via settings, ou automaticamente se não houver token
    return bool(getattr(settings, "PAYMENTS_MOCK", False)) or not _get_mp_token()

class MercadoPago:
    @staticmethod
    def create_preference(title: str, quantity: int, unit_price: float, external_reference: str, payer_email: str = ""):
        """
        Cria a preference e retorna {id, init_point, sandbox_init_point}.
        Se PAYMENTS_MOCK=True ou não houver token, retorna um checkout fictício.
        """
        if _mock_enabled():
            return {
                "id": "mock_pref_123",
                "init_point": f"https://example.com/mock-checkout?ref={external_reference}",
                "sandbox_init_point": f"https://example.com/mock-checkout?ref={external_reference}&env=sandbox",
            }

        token = _get_mp_token()
        if not token:
            raise PaymentError("MERCADO_PAGO_ACCESS_TOKEN ausente.")

        url = f"{MP_BASE}/checkout/preferences"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "items": [{
                "title": title,
                "quantity": quantity,
                "currency_id": "BRL",
                "unit_price": round(unit_price, 2)
            }],
            "payer": {"email": payer_email} if payer_email else {},
            "external_reference": external_reference,
            "back_urls": {
                "success": "http://localhost:8000/checkout/sucesso",
                "failure": "http://localhost:8000/checkout/falha",
                "pending": "http://localhost:8000/checkout/pendente",
            },
            "auto_return": "approved"
        }
        try:
            r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)
            # Se retornar erro, levanta exceção com detalhe curto
            try:
                r.raise_for_status()
            except requests.HTTPError as e:
                body = ""
                try:
                    body = r.json()
                except Exception:
                    body = (r.text or "")[:400]
                raise PaymentError(f"MercadoPago  {r.status_code}: {body}") from e
            data = r.json()
            return {
                "id": data.get("id"),
                "init_point": data.get("init_point"),
                "sandbox_init_point": data.get("sandbox_init_point"),
            }
        except requests.RequestException as e:
            raise PaymentError(f"Erro de rede ao acessar MercadoPago: {e}") from e

    @staticmethod
    def get_payment_info(payment_id: str):
        """
        Retorna {status, external_reference, id}.
        No modo mock, simula 'approved'.
        """
        if _mock_enabled():
            return {"status": "approved", "external_reference": "1", "id": payment_id}

        token = _get_mp_token()
        if not token:
            raise PaymentError("MERCADO_PAGO_ACCESS_TOKEN ausente.")

        url = f"{MP_BASE}/v1/payments/{payment_id}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            r = requests.get(url, headers=headers, timeout=20)
            try:
                r.raise_for_status()
            except requests.HTTPError as e:
                body = ""
                try:
                    body = r.json()
                except Exception:
                    body = (r.text or "")[:400]
                raise PaymentError(f"MercadoPago  {r.status_code}: {body}") from e
            data = r.json()
            return {
                "status": data.get("status"),
                "external_reference": data.get("external_reference"),
                "id": data.get("id"),
            }
        except requests.RequestException as e:
            raise PaymentError(f"Erro de rede ao acessar MercadoPago: {e}") from e
