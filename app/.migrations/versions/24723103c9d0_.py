"""empty message

Revision ID: 24723103c9d0
Revises: b319535879e6
Create Date: 2025-04-08 18:29:49.847118

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '24723103c9d0'
down_revision = 'b319535879e6'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('guesses', schema=None) as batch_op:
        batch_op.drop_constraint('guesses_ibfk_1', type_='foreignkey')
        batch_op.drop_constraint('guesses_ibfk_2', type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['user_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(None, 'rounds', ['round_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('mapbounds', schema=None) as batch_op:
        batch_op.drop_constraint('mapbounds_ibfk_1', type_='foreignkey')
        batch_op.drop_constraint('mapbounds_ibfk_2', type_='foreignkey')
        batch_op.create_foreign_key(None, 'bounds', ['bound_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(None, 'maps', ['map_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('maps', schema=None) as batch_op:
        batch_op.drop_constraint('maps_ibfk_1', type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['creator_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('mapstats', schema=None) as batch_op:
        batch_op.drop_constraint('mapstats_ibfk_1', type_='foreignkey')
        batch_op.create_foreign_key(None, 'maps', ['map_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('players', schema=None) as batch_op:
        batch_op.drop_constraint('players_ibfk_2', type_='foreignkey')
        batch_op.drop_constraint('players_ibfk_1', type_='foreignkey')
        batch_op.create_foreign_key(None, 'sessions', ['session_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(None, 'users', ['user_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('rounds', schema=None) as batch_op:
        batch_op.drop_constraint('rounds_ibfk_2', type_='foreignkey')
        batch_op.drop_constraint('rounds_ibfk_1', type_='foreignkey')
        batch_op.create_foreign_key(None, 'svlocations', ['location_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(None, 'sessions', ['session_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('roundstats', schema=None) as batch_op:
        batch_op.drop_constraint('roundstats_ibfk_1', type_='foreignkey')
        batch_op.drop_constraint('roundstats_ibfk_2', type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['user_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(None, 'sessions', ['session_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_constraint('sessions_ibfk_1', type_='foreignkey')
        batch_op.drop_constraint('sessions_ibfk_2', type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['host_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(None, 'maps', ['map_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('usermapstats', schema=None) as batch_op:
        batch_op.drop_constraint('usermapstats_ibfk_1', type_='foreignkey')
        batch_op.drop_constraint('usermapstats_ibfk_2', type_='foreignkey')
        batch_op.create_foreign_key(None, 'maps', ['map_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(None, 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('usermapstats', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('usermapstats_ibfk_2', 'maps', ['map_id'], ['id'])
        batch_op.create_foreign_key('usermapstats_ibfk_1', 'users', ['user_id'], ['id'])

    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('sessions_ibfk_2', 'maps', ['map_id'], ['id'])
        batch_op.create_foreign_key('sessions_ibfk_1', 'users', ['host_id'], ['id'])

    with op.batch_alter_table('roundstats', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('roundstats_ibfk_2', 'sessions', ['session_id'], ['id'])
        batch_op.create_foreign_key('roundstats_ibfk_1', 'users', ['user_id'], ['id'])

    with op.batch_alter_table('rounds', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('rounds_ibfk_1', 'svlocations', ['location_id'], ['id'])
        batch_op.create_foreign_key('rounds_ibfk_2', 'sessions', ['session_id'], ['id'])

    with op.batch_alter_table('players', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('players_ibfk_1', 'users', ['user_id'], ['id'])
        batch_op.create_foreign_key('players_ibfk_2', 'sessions', ['session_id'], ['id'])

    with op.batch_alter_table('mapstats', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('mapstats_ibfk_1', 'maps', ['map_id'], ['id'])

    with op.batch_alter_table('maps', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('maps_ibfk_1', 'users', ['creator_id'], ['id'])

    with op.batch_alter_table('mapbounds', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('mapbounds_ibfk_2', 'maps', ['map_id'], ['id'])
        batch_op.create_foreign_key('mapbounds_ibfk_1', 'bounds', ['bound_id'], ['id'])

    with op.batch_alter_table('guesses', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('guesses_ibfk_2', 'rounds', ['round_id'], ['id'])
        batch_op.create_foreign_key('guesses_ibfk_1', 'users', ['user_id'], ['id'])

    # ### end Alembic commands ###
