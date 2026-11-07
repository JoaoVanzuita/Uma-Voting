"""Dados iniciais: aptidões canônicas e fonte de curadoria local."""

from django.db import migrations

APTITUDES = [
    ("strategy", "front", "Front"),
    ("strategy", "pace", "Pace"),
    ("strategy", "late", "Late"),
    ("strategy", "end", "End"),
    ("distance", "sprint", "Sprint"),
    ("distance", "mile", "Mile"),
    ("distance", "medium", "Medium"),
    ("distance", "long", "Long"),
    ("surface", "turf", "Turf"),
    ("surface", "dirt", "Dirt"),
]

LOCAL_SOURCE_NAME = "curadoria-local"


def seed_lookups(apps, schema_editor):
    Aptitude = apps.get_model("catalog", "Aptitude")
    CatalogSource = apps.get_model("catalog", "CatalogSource")

    for category, value, label in APTITUDES:
        Aptitude.objects.update_or_create(
            category=category,
            value=value,
            defaults={"label": label},
        )

    CatalogSource.objects.update_or_create(
        name=LOCAL_SOURCE_NAME,
        defaults={
            "kind": "file",
            "license_note": (
                "Acervo curado localmente pelo projeto; origem e licença revisadas "
                "manualmente antes de cada importação."
            ),
            "enabled": True,
        },
    )


def remove_lookups(apps, schema_editor):
    Aptitude = apps.get_model("catalog", "Aptitude")
    CatalogSource = apps.get_model("catalog", "CatalogSource")

    for category, value, _label in APTITUDES:
        Aptitude.objects.filter(category=category, value=value).delete()

    CatalogSource.objects.filter(name=LOCAL_SOURCE_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_lookups, remove_lookups),
    ]
