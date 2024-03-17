# Generated by Django 5.0.3 on 2024-03-17 14:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('backup', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='backupprofile',
            name='weekly_day',
            field=models.CharField(choices=[('monday', 'Monday'), ('tuesday', 'Tuesday'), ('wednesday', 'Wednesday'), ('thursday', 'Thursday'), ('friday', 'Friday'), ('saturday', 'Saturday'), ('sunday', 'Sunday')], default='sunday', max_length=10),
        ),
    ]
