# Generated migration to add missing UNIQUE constraint to rfid_uid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('households', '0015_floodpronearea'),
    ]

    operations = [
        migrations.AlterField(
            model_name='family',
            name='rfid_uid',
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
    ]
