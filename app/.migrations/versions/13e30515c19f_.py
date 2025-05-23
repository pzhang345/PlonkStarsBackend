"""empty message

Revision ID: 13e30515c19f
Revises: 9e4b13f85313
Create Date: 2025-05-20 19:24:04.837896

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '13e30515c19f'
down_revision = '9e4b13f85313'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('party_rules', schema=None) as batch_op:
        batch_op.add_column(sa.Column('base_rule_id', sa.Integer(), nullable=False))
        batch_op.drop_constraint('party_rules_ibfk_2', type_='foreignkey')
        batch_op.create_foreign_key(None, 'base_rules', ['base_rule_id'], ['id'], ondelete='CASCADE')
        batch_op.drop_column('max_rounds')
        batch_op.drop_column('nmpz')
        batch_op.drop_column('time_limit')
        batch_op.drop_column('map_id')

    with op.batch_alter_table('rounds', schema=None) as batch_op:
        batch_op.add_column(sa.Column('base_rule_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(None, 'base_rules', ['base_rule_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('base_rule_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(None, 'base_rules', ['base_rule_id'], ['id'], ondelete='CASCADE')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_column('base_rule_id')

    with op.batch_alter_table('rounds', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_column('base_rule_id')

    with op.batch_alter_table('party_rules', schema=None) as batch_op:
        batch_op.add_column(sa.Column('map_id', mysql.INTEGER(), autoincrement=False, nullable=False))
        batch_op.add_column(sa.Column('time_limit', mysql.INTEGER(), autoincrement=False, nullable=False))
        batch_op.add_column(sa.Column('nmpz', mysql.TINYINT(display_width=1), autoincrement=False, nullable=False))
        batch_op.add_column(sa.Column('max_rounds', mysql.INTEGER(), autoincrement=False, nullable=False))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('party_rules_ibfk_2', 'maps', ['map_id'], ['id'], ondelete='CASCADE')
        batch_op.drop_column('base_rule_id')

    # ### end Alembic commands ###
