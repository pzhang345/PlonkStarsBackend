from datetime import datetime, timedelta
import pytz
from sqlalchemy import desc, func

from api.game.gameutils import create_round
from models.configs import Configs
from models.cosmetics import UserCoins
from models.db import db
from models.session import BaseRules, DailyChallenge, GameType, Session
from models.stats import RoundStats

def create_daily(date=datetime.now(tz=pytz.utc).date() + timedelta(days=1)):
    """Create a new daily challenge"""
    if DailyChallenge.query.filter_by(date=date).first():
        raise Exception("Daily challenge already exists")
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
    daily_challenge = DailyChallenge(session_id=session.id, date=date)
    db.session.add(daily_challenge)
    db.session.commit()
    
    return daily_challenge

def award_prev_daily_challenge_coins():
    """Award coins to users based on their performance in the daily challenge"""
    today = datetime.now(tz=pytz.utc).date()
    yesterday = today - timedelta(days=1)
    for daily in DailyChallenge.query.filter(DailyChallenge.date < yesterday, DailyChallenge.coins_added == False):
        award_daily_challenge_coins(daily)
        
    db.session.commit()

def award_daily_challenge_coins(daily):
    """Award coins to users based on their performance in the daily challenge"""
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