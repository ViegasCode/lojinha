import json
import logging
import os

from django.conf import settings
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q
from django.http import (HttpResponse, HttpResponseBadRequest,
                         HttpResponseForbidden, JsonResponse)
from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .cart import (add as cart_add, clear as cart_clear, items as cart_items,
                   set_qty as cart_set_qty, total_cents as cart_total)
from .models import Category, Order, OrderItem, Product
from .services.payments import MercadoPago
from .utils import gen_otp, otp_expiry

from django.contrib.auth.decorators import login_required
from .forms import ProductForm, CategoryForm

log = logging.getLogger(__name__)


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

    print(f"--- Recebido: Categoria='{cat}', Ordenação='{sort}' ---")
    print(f"1. Contagem de produtos ANTES do filtro: {products.count()}")

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

    print(f"2. Contagem de produtos DEPOIS do filtro: {products.count()}")

    sort_map = {
        "created": "created_at",
        "-created": "-created_at",
        "price": "price_cents",
        "-price": "-price_cents",
        "pop": "-views",
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
        "categories": cats,
        "min_price": request.GET.get("min_price") or "",
        "max_price": request.GET.get("max_price") or "",
    }
    return render(request, "shop/catalog.html", ctx)


def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, active=True)
    Product.objects.filter(pk=product.pk).update(views=F("views") + 1)
    product.refresh_from_db(fields=["views"])
    return render(request, "shop/product_detail.html", {"product": product})


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
        return JsonResponse({"error": f"Falha no checkout: {e}"}, status=502)

    order.payment_provider_id = pref.get("id", "")
    order.save(update_fields=["payment_provider_id"])

    return JsonResponse({
        "order_id": order.id,
        "public_url": request.build_absolute_uri(f"/pedido/{order.public_token}/"),
        "short_code": order.short_code,
        "init_point": pref.get("init_point"),
    })


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
        return HttpResponse(status=200)

    info = MercadoPago.get_payment_info(str(data_id))
    status = (info.get("status") or "").lower()
    external_reference = info.get("external_reference")

    order = None
    if external_reference:
        try:
            order = Order.objects.get(pk=int(external_reference))
        except (Order.DoesNotExist, ValueError):
            order = None

    if order is None:
        order = Order.objects.filter(status="pending").order_by("-created_at").first()

    if not order:
        return HttpResponse(status=200)

    if status in ("approved", "accredited"):
        if order.status != "paid":
            with transaction.atomic():
                items = list(order.items.select_related("product").all())
                for it in items:
                    p = it.product
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
            order = Order.objects.get(customer_email__iexact=email, short_code__iexact=short)
        else:
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

    if timezone.now() > order.otp_expires_at:
        return HttpResponseBadRequest("código expirado")

    if str(otp) != order.otp_code:
        return HttpResponseForbidden("código incorreto")

    return JsonResponse({"public_url": request.build_absolute_uri(f"/pedido/{order.public_token}/")})


def order_status(request, public_token):
    """
    Página de status do pedido com resumo dos itens.
    """
    order = get_object_or_404(Order.objects.prefetch_related("items__product"), public_token=public_token)
    items = list(order.items.all())
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

@login_required
def lista_produtos_view(request):
    # Futuramente, você pode filtrar por request.user para mostrar apenas os produtos daquele vendedor
    produtos = Product.objects.all().order_by('-created_at') 
    return render(request, 'shop/painel/lista_produtos.html', {'products': produtos})

@login_required
def lista_produtos_view(request):
    produtos = Product.objects.all().order_by('-created_at') 
    return render(request, 'shop/painel/lista_produtos.html', {'products': produtos})

@login_required
def criar_produto_view(request):
    if request.method == 'POST':
        # Versão simplificada, sem commit=False e slugify
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            form.save() # Salva diretamente
            return redirect('painel:lista_produtos')
    else:
        form = ProductForm()
    
    return render(request, 'shop/painel/produto_form.html', {'form': form})

@login_required
def editar_produto_view(request, pk):
    produto = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        # Versão simplificada
        form = ProductForm(request.POST, request.FILES, instance=produto)
        if form.is_valid():
            form.save() # Salva diretamente
            return redirect('painel:lista_produtos')
    else:
        form = ProductForm(instance=produto)
        
    return render(request, 'shop/painel/produto_form.html', {'form': form, 'produto': produto})


@login_required
def lista_categorias_view(request):
    categorias = Category.objects.all().order_by('name')
    return render(request, 'shop/painel/lista_categorias.html', {'categories': categorias})

@login_required
def criar_categoria_view(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('painel:lista_categorias')
    else:
        form = CategoryForm()
    return render(request, 'shop/painel/categoria_form.html', {'form': form})

@login_required
def editar_categoria_view(request, pk):
    categoria = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            return redirect('painel:lista_categorias')
    else:
        form = CategoryForm(instance=categoria)
    return render(request, 'shop/painel/categoria_form.html', {'form': form, 'categoria': categoria})