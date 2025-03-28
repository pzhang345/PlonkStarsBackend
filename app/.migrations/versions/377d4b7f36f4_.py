"""empty message

Revision ID: 377d4b7f36f4
Revises: 255734513858
Create Date: 2025-03-28 01:03:24.515267

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '377d4b7f36f4'
down_revision = '255734513858'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('round', 'NMPZ', new_column_name='nmpz')
    op.alter_column('sessions', 'NMPZ', new_column_name='nmpz')
    op.alter_column('usermapstats', 'NMPZ', new_column_name='nmpz')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('round', 'nmpz', new_column_name='NMPZ')
    op.alter_column('sessions', 'nmpz', new_column_name='NMPZ')
    op.alter_column('usermapstats', 'nmpz', new_column_name='NMPZ')

    # ### end Alembic commands ###
