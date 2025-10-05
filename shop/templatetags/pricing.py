from django import template
from django.conf import settings

register = template.Library()

def _plans(price_cents: int, max_inst: int, min_per: int):
    """
    Gera planos 1..max_inst respeitando parcela mínima, mas
    GARANTE que 1x SEMPRE aparece (mesmo que price < min_per).
    """
    out = []
    # sempre inclui 1x
    out.append((1, float(price_cents)))

    # do 2..N respeitando parcela mínima
    for n in range(2, max_inst + 1):
        per = price_cents / n
        if per >= min_per:
            out.append((n, per))
    return out

@register.filter
def money(cents):
    """
    Formata centavos em BRL (R$ 12,34).
    Aceita int/float/str com número.
    """
    try:
        val = float(cents) / 100.0
    except Exception:
        return "R$ 0,00"
    return ("R$ %.2f" % val).replace(".", ",")

@register.simple_tag
def best_installment(price_cents):
    """
    Retorna o melhor plano (maior número de parcelas possível).
    Exemplo de retorno:
      {"n": 3, "per_cents": 1233}
    """
    try:
        price = int(price_cents)
    except Exception:
        return None

    max_inst = int(getattr(settings, "INSTALLMENTS_MAX", 6))
    min_per = int(getattr(settings, "INSTALLMENTS_MIN_PER_CENTS", 1000))

    plans = _plans(price, max_inst, min_per)
    if not plans:
        return {"n": 1, "per_cents": price}  # fallback de segurança

    n, per = plans[-1]  # maior n válido
    return {"n": int(n), "per_cents": int(round(per))}

@register.simple_tag
def installment_plans(price_cents):
    """
    Retorna todos os planos válidos (incluindo 1x) em ordem crescente.
    Cada item: {"n": N, "per_cents": ...}
    """
    try:
        price = int(price_cents)
    except Exception:
        return [{"n": 1, "per_cents": 0}]

    max_inst = int(getattr(settings, "INSTALLMENTS_MAX", 6))
    min_per = int(getattr(settings, "INSTALLMENTS_MIN_PER_CENTS", 1000))

    plans = _plans(price, max_inst, min_per)
    return [{"n": int(n), "per_cents": int(round(per))} for (n, per) in plans]
