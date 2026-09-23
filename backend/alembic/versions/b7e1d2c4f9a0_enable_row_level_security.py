"""enable row level security on every public table (Supabase Data API lockdown)

Supabase exposes the public schema over its REST/GraphQL Data API to the
`anon` and `authenticated` roles, which by default hold full grants on every
table. With RLS off, anyone holding the (intentionally public) publishable key
could read/write users, user_leagues (ESPN cookies, Yahoo tokens), etc.

The app never uses the Data API: the backend connects as `postgres`, which owns
every table and has BYPASSRLS, so enabling RLS with *no policies* denies
anon/authenticated entirely while leaving the backend unaffected.

Also installs an event trigger so tables created by future migrations get RLS
enabled automatically instead of silently shipping exposed.

Revision ID: b7e1d2c4f9a0
Revises: a1b2c3d4e5f6
Create Date: 2026-09-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b7e1d2c4f9a0'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        DO $$
        DECLARE t record;
        BEGIN
            FOR t IN
                SELECT c.relname FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
            LOOP
                EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.relname);
            END LOOP;
        END $$;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION public.rls_auto_enable()
        RETURNS event_trigger LANGUAGE plpgsql AS $$
        DECLARE obj record;
        BEGIN
            FOR obj IN
                SELECT * FROM pg_event_trigger_ddl_commands()
                WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
                  AND object_type = 'table'
                  AND schema_name = 'public'
            LOOP
                EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', obj.object_identity);
            END LOOP;
        END $$;
    """)
    op.execute("REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC, anon, authenticated")
    op.execute("DROP EVENT TRIGGER IF EXISTS rls_auto_enable")
    op.execute("""
        CREATE EVENT TRIGGER rls_auto_enable ON ddl_command_end
        WHEN TAG IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
        EXECUTE FUNCTION public.rls_auto_enable()
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("DROP EVENT TRIGGER IF EXISTS rls_auto_enable")
    op.execute("DROP FUNCTION IF EXISTS public.rls_auto_enable()")
    op.execute("""
        DO $$
        DECLARE t record;
        BEGIN
            FOR t IN
                SELECT c.relname FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
            LOOP
                EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', t.relname);
            END LOOP;
        END $$;
    """)
