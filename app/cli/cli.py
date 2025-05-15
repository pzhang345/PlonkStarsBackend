import pytz
from api.game.gameutils import create_round
from models.party import Party
from models.session import DailyChallenge, GameType, Session
from datetime import datetime, timedelta
from models.db import db
from models.configs import Configs
from fsocket import socketio
from sqlalchemy import func, and_
from models.stats import RoundStats
from models.cosmetics import UserCoins

def award_daily_challenge_coins(session_id):
    # Step 1: Get latest round per user
    latest_rounds_subq = (
        db.session.query(
            RoundStats.user_id,
            func.max(RoundStats.round).label("max_round")
        )
        .filter(RoundStats.session_id == session_id)
        .group_by(RoundStats.user_id)
        .subquery()
    )

    # Step 2: Get the actual RoundStats entries for each user's latest round
    latest_rounds = (
        db.session.query(RoundStats)
        .join(
            latest_rounds_subq,
            and_(
                RoundStats.user_id == latest_rounds_subq.c.user_id,
                RoundStats.round == latest_rounds_subq.c.max_round
            )
        )
        .filter(RoundStats.session_id == session_id)
        .all()
    )

    # Step 3: Sort players by total_score (descending)
    sorted_players = sorted(latest_rounds, key=lambda x: x.total_score, reverse=True)

    # If no players participated, return early without awarding anything
    if not sorted_players:
        return {"message": "No participants found, no coins awarded"}, 200

    # Step 4: Award top prizes starting from the lowest prize for the number of participants (max 5)
    coin_rewards = [1000, 800, 600, 400, 200]  # highest to lowest
    num_participants = len(sorted_players)
    top_prizes_to_award = min(num_participants, 5)

    # Reverse prizes so we assign lowest prizes to lowest rank among top players
    prizes_to_give = coin_rewards[-top_prizes_to_award:]  # get last N prizes
    prizes_to_give.reverse()  # now lowest prize first, highest prize last

    top_5_ids = set()

    for i, player in enumerate(sorted_players[:top_prizes_to_award]):
        reward = prizes_to_give[i]
        top_5_ids.add(player.user_id)
        user_coins = UserCoins.query.filter_by(user_id=player.user_id).first()
        if not user_coins:
            user_coins = UserCoins(user_id=player.user_id, coins=reward + 100)  # include participation
            db.session.add(user_coins)
        else:
            user_coins.coins += reward + 100  # include participation

    # Step 5: Award 100 coins to everyone else (excluding top prize winners)
    for player in sorted_players:
        if player.user_id in top_5_ids:
            continue  # already handled above
        user_coins = UserCoins.query.filter_by(user_id=player.user_id).first()
        if not user_coins:
            user_coins = UserCoins(user_id=player.user_id, coins=100)
            db.session.add(user_coins)
        else:
            user_coins.coins += 100

    db.session.commit()

    return {"message": "Coins awarded successfully"}, 200

def register_commands(app):
    @app.cli.command("create-daily")
    def create_daily():
        today = datetime.now(tz=pytz.utc).date()

        '''get results before creating new daily'''
        previous_session = DailyChallenge.query.filter_by(date=today).first()
        award_daily_challenge_coins(previous_session.id)


        """Create a new daily challenge"""
        tomorrow = today + timedelta(days=1)
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
        parties = Party.query.filter(Party.last_activity < cutoff)
        parties_count = parties.count()
        for party in Party.query.filter(Party.last_activity < cutoff):
            socketio.emit("leave", {"reason": "Party expired"}, namespace="/socket/party", room=party.code)
            db.session.delete(party)
        db.session.commit()
        print(f"{parties_count} parties deleted")

    
# New CLI command to test awarding coins manually
    # @app.cli.command("test-award-coins")
    # def test_award_coins():
    #     today = datetime.now(tz=pytz.utc).date()
    #     daily = DailyChallenge.query.filter_by(date=today).first()
    #     if not daily:
    #         print("No daily challenge found for today.")
    #         return
    #     print(f"Awarding coins for session_id {daily.session_id} (daily challenge for {today})")
    #     result, status = award_daily_challenge_coins(daily.session_id)
    #     print(result["message"])
