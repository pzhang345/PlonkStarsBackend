"""empty message

Revision ID: eadf475001cf
Revises: a81c771bdf07
Create Date: 2025-03-15 23:24:21.314039

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'eadf475001cf'
down_revision = 'a81c771bdf07'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('usermapstats', schema=None) as batch_op:
        batch_op.alter_column('high_average_time',
               existing_type=mysql.INTEGER(),
               type_=sa.Float(),
               existing_nullable=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('usermapstats', schema=None) as batch_op:
        batch_op.alter_column('high_average_time',
               existing_type=sa.Float(),
               type_=mysql.INTEGER(),
               existing_nullable=False)

    # ### end Alembic commands ###
