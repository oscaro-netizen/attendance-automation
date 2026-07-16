"""Add attendance stop/clock-out lifecycle columns

Revision ID: 55ed361dfe4e
Revises: a542632a835f
Create Date: 2026-07-16 09:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '55ed361dfe4e'
down_revision: Union[str, Sequence[str], None] = 'a542632a835f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('attendance_logs', sa.Column('ended', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('attendance_logs', sa.Column('ended_at', sa.DateTime(), nullable=True))
    op.add_column('attendance_logs', sa.Column('stop_slack_event_id', sa.String(length=100), nullable=True))
    op.add_column('attendance_logs', sa.Column('stop_status', sa.String(length=50), nullable=True))
    op.add_column('attendance_logs', sa.Column('stop_failure_reason', sa.Text(), nullable=True))
    op.add_column('attendance_logs', sa.Column('stop_response_time', sa.Float(), nullable=True))

    op.create_index(
        op.f('ix_attendance_logs_stop_slack_event_id'),
        'attendance_logs',
        ['stop_slack_event_id'],
        unique=True,
    )

    # server_default was only needed to backfill existing rows; drop it so
    # the ORM's Python-side default is the single source of truth going forward.
    op.alter_column('attendance_logs', 'ended', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_attendance_logs_stop_slack_event_id'), table_name='attendance_logs')
    op.drop_column('attendance_logs', 'stop_response_time')
    op.drop_column('attendance_logs', 'stop_failure_reason')
    op.drop_column('attendance_logs', 'stop_status')
    op.drop_column('attendance_logs', 'stop_slack_event_id')
    op.drop_column('attendance_logs', 'ended_at')
    op.drop_column('attendance_logs', 'ended')
