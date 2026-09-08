"""Add the single missing column: app_audioclip.cover_image.

The AudioClip model has `cover_image` (ImageField) but 0001_initial.py
never created the column. Other fields were added in subsequent
commits/migrations outside of Django's tracking. Adding just the
missing one keeps this migration minimal and focused.

The uploader hits this when scraper imports fail with:
    column "cover_image" of relation "app_audioclip" does not exist
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0003_audioclip_segments'),
    ]

    operations = [
        migrations.AddField(
            model_name='audioclip',
            name='cover_image',
            field=models.ImageField(blank=True, null=True,
                                    upload_to='covers/%Y/%m/%d/'),
        ),
    ]
