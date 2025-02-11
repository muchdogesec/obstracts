# Generated by Django 5.0.8 on 2024-11-25 11:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('server', '0005_file_ai_summary_provider'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='file',
            name='ai_summary_provider',
        ),
        migrations.AddField(
            model_name='profile',
            name='ignore_image_refs',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='ignore_link_refs',
            field=models.BooleanField(default=True),
        ),
    ]
