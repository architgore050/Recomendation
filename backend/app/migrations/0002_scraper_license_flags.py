from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='audioclip',
            name='is_noncommercial',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='audioclip',
            name='requires_share_alike',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='audioclip',
            name='license_family',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        # SECURITY: Index supports fast feed exclusion of NC + SA items.
        migrations.AddIndex(
            model_name='audioclip',
            index=models.Index(
                fields=['is_noncommercial', '-created_at'],
                name='audioclip_nc_created_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='audioclip',
            index=models.Index(
                fields=['requires_share_alike', '-created_at'],
                name='audioclip_sa_created_idx',
            ),
        ),
    ]