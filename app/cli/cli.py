import pytz
from api.game.gameutils import create_round
from models.party import Party
from models.session import DailyChallenge, GameType, Session
from datetime import datetime, timedelta
from models.db import db
from models.configs import Configs
        
def register_commands(app):
    @app.cli.command("create-daily")
    def create_daily():
        """Create a new daily challenge"""
        tomorrow = datetime.now(tz=pytz.utc).date() + timedelta(days=1)
        if DailyChallenge.query.filter_by(date=tomorrow).first():
            print("Daily challenge already exists for tomorrow.")
            return

        ROUND_NUMBER = int(Configs.get("DAILY_DEFAULT_ROUNDS"))
        TIME_LIMIT =  int(Configs.get("DAILY_DEFAULT_TIME_LIMIT"))
        NMPZ = Configs.get("DAILY_DEFAULT_NMPZ").lower() == "true"
        MAP_ID = int(Configs.get("DAILY_DEFAULT_MAP_ID"))
        HOST_ID = int(Configs.get("DAILY_DEFAULT_HOST_ID"))
        
        session = Session(
            host_id=HOST_ID,
            map_id=MAP_ID,
            time_limit=TIME_LIMIT,
            max_rounds=ROUND_NUMBER,
            type=GameType.CHALLENGE, 
            nmpz=NMPZ
        )
        db.session.add(session)
        db.session.flush()
        for i in range(ROUND_NUMBER):
            create_round(session,TIME_LIMIT)
        daily_challenge = DailyChallenge(session_id=session.id, date=tomorrow)
        db.session.add(daily_challenge)
        db.session.commit()
        
        print("Daily challenge created successfully.")
        
    @app.cli.command("clean-parties")
    def clean_party():
        """Deletes all inactive parties"""
        cutoff = datetime.now(tz=pytz.utc) - timedelta(days=1)
        Party.query.filter(Party.last_activity < cutoff).delete(synchronize_session=False)
        db.session.commit()
        print("Inactive parties deleted successfully.")