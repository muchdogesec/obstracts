# Generated by Django 5.0.6 on 2024-08-07 12:53

import django.contrib.postgres.fields
import functools
import obstracts.server.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('server', '0005_alter_profile_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='aliases',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=256, validators=[functools.partial(obstracts.server.models.validate_extractor, *(['alias'],), **{})]), default=list, help_text='alias id(s)', size=None),
        ),
        migrations.AlterField(
            model_name='profile',
            name='extractions',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=256, validators=[functools.partial(obstracts.server.models.validate_extractor, *(['ai', 'pattern', 'lookup'],), **{})]), help_text='extraction id(s)', size=None),
        ),
        migrations.AlterField(
            model_name='profile',
            name='whitelists',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=256, validators=[functools.partial(obstracts.server.models.validate_extractor, *(['whitelist'],), **{})]), default=list, help_text='whitelist id(s)', size=None),
        ),
    ]
