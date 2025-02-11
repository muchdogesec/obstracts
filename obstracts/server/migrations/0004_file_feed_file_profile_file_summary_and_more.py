# Generated by Django 5.0.8 on 2024-11-19 09:59

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('server', '0003_remove_profile_aliases_remove_profile_whitelists'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='feed',
            field=models.ForeignKey(default=None, null=True, on_delete=django.db.models.deletion.CASCADE, to='server.feedprofile'),
        ),
        migrations.AddField(
            model_name='file',
            name='profile',
            field=models.ForeignKey(default=None, null=True, on_delete=django.db.models.deletion.PROTECT, to='server.profile'),
        ),
        migrations.AddField(
            model_name='file',
            name='summary',
            field=models.CharField(max_length=65535, null=True),
        ),
        migrations.AlterField(
            model_name='feedprofile',
            name='profile',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='server.profile'),
        ),
    ]
