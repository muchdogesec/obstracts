# Generated by Django 5.0.10 on 2025-02-06 06:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('server', '0009_profile_ignore_extraction_boundary'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='ignore_embedded_relationships',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='profile',
            name='ignore_embedded_relationships_smo',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='ignore_embedded_relationships_sro',
            field=models.BooleanField(default=True),
        ),
    ]
