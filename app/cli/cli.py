from api.game.gameutils import create_round
from models.session import DailyChallenge, GameType, Session
from datetime import datetime, timedelta
from models.db import db
        
def register_commands(app):
    @app.cli.command("create-daily")
    def create_daily():
        """Create a new daily challenge"""
        tomorrow = (datetime.now() + timedelta(days=1,hours=12)).date()
        if DailyChallenge.query.filter_by(date=tomorrow).first():
            print("Daily challenge already exists for tomorrow.")
            return
        
        ROUND_NUMBER = 5
        TIME_LIMIT = 180
        NMPZ = False
        MAP_ID = 1
        HOST_ID = 42
        
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