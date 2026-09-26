import eventlet
eventlet.monkey_patch(socket=True)

from factory import create_app
from fsocket import socketio
from my_celery.db_sync import start_sync_db

app = create_app()

if __name__ == "__main__":
    start_sync_db(app)
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
