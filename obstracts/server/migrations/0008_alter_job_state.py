# Generated by Django 5.0.9 on 2024-12-16 16:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('server', '0007_profile_ai_summary_provider'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='state',
            field=models.CharField(choices=[('retrieving', 'Retrieving'), ('in-queue', 'Queued'), ('processing', 'Processing'), ('processed', 'Processed'), ('processing_failed', 'Process Failed'), ('retrieve_failed', 'Retrieve Failed')], default='retrieving', max_length=20),
        ),
    ]