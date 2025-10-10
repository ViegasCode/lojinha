# NOVO ARQUIVO: shop/painel_urls.py
from django.urls import path
from . import views

app_name = 'painel' # Namespace para o painel

urlpatterns = [
    path('', views.lista_produtos_view, name='lista_produtos'),
    path('produtos/novo/', views.criar_produto_view, name='criar_produto'),
    path('produtos/editar/<int:pk>/', views.editar_produto_view, name='editar_produto'),
    path('categorias/', views.lista_categorias_view, name='lista_categorias'),
    path('categorias/nova/', views.criar_categoria_view, name='criar_categoria'),
    path('categorias/editar/<int:pk>/', views.editar_categoria_view, name='editar_categoria'),
]