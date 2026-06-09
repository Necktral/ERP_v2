"""Insumos contra inventario: enlaza InsumoApplication a un StockMovement real."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finca", "0002_seed_labors"),
    ]

    operations = [
        migrations.AddField(
            model_name="insumoapplication",
            name="source",
            field=models.CharField(
                choices=[("MANUAL", "Manual"), ("INVENTORY", "Inventario")],
                default="MANUAL",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="insumoapplication",
            name="inventory_item_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="insumoapplication",
            name="warehouse_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="insumoapplication",
            name="stock_movement_ref",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
