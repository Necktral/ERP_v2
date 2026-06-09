from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounting", "0013_operationalpostingconfig_enable_nomina"),
    ]

    operations = [
        migrations.AddField(
            model_name="fiscalperiod",
            name="reopened_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="fiscalperiod",
            name="reopened_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="acc_periods_reopened",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="fiscalperiod",
            name="reopen_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
