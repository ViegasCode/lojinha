from django.test import TestCase
from django.conf import settings
from django.utils import timezone
from django.urls import reverse

from shop.utils import gen_public_token, gen_short_code, gen_otp, otp_expiry
from shop.models import Order, Product

class SettingsTest(TestCase):
    def test_base_dir_defined(self):
        # BASE_DIR deve existir e ser um Path
        self.assertTrue(hasattr(settings, 'BASE_DIR'))

        # Em vez de fixar o nome da pasta, vamos só garantir que existe manage.py lá dentro
        manage_py = settings.BASE_DIR / "manage.py"
        self.assertTrue(manage_py.exists(), f"manage.py não encontrado em {settings.BASE_DIR}")


class UtilsTest(TestCase):
    def test_public_token_length_and_uniqueness(self):
        tokens = {gen_public_token() for _ in range(100)}
        self.assertEqual(len(tokens), 100)
        self.assertTrue(all(20 <= len(t) <= 40 for t in tokens))

    def test_short_code_length(self):
        code = gen_short_code()
        self.assertEqual(len(code), 8)

    def test_otp_and_expiry(self):
        otp = gen_otp()
        self.assertEqual(len(otp), 6)
        exp = otp_expiry(1)
        self.assertGreater(exp, timezone.now())

class OrderModelTest(TestCase):
    def test_order_defaults(self):
        o = Order.objects.create()
        self.assertEqual(o.status, 'pending')
        self.assertTrue(o.public_token)
        self.assertTrue(o.short_code)

class ViewSmokeTest(TestCase):
    def test_catalog_renders(self):
        resp = self.client.get(reverse('catalog'))
        self.assertEqual(resp.status_code, 200)

    def test_product_detail_renders(self):
        p = Product.objects.create(title='Teste', slug='teste', price_cents=1000, stock=10, active=True)
        resp = self.client.get(reverse('product_detail', args=[p.slug]))
        self.assertEqual(resp.status_code, 200)

    def test_create_checkout_bad_json(self):
        resp = self.client.post(reverse('create_checkout'), data='not-json', content_type='text/plain')
        self.assertEqual(resp.status_code, 400)
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch
from shop.models import Product, Order, OrderItem

class WebhookStockTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.p = Product.objects.create(
            title="Produto X", slug="produto-x", price_cents=1000, stock=5, active=True
        )
        self.order = Order.objects.create(customer_email="test@example.com", total_cents=2000)
        OrderItem.objects.create(order=self.order, product=self.p, qty=2, unit_price_cents=1000)

    @patch("shop.services.payments.MercadoPago.get_payment_info")
    def test_webhook_approved_decrements_stock_once(self, mock_info):
        mock_info.return_value = {"status": "approved", "external_reference": str(self.order.id), "id": "pay_123"}

        # 1ª chamada (baixa estoque)
        resp1 = self.client.post(
            reverse("mp_webhook"),
            data='{"data":{"id":"pay_123"}}',
            content_type="application/json",
        )
        self.assertEqual(resp1.status_code, 200)
        self.p.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        self.assertEqual(self.p.stock, 3)  # 5 - 2

        # 2ª chamada (idempotente, não baixa de novo)
        resp2 = self.client.post(
            reverse("mp_webhook"),
            data='{"data":{"id":"pay_123"}}',
            content_type="application/json",
        )
        self.assertEqual(resp2.status_code, 200)
        self.p.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        self.assertEqual(self.p.stock, 3)  # permanece 3

    @patch("shop.services.payments.MercadoPago.get_payment_info")
    def test_webhook_rejected_sets_canceled(self, mock_info):
        mock_info.return_value = {"status": "rejected", "external_reference": str(self.order.id), "id": "pay_999"}
        resp = self.client.post(
            reverse("mp_webhook"),
            data='{"data":{"id":"pay_999"}}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "canceled")
from django.test import TestCase
from django.conf import settings
from shop.templatetags import pricing

class InstallmentsTest(TestCase):
    def test_best_installment_respects_min_per(self):
        # Com parcela mínima de R$10,00 e valor R$ 25,00 => melhor é 2x (12,50)
        with self.settings(INSTALLMENTS_MAX=6, INSTALLMENTS_MIN_PER_CENTS=1000):
            inst = pricing.best_installment(2500)
            self.assertIsNotNone(inst)
            self.assertEqual(inst["n"], 2)
            self.assertEqual(inst["per_cents"], 1250)

    def test_installment_plans_full_list(self):
        with self.settings(INSTALLMENTS_MAX=4, INSTALLMENTS_MIN_PER_CENTS=1000):
            plans = pricing.installment_plans(5000)  # R$ 50
            # 1x (50), 2x (25), 3x (16,67), 4x (12,5) => todos >= 10
            ns = [p["n"] for p in plans]
            self.assertEqual(ns, [1,2,3,4])
            self.assertEqual(plans[-1]["per_cents"], 1250)  # 4x de 12,50

    def test_no_plan_below_min(self):
        # R$ 15 com min R$ 10 => 2x seria 7,5 (descarta), então só 1x
        with self.settings(INSTALLMENTS_MAX=6, INSTALLMENTS_MIN_PER_CENTS=1000):
            plans = pricing.installment_plans(1500)
            self.assertEqual([p["n"] for p in plans], [1])

from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch
from shop.models import Product, Order, OrderItem

class CartFlowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.p1 = Product.objects.create(title="A", slug="a", price_cents=1000, stock=5, active=True)
        self.p2 = Product.objects.create(title="B", slug="b", price_cents=2500, stock=3, active=True)

    def test_add_and_update_cart(self):
        # add p1 x2
        r = self.client.post(reverse("api_cart_add"), data='{"product_id": %d, "qty": 2}' % self.p1.id, content_type="application/json")
        self.assertEqual(r.status_code, 200)
        # update p1 -> 3
        r = self.client.post(reverse("api_cart_update"), data='{"product_id": %d, "qty": 3}' % self.p1.id, content_type="application/json")
        self.assertEqual(r.status_code, 200)

    @patch("shop.services.payments.MercadoPago.create_preference")
    def test_checkout_from_cart_creates_order(self, mock_pref):
        mock_pref.return_value = {"id": "pref_1", "init_point": "http://pay.example/123"}
        # add p1 x2 and p2 x1
        self.client.post(reverse("api_cart_add"), data='{"product_id": %d, "qty": 2}' % self.p1.id, content_type="application/json")
        self.client.post(reverse("api_cart_add"), data='{"product_id": %d, "qty": 1}' % self.p2.id, content_type="application/json")
        # checkout
        r = self.client.post(reverse("checkout_from_cart"), data='{"email":"x@test.com"}', content_type="application/json")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("order_id", data)
        self.assertIn("init_point", data)
        o = Order.objects.get(id=data["order_id"])
        self.assertEqual(o.total_cents, 2*1000 + 1*2500)
        self.assertEqual(o.items.count(), 2)
