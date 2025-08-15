from api.game.gametype import game_type
from base_celery import celery
from models.db import db
from models.session import CeleryTaskTracker, Session
from models.user import User

def update_game_state(data, user, session, time):
    if "type" not in data:
        data["type"] = "ping"
    stop_current_task(session)
    
    task = __update_game_state__.apply_async(args=[data, user.id, session.id], countdown=time)
    task_tracker = CeleryTaskTracker(session_id=session.id, task_id=task.id)
    db.session.add(task_tracker)
    db.session.commit()
    

def stop_current_task(session):
    current_task = CeleryTaskTracker.query.filter_by(session_id=session.id).first()
    if current_task:
        celery.control.revoke(current_task.task_id, terminate=True)
        db.session.delete(current_task)
        db.session.commit()

@celery.task(ignore_result=True)
def __update_game_state__(data, user_id, session_id):
    session = Session.query.filter_by(id=session_id).first()
    user = User.query.filter_by(id=user_id).first()
    game_type[session.type].ping(data, user, session)
    