"""Cria a fonte externa ``umamusume-global`` de forma idempotente."""

from django.db import migrations

SOURCE_NAME = "umamusume-global"
DEFAULT_LICENSE = "Imagens © Cygames, Inc. Uso interno; revisar autorização antes de publicar."
DEFAULT_BASE_URL = "https://umamusume.com/characters/"


def seed_umamusume_global(apps, schema_editor):
    catalog_source = apps.get_model("catalog", "CatalogSource")
    source, created = catalog_source.objects.get_or_create(
        name=SOURCE_NAME,
        defaults={
            "kind": "api",
            "base_url": DEFAULT_BASE_URL,
            "license_note": DEFAULT_LICENSE,
            "enabled": True,
            "adapter": SOURCE_NAME,
        },
    )
    if created:
        return

    # Preserva valores já revisados manualmente; preenche apenas o que estiver vazio.
    update_fields = []
    if not source.adapter:
        source.adapter = SOURCE_NAME
        update_fields.append("adapter")
    if not source.kind:
        source.kind = "api"
        update_fields.append("kind")
    if not source.base_url:
        source.base_url = DEFAULT_BASE_URL
        update_fields.append("base_url")
    if not source.license_note.strip():
        source.license_note = DEFAULT_LICENSE
        update_fields.append("license_note")
    if update_fields:
        source.save(update_fields=update_fields)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0004_catalogsource_adapter_importjob"),
    ]

    operations = [
        migrations.RunPython(seed_umamusume_global, migrations.RunPython.noop),
    ]
