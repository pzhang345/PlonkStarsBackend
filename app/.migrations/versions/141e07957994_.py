"""empty message

Revision ID: 141e07957994
Revises: 
Create Date: 2025-02-18 18:07:00.355047

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '141e07957994'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('players', schema=None) as batch_op:
        batch_op.add_column(sa.Column('current_round', sa.Integer(), nullable=False))
        batch_op.add_column(sa.Column('start_time', sa.DateTime(), nullable=False))

    with op.batch_alter_table('rounds', schema=None) as batch_op:
        batch_op.add_column(sa.Column('time_limit', sa.Integer(), nullable=False))

    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('max_rounds', sa.Integer(), nullable=False))
        batch_op.add_column(sa.Column('time_limit', sa.Integer(), nullable=False))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_column('time_limit')
        batch_op.drop_column('max_rounds')

    with op.batch_alter_table('rounds', schema=None) as batch_op:
        batch_op.drop_column('time_limit')

    with op.batch_alter_table('players', schema=None) as batch_op:
        batch_op.drop_column('start_time')
        batch_op.drop_column('current_round')

    # ### end Alembic commands ###
