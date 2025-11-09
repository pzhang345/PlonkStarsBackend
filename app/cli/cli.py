from api.party.party import clean_db, clean_party
from api.session.daily import award_prev_daily_challenge_coins, create_daily
from models.db import db
from models.user import User

def register_commands(app):
    @app.cli.command("daily-tasks")
    def daily_cli():
        create_daily()
        clean_party()
        award_prev_daily_challenge_coins()
        clean_db()
        
    
    @app.cli.command("create-daily")
    def create_daily_cli():
        create_daily()
        print("Daily challenge created successfully.")
        
    @app.cli.command("clean-parties")
    def clean_party_cli():
        """Deletes all inactive parties"""
        parties_count = clean_party()
        print(f"{parties_count} parties deleted")

    @app.cli.command("daily-coins")
    def award_daily_challenge_coins_cli():
        """Award coins to users based on their performance in the daily challenge"""
        award_prev_daily_challenge_coins()
        print("Coins awarded successfully")
    
    @app.cli.command("clean-db")
    def clean_db_cli():
        """Cleans up the database"""
        clean_db()
        print("Database cleaned successfully")
        
    @app.cli.command("create-demo")
    def create_demo_cli():
        """Creates a demo user for testing purposes"""
        demo_user = User(username="demo", password='a')
        db.session.add(demo_user)
        db.session.commit()
        print("Demo user created successfully.")
