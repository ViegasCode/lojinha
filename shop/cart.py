from typing import Dict, Tuple, List
from .models import Product

CART_KEY = "cart_v1"

def _get(session) -> Dict[str, int]:
    return session.get(CART_KEY, {}) or {}

def _save(session, cart: Dict[str, int]):
    session[CART_KEY] = cart
    session.modified = True

def add(session, product_id: int, qty: int = 1):
    cart = _get(session)
    pid = str(int(product_id))
    cart[pid] = max(1, cart.get(pid, 0) + int(qty))
    _save(session, cart)

def set_qty(session, product_id: int, qty: int):
    cart = _get(session)
    pid = str(int(product_id))
    qty = int(qty)
    if qty <= 0:
        cart.pop(pid, None)
    else:
        cart[pid] = qty
    _save(session, cart)

def clear(session):
    _save(session, {})

def items(session) -> List[Tuple[Product, int]]:
    cart = _get(session)
    pids = [int(pid) for pid in cart.keys()]
    if not pids:
        return []
    products = {p.id: p for p in Product.objects.filter(id__in=pids, active=True)}
    out = []
    for pid, qty in cart.items():
        p = products.get(int(pid))
        if p:
            out.append((p, int(qty)))
    return out

def total_cents(session) -> int:
    return sum(p.price_cents * qty for p, qty in items(session))
