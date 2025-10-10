# NOVO ARQUIVO: shop/forms.py
from django import forms
from .models import Product, Category

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['title','slug', 'category', 'description', 'price_cents', 'image_url', 'stock', 'active', 'featured'] 

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'slug', 'featured']