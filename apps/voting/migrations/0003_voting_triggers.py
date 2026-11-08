"""Triggers PostgreSQL de ciclo de vida, configuração e snapshots."""

from django.db import migrations

FORWARD_SQL = """
CREATE OR REPLACE FUNCTION voting_transition() RETURNS trigger AS $$
BEGIN
    IF OLD.status = NEW.status THEN
        RETURN NEW;
    END IF;

    IF (OLD.status = 'draft' AND NEW.status IN ('scheduled', 'open', 'cancelled'))
       OR (OLD.status = 'scheduled' AND NEW.status IN ('open', 'cancelled'))
       OR (OLD.status = 'open' AND NEW.status IN ('closed', 'cancelled'))
       OR (OLD.status = 'closed' AND NEW.status = 'cancelled') THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'Transição de votação não permitida: % -> %.', OLD.status, NEW.status
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION voting_config_immutable() RETURNS trigger AS $$
BEGIN
    IF OLD.status <> 'draft' THEN
        IF NEW.title IS DISTINCT FROM OLD.title
           OR NEW.description IS DISTINCT FROM OLD.description
           OR NEW.choices_count IS DISTINCT FROM OLD.choices_count
           OR NEW.catalog_cutoff_date IS DISTINCT FROM OLD.catalog_cutoff_date
           OR NEW.opens_at IS DISTINCT FROM OLD.opens_at
           OR NEW.closes_at IS DISTINCT FROM OLD.closes_at
           OR NEW.open_mode IS DISTINCT FROM OLD.open_mode
           OR NEW.close_mode IS DISTINCT FROM OLD.close_mode
           OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id THEN
            RAISE EXCEPTION 'A configuração da votação é imutável após o rascunho.'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION voting_eligibility_draft_only() RETURNS trigger AS $$
DECLARE
    v_status varchar(12);
    v_voting_id bigint;
BEGIN
    -- Escape hatch usado apenas por factories de teste; nunca pela aplicação.
    IF current_setting('app.fixture_seed', true) = 'on' THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;

    v_voting_id := COALESCE(NEW.voting_id, OLD.voting_id);
    SELECT status INTO v_status FROM voting_voting WHERE id = v_voting_id;

    IF v_status IS DISTINCT FROM 'draft' THEN
        RAISE EXCEPTION 'Elegíveis só podem ser alterados com votação em rascunho.'
            USING ERRCODE = '23514';
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION voting_snapshot_no_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Snapshots de votação são imutáveis.'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION voting_snapshot_no_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Snapshots de votação não podem ser apagados.'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION voting_snapshot_insert_window() RETURNS trigger AS $$
DECLARE
    v_status varchar(12);
BEGIN
    IF current_setting('app.fixture_seed', true) = 'on' THEN
        RETURN NEW;
    END IF;

    IF TG_TABLE_NAME = 'voting_votingcharactersnapshot' THEN
        SELECT status INTO v_status
          FROM voting_voting
         WHERE id = NEW.voting_id;
    ELSIF TG_TABLE_NAME = 'voting_votingversionsnapshot' THEN
        SELECT v.status INTO v_status
          FROM voting_voting v
          JOIN voting_votingcharactersnapshot s ON s.voting_id = v.id
         WHERE s.id = NEW.character_snapshot_id;
    ELSE
        SELECT v.status INTO v_status
          FROM voting_voting v
          JOIN voting_votingcharactersnapshot s ON s.voting_id = v.id
          JOIN voting_votingversionsnapshot vs ON vs.character_snapshot_id = s.id
         WHERE vs.id = NEW.version_snapshot_id;
    END IF;

    IF v_status IS DISTINCT FROM 'draft' AND v_status IS DISTINCT FROM 'scheduled' THEN
        RAISE EXCEPTION 'Snapshots só podem ser criados durante a abertura da votação.'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION voting_snapshot_image_character() RETURNS trigger AS $$
BEGIN
    IF NEW.image_asset_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
          FROM catalog_imageasset
         WHERE id = NEW.image_asset_id
           AND character_id = NEW.source_character_id
    ) THEN
        RAISE EXCEPTION 'A imagem do snapshot deve pertencer à personagem.'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION voting_snapshot_version_character() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM catalog_characterversion cv
          JOIN voting_votingcharactersnapshot s ON s.id = NEW.character_snapshot_id
         WHERE cv.id = NEW.source_version_id
           AND cv.character_id = s.source_character_id
    ) THEN
        RAISE EXCEPTION 'A versão do snapshot deve pertencer à personagem.'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER voting_transition
    BEFORE UPDATE ON voting_voting
    FOR EACH ROW EXECUTE FUNCTION voting_transition();

CREATE TRIGGER voting_config_immutable
    BEFORE UPDATE ON voting_voting
    FOR EACH ROW EXECUTE FUNCTION voting_config_immutable();

CREATE TRIGGER eligibility_draft_only
    BEFORE INSERT OR UPDATE OR DELETE ON voting_votingeligibility
    FOR EACH ROW EXECUTE FUNCTION voting_eligibility_draft_only();

CREATE TRIGGER snapshot_no_update
    BEFORE UPDATE ON voting_votingcharactersnapshot
    FOR EACH ROW EXECUTE FUNCTION voting_snapshot_no_update();

CREATE TRIGGER snapshot_no_update
    BEFORE UPDATE ON voting_votingversionsnapshot
    FOR EACH ROW EXECUTE FUNCTION voting_snapshot_no_update();

CREATE TRIGGER snapshot_no_update
    BEFORE UPDATE ON voting_votingversionaptitudesnapshot
    FOR EACH ROW EXECUTE FUNCTION voting_snapshot_no_update();

CREATE TRIGGER snapshot_no_delete
    BEFORE DELETE ON voting_votingcharactersnapshot
    FOR EACH ROW EXECUTE FUNCTION voting_snapshot_no_delete();

CREATE TRIGGER snapshot_no_delete
    BEFORE DELETE ON voting_votingversionsnapshot
    FOR EACH ROW EXECUTE FUNCTION voting_snapshot_no_delete();

CREATE TRIGGER snapshot_no_delete
    BEFORE DELETE ON voting_votingversionaptitudesnapshot
    FOR EACH ROW EXECUTE FUNCTION voting_snapshot_no_delete();

CREATE TRIGGER snapshot_insert_window
    BEFORE INSERT ON voting_votingcharactersnapshot
    FOR EACH ROW EXECUTE FUNCTION voting_snapshot_insert_window();

CREATE TRIGGER snapshot_insert_window
    BEFORE INSERT ON voting_votingversionsnapshot
    FOR EACH ROW EXECUTE FUNCTION voting_snapshot_insert_window();

CREATE TRIGGER snapshot_insert_window
    BEFORE INSERT ON voting_votingversionaptitudesnapshot
    FOR EACH ROW EXECUTE FUNCTION voting_snapshot_insert_window();

CREATE TRIGGER snapshot_image_character
    BEFORE INSERT OR UPDATE ON voting_votingcharactersnapshot
    FOR EACH ROW EXECUTE FUNCTION voting_snapshot_image_character();

CREATE TRIGGER snapshot_version_character
    BEFORE INSERT ON voting_votingversionsnapshot
    FOR EACH ROW EXECUTE FUNCTION voting_snapshot_version_character();
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS snapshot_version_character ON voting_votingversionsnapshot;
DROP TRIGGER IF EXISTS snapshot_image_character ON voting_votingcharactersnapshot;
DROP TRIGGER IF EXISTS snapshot_insert_window ON voting_votingversionaptitudesnapshot;
DROP TRIGGER IF EXISTS snapshot_insert_window ON voting_votingversionsnapshot;
DROP TRIGGER IF EXISTS snapshot_insert_window ON voting_votingcharactersnapshot;
DROP TRIGGER IF EXISTS snapshot_no_delete ON voting_votingversionaptitudesnapshot;
DROP TRIGGER IF EXISTS snapshot_no_delete ON voting_votingversionsnapshot;
DROP TRIGGER IF EXISTS snapshot_no_delete ON voting_votingcharactersnapshot;
DROP TRIGGER IF EXISTS snapshot_no_update ON voting_votingversionaptitudesnapshot;
DROP TRIGGER IF EXISTS snapshot_no_update ON voting_votingversionsnapshot;
DROP TRIGGER IF EXISTS snapshot_no_update ON voting_votingcharactersnapshot;
DROP TRIGGER IF EXISTS eligibility_draft_only ON voting_votingeligibility;
DROP TRIGGER IF EXISTS voting_config_immutable ON voting_voting;
DROP TRIGGER IF EXISTS voting_transition ON voting_voting;

DROP FUNCTION IF EXISTS voting_snapshot_version_character();
DROP FUNCTION IF EXISTS voting_snapshot_image_character();
DROP FUNCTION IF EXISTS voting_snapshot_insert_window();
DROP FUNCTION IF EXISTS voting_snapshot_no_delete();
DROP FUNCTION IF EXISTS voting_snapshot_no_update();
DROP FUNCTION IF EXISTS voting_eligibility_draft_only();
DROP FUNCTION IF EXISTS voting_config_immutable();
DROP FUNCTION IF EXISTS voting_transition();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("voting", "0002_ballot_triggers"),
    ]

    operations = [
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
