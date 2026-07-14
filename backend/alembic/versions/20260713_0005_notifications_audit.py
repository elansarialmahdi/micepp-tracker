"""Add notifications, immutable audit and visibility states.

Revision ID: 20260713_0005
Revises: 20260713_0004
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260713_0005"
down_revision: str | None = "20260713_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("vulnerability_id", sa.Uuid(), nullable=True),
        sa.Column("service_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low', 'info')",
            name="ck_notifications_severity",
        ),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index("ix_notifications_service_id", "notifications", ["service_id"])
    op.create_index("ix_notifications_severity", "notifications", ["severity"])
    op.create_index("ix_notifications_type", "notifications", ["type"])
    op.create_table(
        "notification_platforms",
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("platform_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("notification_id", "platform_id"),
    )
    op.create_table(
        "notification_user_states",
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("notification_id", "user_id"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=150), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("platform_id", sa.Uuid(), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("before_data", sa.JSON(), nullable=True),
        sa.Column("after_data", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "action",
        "actor_user_id",
        "created_at",
        "entity_id",
        "entity_type",
        "platform_id",
        "request_id",
    ):
        op.create_index(f"ix_audit_events_{column}", "audit_events", [column])
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION prevent_audit_event_mutation() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Audit events are immutable';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER audit_events_immutable
            BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation()
            """
        )
    elif dialect == "sqlite":
        op.execute(
            """
            CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events
            BEGIN SELECT RAISE(ABORT, 'Audit events are immutable'); END
            """
        )
        op.execute(
            """
            CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events
            BEGIN SELECT RAISE(ABORT, 'Audit events are immutable'); END
            """
        )
    op.create_table(
        "history_visibility_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("platform_id", sa.Uuid(), nullable=True),
        sa.Column("hidden_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "platform_id", name="uq_history_visibility_user_platform"),
    )
    op.create_index(
        "ix_history_visibility_states_platform_id", "history_visibility_states", ["platform_id"]
    )
    op.create_index(
        "ix_history_visibility_states_user_id", "history_visibility_states", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_history_visibility_states_user_id", table_name="history_visibility_states")
    op.drop_index(
        "ix_history_visibility_states_platform_id", table_name="history_visibility_states"
    )
    op.drop_table("history_visibility_states")
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER audit_events_immutable ON audit_events")
        op.execute("DROP FUNCTION prevent_audit_event_mutation()")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER audit_events_no_update")
        op.execute("DROP TRIGGER audit_events_no_delete")
    for column in (
        "request_id",
        "platform_id",
        "entity_type",
        "entity_id",
        "created_at",
        "actor_user_id",
        "action",
    ):
        op.drop_index(f"ix_audit_events_{column}", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("notification_user_states")
    op.drop_table("notification_platforms")
    op.drop_index("ix_notifications_type", table_name="notifications")
    op.drop_index("ix_notifications_severity", table_name="notifications")
    op.drop_index("ix_notifications_service_id", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_table("notifications")
