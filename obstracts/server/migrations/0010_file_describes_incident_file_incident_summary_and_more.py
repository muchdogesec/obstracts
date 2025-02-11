# Generated by Django 5.0.10 on 2025-02-07 06:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('server', '0009_profile_ignore_extraction_boundary'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='describes_incident',
            field=models.BooleanField(default=None, null=True),
        ),
        migrations.AddField(
            model_name='file',
            name='incident_summary',
            field=models.CharField(default=None, max_length=65535, null=True),
        ),
        migrations.AddField(
            model_name='job',
            name='ai_content_check_variable',
            field=models.CharField(default=None, null=True),
        ),
    ]
