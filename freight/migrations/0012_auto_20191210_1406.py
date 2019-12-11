# Generated by Django 2.2.8 on 2019-12-10 14:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('freight', '0011_contractcustomernotification'),
    ]

    operations = [
        migrations.AddField(
            model_name='contracthandler',
            name='price_per_volume_modifier',
            field=models.FloatField(blank=True, default=None, help_text='global modifier for price per volume in percent, e.g. 2.5 = +2.5%', null=True),
        ),
        migrations.AddField(
            model_name='pricing',
            name='use_price_per_volume_modifier',
            field=models.BooleanField(default=False, help_text='Whether the global price per volume modifier is used'),
        ),
    ]