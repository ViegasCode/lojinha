import json
import logging
import os

from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse

from .models import Product, Order, OrderItem
from .utils import gen_otp, otp_expiry
from .services.payments import MercadoPago

log = logging.getLogger(__name__)

# ---------- CATÁLOGO ----------

from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from .models import Product, Order, OrderItem, Category
from .utils import gen_otp, otp_expiry
from .services.payments import MercadoPago
import json, logging, os
log = logging.getLogger(__name__)

from django.shortcuts import render, get_object_or_404
from .models import Product, Category
from django.core.paginator import Paginator
from django.db.models import Q, F

def catalog_view(request):
    """
    Catálogo com filtros:
      - q (busca)
      - cat (slug da categoria)
      - featured=1
      - min_price / max_price (em reais) -> convertemos para centavos
      - sort: -created|created|price|-price|pop (popularidade desc)
      - page
    """
    q = (request.GET.get("q") or "").strip()
    cat = (request.GET.get("cat") or "").strip()
    sort = (request.GET.get("sort") or "-created").strip()
    featured = request.GET.get("featured") == "1"

    # preços em REAIS (ex.: 19.90) -> centavos
    def to_cents(val):
        if not val:
            return None
        try:
            return int(round(float(str(val).replace(",", ".")) * 100))
        except Exception:
            return None

    min_cents = to_cents(request.GET.get("min_price"))
    max_cents = to_cents(request.GET.get("max_price"))

    products = Product.objects.filter(active=True)

    if q:
        products = products.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if cat:
        products = products.filter(category__slug=cat)
    if featured:
        products = products.filter(featured=True)
    if min_cents is not None:
        products = products.filter(price_cents__gte=min_cents)
    if max_cents is not None:
        products = products.filter(price_cents__lte=max_cents)

    sort_map = {
        "created": "created_at",
        "-created": "-created_at",
        "price": "price_cents",
        "-price": "-price_cents",
        "pop": "-views",  # 👈 popularidade (mais vistos primeiro)
    }
    products = products.order_by(sort_map.get(sort, "-created_at"))

    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    cats = Category.objects.all().order_by("name")

    ctx = {
        "products": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "sort": sort,
        "cat": cat,
        "featured_flag": featured,
        "cats": cats,
        "min_price": request.GET.get("min_price") or "",
        "max_price": request.GET.get("max_price") or "",
    }
    return render(request, "shop/catalog.html", ctx)

def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, active=True)
    # incrementa popularidade de forma atômica
    Product.objects.filter(pk=product.pk).update(views=F("views") + 1)
    product.refresh_from_db(fields=["views"])
    return render(request, "shop/product_detail.html", {"product": product})


# ---------- CHECKOUT ----------
@csrf_exempt
@require_http_methods(["POST"])
def create_checkout(request):
    """Cria Order + Preference no MP (ou mock) e retorna a URL do checkout."""
    try:
        payload = json.loads(request.body)
    except Exception:
        return HttpResponseBadRequest("JSON inválido")

    product_id = payload.get("product_id")
    qty = int(payload.get("qty", 1))
    email = payload.get("email", "")
    phone = payload.get("phone", "")

    product = get_object_or_404(Product, pk=product_id, active=True)

    # Valida estoque básico
    if product.stock is not None and qty > product.stock > 0:
        return HttpResponseBadRequest("Sem estoque suficiente")

    order = Order.objects.create(
        customer_email=email,
        customer_phone=phone,
        total_cents=product.price_cents * qty,
        payment_provider="mercadopago",
    )
    OrderItem.objects.create(order=order, product=product, qty=qty, unit_price_cents=product.price_cents)

    try:
        pref = MercadoPago.create_preference(
            title=product.title,
            quantity=qty,
            unit_price=product.price_cents / 100.0,
            external_reference=str(order.id),
            payer_email=email,
        )
    except Exception as e:
        # não derruba a app — devolve erro amigável ao front
        return JsonResponse({"error": f"Falha no checkout: {e}"}, status=502)

    order.payment_provider_id = pref.get("id", "")
    order.save(update_fields=["payment_provider_id"])

    return JsonResponse({
        "order_id": order.id,
        "public_url": request.build_absolute_uri(f"/pedido/{order.public_token}/"),
        "short_code": order.short_code,
        "init_point": pref.get("init_point"),
    })


# ---------- WEBHOOK MERCADO PAGO ----------

from django.db import transaction

@csrf_exempt
@require_http_methods(["POST"])
def mp_webhook(request):
    """Processa eventos do Mercado Pago. Espera `data.id` de payment."""
    try:
        event = json.loads(request.body)
    except Exception:
        return HttpResponseBadRequest("payload inválido")

    data_id = (event.get("data") or {}).get("id")
    if not data_id:
        return HttpResponse(status=200)  # nada a fazer / não é evento de payment

    info = MercadoPago.get_payment_info(str(data_id))
    status = (info.get("status") or "").lower()
    external_reference = info.get("external_reference")  # deve conter o Order.id

    order = None
    if external_reference:
        try:
            order = Order.objects.get(pk=int(external_reference))
        except (Order.DoesNotExist, ValueError):
            order = None

    # Fallback: se não achou por external_reference, tenta a última pendente
    if order is None:
        order = Order.objects.filter(status="pending").order_by("-created_at").first()

    if not order:
        return HttpResponse(status=200)

    # Idempotência simples: se já está pago e chegar repetido, apenas 200 OK
    if status in ("approved", "accredited"):
        if order.status != "paid":
            with transaction.atomic():
                # baixa estoque uma única vez
                items = list(order.items.select_related("product").all())
                for it in items:
                    p = it.product
                    # evita estoque negativo
                    new_stock = p.stock - it.qty
                    if new_stock < 0:
                        new_stock = 0
                    p.stock = new_stock
                    p.save(update_fields=["stock"])
                order.status = "paid"
                order.save(update_fields=["status"])
    elif status in ("cancelled", "rejected", "expired"):
        if order.status != "canceled":
            order.status = "canceled"
            order.save(update_fields=["status"])

    # Envia e-mail com link mágico
    if order.customer_email:
        try:
            send_mail(
                subject="Pedido atualizado",
                message=(
                    f"Seu pedido {order.short_code} está: {order.status}.\n"
                    f"Acompanhe: {request.build_absolute_uri(f'/pedido/{order.public_token}/')}"
                ),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[order.customer_email],
                fail_silently=True,
            )
        except Exception:
            pass

    return HttpResponse(status=200)

# ---------- LINK MÁGICO & CONSULTA ----------

@csrf_exempt
@require_http_methods(["POST"])
def orders_lookup(request):
    """Cliente envia email + short_code → sistema gera OTP e manda por e-mail."""
    try:
        payload = json.loads(request.body)
    except Exception:
        return HttpResponseBadRequest("JSON inválido")

    email = payload.get("email")
    short = payload.get("short_code")
    if not (email and short):
        return HttpResponseBadRequest("email e short_code são obrigatórios")

    try:
        order = Order.objects.get(customer_email__iexact=email, short_code__iexact=short)
    except Order.DoesNotExist:
        return HttpResponseBadRequest("pedido não encontrado")

    otp = gen_otp()
    order.otp_code = otp
    order.otp_expires_at = otp_expiry(10)
    order.save(update_fields=["otp_code", "otp_expires_at"])

    send_mail(
        subject="Seu código de verificação",
        message=f"Seu código é: {otp}. Ele expira em 10 minutos.",
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        recipient_list=[email],
        fail_silently=True,
    )

    return JsonResponse({"message": "OTP enviado"})

@csrf_exempt
@require_http_methods(["POST"])
def verify_otp(request):
    try:
        payload = json.loads(request.body)
    except Exception:
        return HttpResponseBadRequest("JSON inválido")

    email = payload.get("email")
    short = payload.get("short_code")
    otp = payload.get("otp")

    if not (email and short and otp):
        return HttpResponseBadRequest("campos obrigatórios faltando")

    try:
        order = Order.objects.get(customer_email__iexact=email, short_code__iexact=short)
    except Order.DoesNotExist:
        return HttpResponseBadRequest("pedido não encontrado")

    if not order.otp_code or not order.otp_expires_at:
        return HttpResponseBadRequest("solicite o código novamente")

    from django.utils import timezone
    if timezone.now() > order.otp_expires_at:
        return HttpResponseBadRequest("código expirado")

    if str(otp) != order.otp_code:
        return HttpResponseForbidden("código incorreto")

    return JsonResponse({"public_url": request.build_absolute_uri(f"/pedido/{order.public_token}/")})

# ---------- PÁGINAS SIMPLES ----------

from django.shortcuts import render, get_object_or_404
# ...imports já existentes...

def order_status(request, public_token):
    """
    Página de status do pedido com resumo dos itens.
    """
    order = get_object_or_404(Order.objects.prefetch_related("items__product"), public_token=public_token)
    items = list(order.items.all())
    # total_cents já é salvo no momento do checkout; mantemos como fonte de verdade.
    ctx = {
        "order": order,
        "items": items,
        "items_count": sum(it.qty for it in items),
    }
    return render(request, "shop/order_status.html", ctx)


def checkout_success(request):
    return render(request, "shop/checkout_success.html")

def order_lookup_page(request):
    """Página HTML para cliente buscar pedido via email + short_code + OTP."""
    return render(request, "shop/order_lookup.html")

# Substitua apenas a função orders_lookup por esta:

from django.db.models import Max

@csrf_exempt
@require_http_methods(["POST"])
def orders_lookup(request):
    """
    Cliente envia:
      - email + short_code  -> lookup específico
      - OU só email         -> pega o pedido MAIS RECENTE daquele email
    Em ambos os casos, envia um OTP para o e-mail para confirmar.
    """
    try:
        payload = json.loads(request.body)
    except Exception:
        return HttpResponseBadRequest("JSON inválido")

    email = (payload.get("email") or "").strip()
    short = (payload.get("short_code") or "").strip()

    if not email:
        return HttpResponseBadRequest("email é obrigatório")

    try:
        if short:
            # Caminho 1: lookup pelo par email + short_code
            order = Order.objects.get(customer_email__iexact=email, short_code__iexact=short)
        else:
            # Caminho 2: apenas email -> pega o pedido mais recente
            order = (
                Order.objects
                .filter(customer_email__iexact=email)
                .order_by("-created_at")
                .first()
            )
            if not order:
                return HttpResponseBadRequest("nenhum pedido encontrado para este e-mail")
    except Order.DoesNotExist:
        return HttpResponseBadRequest("pedido não encontrado")

    otp = gen_otp()
    order.otp_code = otp
    order.otp_expires_at = otp_expiry(10)
    order.save(update_fields=["otp_code", "otp_expires_at"])

    send_mail(
        subject="Seu código de verificação",
        message=f"Seu código é: {otp}. Ele expira em 10 minutos.",
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        recipient_list=[email],
        fail_silently=True,
    )

    return JsonResponse({"message": "OTP enviado"})
# ... imports já existentes ...
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import F
from .cart import items as cart_items, add as cart_add, set_qty as cart_set_qty, clear as cart_clear, total_cents as cart_total
from .models import Product, Order, OrderItem
from .services.payments import MercadoPago

# --------- CARRINHO (session) ---------

def cart_view(request):
    its = cart_items(request.session)
    total = cart_total(request.session)
    return render(request, "shop/cart.html", {"items": its, "total_cents": total})

@require_http_methods(["POST"])
def api_cart_add(request):
    try:
        data = json.loads(request.body or "{}")
    except Exception:
        return HttpResponseBadRequest("JSON inválido")
    pid = data.get("product_id")
    qty = int(data.get("qty", 1))
    if not pid:
        return HttpResponseBadRequest("product_id é obrigatório")
    # valida produto ativo
    get_object_or_404(Product, pk=pid, active=True)
    cart_add(request.session, int(pid), qty)
    return JsonResponse({"message": "ok"})

@require_http_methods(["POST"])
def api_cart_update(request):
    try:
        data = json.loads(request.body or "{}")
    except Exception:
        return HttpResponseBadRequest("JSON inválido")
    pid = data.get("product_id")
    qty = int(data.get("qty", 0))
    if not pid:
        return HttpResponseBadRequest("product_id é obrigatório")
    cart_set_qty(request.session, int(pid), qty)
    return JsonResponse({"message": "ok"})

@require_http_methods(["POST"])
def api_cart_clear(request):
    cart_clear(request.session)
    return JsonResponse({"message": "ok"})

@require_http_methods(["POST"])
@require_http_methods(["POST"])
def checkout_from_cart(request):
    try:
        data = json.loads(request.body or "{}")
    except Exception:
        return HttpResponseBadRequest("JSON inválido")

    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()

    cart = cart_items(request.session)
    if not cart:
        return HttpResponseBadRequest("carrinho vazio")

    for p, qty in cart:
        if p.stock is not None and qty > p.stock > 0:
            return HttpResponseBadRequest(f"sem estoque suficiente para {p.title}")

    order_total = sum(p.price_cents * qty for p, qty in cart)
    order = Order.objects.create(
        customer_email=email,
        customer_phone=phone,
        total_cents=order_total,
        payment_provider="mercadopago",
    )
    for p, qty in cart:
        OrderItem.objects.create(order=order, product=p, qty=qty, unit_price_cents=p.price_cents)

    distinct = len(cart)
    title = f"Pedido ({distinct} item{'s' if distinct != 1 else ''})"

    try:
        pref = MercadoPago.create_preference(
            title=title,
            quantity=1,
            unit_price=order_total / 100.0,
            external_reference=str(order.id),
            payer_email=email,
        )
    except Exception as e:
        return JsonResponse({"error": f"Falha no checkout: {e}"}, status=502)

    order.payment_provider_id = pref.get("id", "")
    order.save(update_fields=["payment_provider_id"])
    cart_clear(request.session)

    return JsonResponse({
        "order_id": order.id,
        "public_url": request.build_absolute_uri(f"/pedido/{order.public_token}/"),
        "short_code": order.short_code,
        "init_point": pref.get("init_point"),
    })

