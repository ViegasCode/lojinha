from django.db import models
from django.urls import reverse
from .utils import gen_public_token, gen_short_code

class Category(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    featured = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

class Product(models.Model):
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180, unique=True)
    description = models.TextField(blank=True)
    price_cents = models.PositiveIntegerField()
    stock = models.PositiveIntegerField(default=0)
    image_url = models.URLField(blank=True)
    category = models.ForeignKey("Category", null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    views = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def price(self):
        # Retorna o valor em reais, e não em centavos
        return self.price_cents / 100.0

    def __str__(self):
        return self.title

    @property
    def price(self):
        return self.price_cents / 100

 
    def get_absolute_url(self):
        """Retorna a URL completa para a página de detalhe de um produto."""
        return reverse('shop:product_detail', kwargs={'slug': self.slug})


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pendente"),
        ("paid", "Pago"),
        ("canceled", "Cancelado"),
    ]
    public_token = models.CharField(max_length=48, unique=True, default=gen_public_token)
    short_code = models.CharField(max_length=10, db_index=True, default=gen_short_code)

    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    total_cents = models.PositiveIntegerField(default=0)

    payment_provider = models.CharField(max_length=40, blank=True)
    payment_provider_id = models.CharField(max_length=120, blank=True)

    otp_code = models.CharField(max_length=10, blank=True)
    otp_expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.id} ({self.status})"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    qty = models.PositiveIntegerField(default=1)
    unit_price_cents = models.PositiveIntegerField()

    def line_total_cents(self):
        return self.qty * self.unit_price_cents