# Generated by Django 2.2.5 on 2019-10-04 22:37

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('freight', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='freight',
            options={'default_permissions': (), 'managed': False, 'permissions': (('basic_access', 'Can access this app'), ('setup_contracts_handler', 'Can setup contracts handler'), ('use_calculator', 'Can use the calculator'), ('view_contracts', 'Can view the contracts list'), ('add_location', 'Can add / update locations'), ('view_statistics', 'Can view freight statistics'))},
        ),
    ]
