"""Add durable notification event identity and lookup indexes.

Revision ID: d84e2f6a7b30
Revises: b73d8a4c9f10
"""
from alembic import op
import sqlalchemy as sa

revision = "d84e2f6a7b30"
down_revision = "b73d8a4c9f10"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    columns = {column['name'] for column in sa.inspect(connection).get_columns('notifications')}
    if not {'notification_id', 'user_id', 'application_id', 'is_read', 'notification_message'}.issubset(columns):
        raise RuntimeError('Unexpected notifications schema. Stop and inspect before migration.')
    if {'event_type', 'event_key', 'job_id'} & columns:
        raise RuntimeError('Notification migration appears partially applied. Manual inspection required.')
    # Chỉ định danh bản ghi cũ, không dựng lại sự kiện Application trong quá khứ.
    op.add_column('notifications', sa.Column('event_type', sa.String(40), nullable=True))
    op.add_column('notifications', sa.Column('event_key', sa.String(160), nullable=True))
    op.add_column('notifications', sa.Column('job_id', sa.Integer(), nullable=True))
    table = sa.table('notifications', sa.column('notification_id', sa.Integer()),
                     sa.column('event_type', sa.String()), sa.column('event_key', sa.String()))
    for row in connection.execute(sa.select(table.c.notification_id)).all():
        connection.execute(table.update().where(table.c.notification_id == row.notification_id).values(
            event_type='LEGACY', event_key=f'legacy:{row.notification_id}'))
    with op.batch_alter_table('notifications') as batch:
        batch.alter_column('event_type', existing_type=sa.String(40), nullable=False)
        batch.alter_column('event_key', existing_type=sa.String(160), nullable=False)
        batch.create_foreign_key('fk_notification_job_id_jobs', 'jobs', ['job_id'], ['job_id'])
        batch.create_unique_constraint('uq_notification_user_event', ['user_id', 'event_key'])
        batch.create_index('ix_notification_user_latest', ['user_id', 'notification_id'])
        batch.create_index('ix_notification_user_unread', ['user_id', 'is_read', 'notification_id'])


def downgrade():
    # Giữ bản ghi thông báo và các trường cũ, chỉ bỏ metadata bổ sung.
    connection = op.get_bind()
    if connection.dialect.name == 'mysql':
        removed = {'ix_notification_user_unread', 'ix_notification_user_latest', 'uq_notification_user_event'}
        indexes = sa.inspect(connection).get_indexes('notifications')
        if not any(index['name'] not in removed and index['column_names'][:1] == ['user_id'] for index in indexes):
            # InnoDB có thể bỏ index FK cũ khi index ghép thay thế được nó.
            op.create_index('ix_notification_user_id', 'notifications', ['user_id'])
    with op.batch_alter_table('notifications') as batch:
        batch.drop_index('ix_notification_user_unread')
        batch.drop_index('ix_notification_user_latest')
        batch.drop_constraint('uq_notification_user_event', type_='unique')
        batch.drop_constraint('fk_notification_job_id_jobs', type_='foreignkey')
        batch.drop_column('job_id')
        batch.drop_column('event_key')
        batch.drop_column('event_type')
