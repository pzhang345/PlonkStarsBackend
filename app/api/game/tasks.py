from base_celery import celery
from models.db import db
from models.session import CeleryTaskTracker, Session
from models.user import User

@celery.task(ignore_result=True)
def __update_game_state__(data, session_id):
    from api.game.gametype import game_type
    
    session = Session.query.filter_by(id=session_id).first()
    game_type[session.type].update_state(data, session)
    CeleryTaskTracker.query.filter_by(session_id=session.id).delete()
    db.session.commit()

def update_game_state(data, session, time):
    stop_current_task(session)
    task = __update_game_state__.apply_async(args=[data, session.id], countdown=time)
    
    task_tracker = CeleryTaskTracker(session_id=session.id, task_id=task.id)
    db.session.add(task_tracker)
    db.session.commit()
    

def stop_current_task(session):
    current_task = CeleryTaskTracker.query.filter_by(session_id=session.id).first()
    if current_task:
        celery.control.revoke(current_task.task_id)
        db.session.delete(current_task)
        db.session.commit()
    