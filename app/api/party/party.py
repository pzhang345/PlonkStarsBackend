from datetime import datetime, timedelta

import pytz

from api.game.gameutils import delete_orphaned_rules
from api.game.gametype import game_type
from models.db import db
from models.party import Party
from fsocket import socketio
from models.session import PlayerPlonk


def clean_party():
    """Deletes all inactive parties"""
    cutoff = datetime.now(tz=pytz.utc) - timedelta(days=1)
    parties = Party.query.filter(Party.last_activity < cutoff)
    parties_count = parties.count()
    for party in Party.query.filter(Party.last_activity < cutoff):
        socketio.emit("leave", {"reason": "Party expired"}, namespace="/socket/party", room=party.code)
        db.session.delete(party)
    delete_orphaned_rules()
    db.session.commit()
    return parties_count

def clean_db():
    """Cleans up the database"""
    delete_orphaned_rules()
    for plonk in PlayerPlonk.query.all():
        session = plonk.round.session
        game_type[session.type].ping(plonk.user,session)