"""Triggers de imutabilidade de execuções terminais e bloqueio de exclusão."""

from django.db import migrations

CREATE_TRIGGERS = """
CREATE OR REPLACE FUNCTION catalog_importjob_terminal_immutable_fn()
RETURNS trigger AS $$
BEGIN
    IF OLD.status IN ('success', 'partial', 'failed', 'cancelled') THEN
        RAISE EXCEPTION 'Execução de importação terminal não pode ser alterada.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS catalog_importjob_terminal_immutable ON catalog_importjob;
CREATE TRIGGER catalog_importjob_terminal_immutable
BEFORE UPDATE ON catalog_importjob
FOR EACH ROW EXECUTE FUNCTION catalog_importjob_terminal_immutable_fn();

CREATE OR REPLACE FUNCTION catalog_importjob_no_delete_fn()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Execução de importação não pode ser removida.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS catalog_importjob_no_delete ON catalog_importjob;
CREATE TRIGGER catalog_importjob_no_delete
BEFORE DELETE ON catalog_importjob
FOR EACH ROW EXECUTE FUNCTION catalog_importjob_no_delete_fn();
"""

DROP_TRIGGERS = """
DROP TRIGGER IF EXISTS catalog_importjob_terminal_immutable ON catalog_importjob;
DROP TRIGGER IF EXISTS catalog_importjob_no_delete ON catalog_importjob;
DROP FUNCTION IF EXISTS catalog_importjob_terminal_immutable_fn();
DROP FUNCTION IF EXISTS catalog_importjob_no_delete_fn();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_seed_umamusume_global"),
    ]

    operations = [
        migrations.RunSQL(CREATE_TRIGGERS, DROP_TRIGGERS),
    ]
