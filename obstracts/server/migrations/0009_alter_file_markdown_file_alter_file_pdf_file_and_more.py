# Generated by Django 5.2.1 on 2025-07-24 12:31

import obstracts.server.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('obstracts', '0008_file_pdf_file'),
    ]

    operations = [
        migrations.AlterField(
            model_name='file',
            name='markdown_file',
            field=models.FileField(max_length=1024, null=True, upload_to=obstracts.server.models.upload_to_func),
        ),
        migrations.AlterField(
            model_name='file',
            name='pdf_file',
            field=models.FileField(max_length=1024, null=True, upload_to=obstracts.server.models.upload_to_func),
        ),
        migrations.AlterField(
            model_name='fileimage',
            name='file',
            field=models.ImageField(max_length=1024, upload_to=obstracts.server.models.upload_to_func),
        ),
    ]
