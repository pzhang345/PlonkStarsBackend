"""empty message

Revision ID: 4171b6e7e638
Revises: 2e06978dd636
Create Date: 2025-03-15 19:21:19.083827

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '4171b6e7e638'
down_revision = '2e06978dd636'
branch_labels = None
depends_on = None


def upgrade():
       # ### commands auto generated by Alembic - please adjust! ###

    with op.batch_alter_table('usermapstats', schema=None) as batch_op:
        batch_op.alter_column('high_average_score',
               existing_type=mysql.INTEGER(),
               type_=sa.Float(),
               existing_nullable=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('usermapstats', schema=None) as batch_op:
        batch_op.alter_column('high_average_score',
               existing_type=sa.Float(),
               type_=mysql.INTEGER(),
               existing_nullable=False)

    # ### end Alembic commands ###
