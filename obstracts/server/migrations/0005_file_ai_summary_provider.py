# Generated by Django 5.0.8 on 2024-11-25 06:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('server', '0004_file_feed_file_profile_file_summary_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='ai_summary_provider',
            field=models.CharField(default=None, max_length=256, null=True),
        ),
    ]