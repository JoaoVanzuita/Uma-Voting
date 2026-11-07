"""Triggers PostgreSQL de integridade de cédulas e escolhas."""

from django.db import migrations

FORWARD_SQL = """
CREATE OR REPLACE FUNCTION voting_ballot_insert_open() RETURNS trigger AS $$
DECLARE
    v_status varchar(12);
    v_close_mode varchar(10);
    v_closes_at timestamptz;
BEGIN
    SELECT status, close_mode, closes_at
      INTO v_status, v_close_mode, v_closes_at
      FROM voting_voting
     WHERE id = NEW.voting_id;

    IF v_status IS DISTINCT FROM 'open' THEN
        RAISE EXCEPTION 'Cédula só pode ser inserida com votação aberta.'
            USING ERRCODE = '23514';
    END IF;

    IF v_close_mode = 'automatic'
       AND (v_closes_at IS NULL OR now() >= v_closes_at) THEN
        RAISE EXCEPTION 'O prazo de encerramento da votação já passou.'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION voting_ballot_eligible_participant() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM voting_votingeligibility
         WHERE voting_id = NEW.voting_id
           AND user_id = NEW.participant_id
    ) THEN
        RAISE EXCEPTION 'Participante não é elegível para esta votação.'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION voting_ballot_no_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Cédulas são imutáveis.'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION voting_ballot_delete_window() RETURNS trigger AS $$
DECLARE
    v_status varchar(12);
BEGIN
    SELECT status INTO v_status
      FROM voting_voting
     WHERE id = OLD.voting_id;

    IF v_status = 'open' OR v_status = 'cancelled' THEN
        -- Autoriza a cascata para as escolhas na mesma transação.
        PERFORM set_config('app.ballot_delete', 'on', true);
        RETURN OLD;
    END IF;

    RAISE EXCEPTION 'Exclusão de cédula permitida apenas com votação aberta ou cancelada.'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION voting_ballot_choice_insert_open() RETURNS trigger AS $$
DECLARE
    v_status varchar(12);
    v_close_mode varchar(10);
    v_closes_at timestamptz;
    v_ballot_voting bigint;
    v_snapshot_voting bigint;
BEGIN
    SELECT v.status, v.close_mode, v.closes_at, b.voting_id
      INTO v_status, v_close_mode, v_closes_at, v_ballot_voting
      FROM voting_ballot b
      JOIN voting_voting v ON v.id = b.voting_id
     WHERE b.id = NEW.ballot_id;

    IF v_status IS DISTINCT FROM 'open' THEN
        RAISE EXCEPTION 'Escolha só pode ser inserida com votação aberta.'
            USING ERRCODE = '23514';
    END IF;

    IF v_close_mode = 'automatic'
       AND (v_closes_at IS NULL OR now() >= v_closes_at) THEN
        RAISE EXCEPTION 'O prazo de encerramento da votação já passou.'
            USING ERRCODE = '23514';
    END IF;

    SELECT voting_id INTO v_snapshot_voting
      FROM voting_votingcharactersnapshot
     WHERE id = NEW.character_snapshot_id;

    IF v_snapshot_voting IS DISTINCT FROM v_ballot_voting THEN
        RAISE EXCEPTION 'A personagem escolhida não pertence à votação da cédula.'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION voting_ballot_choice_no_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Escolhas de cédula são imutáveis.'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION voting_ballot_choice_delete_window() RETURNS trigger AS $$
DECLARE
    v_status varchar(12);
BEGIN
    IF current_setting('app.ballot_delete', true) = 'on' THEN
        RETURN OLD;
    END IF;

    SELECT v.status INTO v_status
      FROM voting_ballot b
      JOIN voting_voting v ON v.id = b.voting_id
     WHERE b.id = OLD.ballot_id;

    IF v_status = 'cancelled' THEN
        RETURN OLD;
    END IF;

    RAISE EXCEPTION 'Exclusão individual de escolha não é permitida.'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION voting_ballot_choice_count() RETURNS trigger AS $$
DECLARE
    v_ballot_id bigint;
    v_expected integer;
    v_count integer;
BEGIN
    v_ballot_id := COALESCE(NEW.ballot_id, OLD.ballot_id);

    SELECT v.choices_count
      INTO v_expected
      FROM voting_voting v
      JOIN voting_ballot b ON b.voting_id = v.id
     WHERE b.id = v_ballot_id;

    IF NOT FOUND THEN
        -- A cédula foi apagada (exclusão administrativa ou cancelamento).
        RETURN NULL;
    END IF;

    SELECT COUNT(*) INTO v_count
      FROM voting_ballotchoice
     WHERE ballot_id = v_ballot_id;

    IF v_count <> v_expected THEN
        RAISE EXCEPTION 'A cédula deve conter exatamente % escolhas.', v_expected
            USING ERRCODE = '23514';
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ballot_eligible_participant
    BEFORE INSERT ON voting_ballot
    FOR EACH ROW EXECUTE FUNCTION voting_ballot_eligible_participant();

CREATE TRIGGER ballot_insert_open
    BEFORE INSERT ON voting_ballot
    FOR EACH ROW EXECUTE FUNCTION voting_ballot_insert_open();

CREATE TRIGGER ballot_no_update
    BEFORE UPDATE ON voting_ballot
    FOR EACH ROW EXECUTE FUNCTION voting_ballot_no_update();

CREATE TRIGGER ballot_delete_window
    BEFORE DELETE ON voting_ballot
    FOR EACH ROW EXECUTE FUNCTION voting_ballot_delete_window();

CREATE TRIGGER ballot_choice_insert_open
    BEFORE INSERT ON voting_ballotchoice
    FOR EACH ROW EXECUTE FUNCTION voting_ballot_choice_insert_open();

CREATE TRIGGER ballot_choice_no_update
    BEFORE UPDATE ON voting_ballotchoice
    FOR EACH ROW EXECUTE FUNCTION voting_ballot_choice_no_update();

CREATE TRIGGER ballot_choice_delete_window
    BEFORE DELETE ON voting_ballotchoice
    FOR EACH ROW EXECUTE FUNCTION voting_ballot_choice_delete_window();

CREATE CONSTRAINT TRIGGER ballot_choice_count
    AFTER INSERT OR UPDATE OR DELETE ON voting_ballotchoice
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION voting_ballot_choice_count();
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS ballot_choice_count ON voting_ballotchoice;
DROP TRIGGER IF EXISTS ballot_choice_delete_window ON voting_ballotchoice;
DROP TRIGGER IF EXISTS ballot_choice_no_update ON voting_ballotchoice;
DROP TRIGGER IF EXISTS ballot_choice_insert_open ON voting_ballotchoice;
DROP TRIGGER IF EXISTS ballot_delete_window ON voting_ballot;
DROP TRIGGER IF EXISTS ballot_no_update ON voting_ballot;
DROP TRIGGER IF EXISTS ballot_insert_open ON voting_ballot;
DROP TRIGGER IF EXISTS ballot_eligible_participant ON voting_ballot;

DROP FUNCTION IF EXISTS voting_ballot_choice_count();
DROP FUNCTION IF EXISTS voting_ballot_choice_delete_window();
DROP FUNCTION IF EXISTS voting_ballot_choice_no_update();
DROP FUNCTION IF EXISTS voting_ballot_choice_insert_open();
DROP FUNCTION IF EXISTS voting_ballot_delete_window();
DROP FUNCTION IF EXISTS voting_ballot_no_update();
DROP FUNCTION IF EXISTS voting_ballot_insert_open();
DROP FUNCTION IF EXISTS voting_ballot_eligible_participant();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("voting", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
