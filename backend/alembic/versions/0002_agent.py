"""add agent tables and columns

Revision ID: 0002_agent
Revises: 0001_initial
Create Date: 2026-04-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_agent"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add agent columns to conversations
    op.add_column(
        "conversations",
        sa.Column("agent_phase", sa.String(50), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("agent_phase_before_change", sa.String(50), nullable=True),
    )

    # Add staleness_status to document_versions
    op.add_column(
        "document_versions",
        sa.Column(
            "staleness_status",
            sa.String(20),
            nullable=False,
            server_default="CURRENT",
        ),
    )

    # domain_concepts
    op.create_table(
        "domain_concepts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "conversation_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("concept_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_domain_concepts_id"), "domain_concepts", ["id"], unique=False
    )

    # business_scenario_records
    op.create_table(
        "business_scenario_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "conversation_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("scenario_key", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_business_scenario_records_id"),
        "business_scenario_records",
        ["id"],
        unique=False,
    )

    # requirement_change_records
    op.create_table(
        "requirement_change_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "affected_document_types",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_requirement_change_records_id"),
        "requirement_change_records",
        ["id"],
        unique=False,
    )

    # phase_documents
    op.create_table(
        "phase_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("phase", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "rendered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_phase_documents_id"), "phase_documents", ["id"], unique=False
    )
    op.create_index(
        "ix_phase_documents_conversation_phase",
        "phase_documents",
        ["conversation_id", "phase"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_phase_documents_conversation_phase", table_name="phase_documents")
    op.drop_index(op.f("ix_phase_documents_id"), table_name="phase_documents")
    op.drop_table("phase_documents")

    op.drop_index(
        op.f("ix_requirement_change_records_id"),
        table_name="requirement_change_records",
    )
    op.drop_table("requirement_change_records")

    op.drop_index(
        op.f("ix_business_scenario_records_id"),
        table_name="business_scenario_records",
    )
    op.drop_table("business_scenario_records")

    op.drop_index(op.f("ix_domain_concepts_id"), table_name="domain_concepts")
    op.drop_table("domain_concepts")

    op.drop_column("document_versions", "staleness_status")
    op.drop_column("conversations", "agent_phase_before_change")
    op.drop_column("conversations", "agent_phase")
