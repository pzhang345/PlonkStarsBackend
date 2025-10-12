from api.party.party import clean_db
from api.session.daily import award_prev_daily_challenge_coins, create_daily
from my_celery.daily_tasks import clean_party

def register_commands(app):
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
