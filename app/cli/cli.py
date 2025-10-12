import pytz
from api.game.gameutils import create_round, delete_orphaned_rules
from models.party import Party
from models.session import BaseRules, CeleryTaskTracker, DailyChallenge, GameType, PlayerPlonk, Session
from datetime import datetime, timedelta
from models.db import db
from models.configs import Configs
from fsocket import socketio
from sqlalchemy import desc, func
from models.stats import RoundStats
from models.cosmetics import UserCoins
from api.game.gametype import game_type

def register_commands(app):
    @app.cli.command("create-daily")
    def create_daily():
        """Create a new daily challenge"""
        today = datetime.now(tz=pytz.utc).date()
        tomorrow = today + timedelta(days=1)
        if DailyChallenge.query.filter_by(date=tomorrow).first():
            print("Daily challenge already exists for tomorrow.")
            return

        ROUND_NUMBER = int(Configs.get("DAILY_DEFAULT_ROUNDS"))
        TIME_LIMIT =  int(Configs.get("DAILY_DEFAULT_TIME_LIMIT"))
        NMPZ = Configs.get("DAILY_DEFAULT_NMPZ").lower() == "true"
        MAP_ID = int(Configs.get("DAILY_DEFAULT_MAP_ID"))
        HOST_ID = int(Configs.get("DAILY_DEFAULT_HOST_ID"))
        
        rules = BaseRules.query.filter_by(
            map_id=MAP_ID,
            time_limit=TIME_LIMIT,
            max_rounds=ROUND_NUMBER,
            nmpz=NMPZ
        ).first()
        
        session = Session(
            host_id=HOST_ID,
            type=GameType.CHALLENGE, 
            base_rule_id=rules.id,
        )
        db.session.add(session)
        db.session.flush()
        for i in range(ROUND_NUMBER):
            create_round(session,rules)
        daily_challenge = DailyChallenge(session_id=session.id, date=tomorrow)
        db.session.add(daily_challenge)
        db.session.commit()
        
        print("Daily challenge created successfully.")
        
    @app.cli.command("clean-parties")
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
        print(f"{parties_count} parties deleted")

    @app.cli.command("daily-coins")
    def award_daily_challenge_coins():
        """Award coins to users based on their performance in the daily challenge"""
        today = datetime.now(tz=pytz.utc).date()

        yesterday = today - timedelta(days=1)
        for daily in DailyChallenge.query.filter(DailyChallenge.date < yesterday, DailyChallenge.coins_added == False):
            session = daily.session
            stats = RoundStats.query.filter_by(session_id=session.id,round=session.base_rules.max_rounds).subquery()
            ranked_users = db.session.query(
                func.rank().over(order_by=(desc(stats.c.total_score),stats.c.total_time)).label("rank"),
                UserCoins,
                stats.c.total_score,
            ).join(UserCoins,UserCoins.user_id == stats.c.user_id).order_by("rank")
            
            # Step 4: Award top prizes starting from the lowest prize for the number of participants (max 5)
            total_participants = ranked_users.count()
            
            # going to have to balance this later
            placement_rewards = {1:500, 2:450, 3:400}
            score_per_coin = 50 # every 50pts = 1 coins
            percentile_rewards = {0.01:350, 0.1:250, 0.25:100, 0.5:50}
            percentages = sorted(list(percentile_rewards.keys()))
            current_percentile = 0
            
            for rank,coins, total_score in ranked_users:
                if rank in placement_rewards:
                    coins.coins += placement_rewards[rank]
                elif current_percentile < len(percentages):
                    percent = percentages[current_percentile]
                    
                    while rank/total_participants > percent:
                        current_percentile += 1
                        if current_percentile >= len(percentages):
                            break
                        percent = percentages[current_percentile]
                    
                    if current_percentile < len(percentages):
                        coins.coins += percentile_rewards[percent]
                        
                coins.coins += total_score // score_per_coin
        
            daily.coins_added = True
        
        db.session.commit()
        print("Coins awarded successfully")
    
    @app.cli.command("clean-db")
    def clean_db():
        """Cleans up the database"""
        delete_orphaned_rules()
        for plonk in PlayerPlonk.query.all():
            session = plonk.round.session
            game_type[session.type].ping(plonk.user,session)
        print("Database cleaned successfully")
