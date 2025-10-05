from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0002_catalog_models"),  # ajuste se o seu número anterior for diferente
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="views",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
