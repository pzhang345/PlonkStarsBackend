import os

from config import Config


class TestConfig(Config):
    TESTING = True

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://plonktest:plonktest@localhost:55432/plonkstars_test",
    )

    SECRET_KEY = "test-secret-key"

    ENABLE_CELERY = False
    ENABLE_ADMIN = False
    ENABLE_MAIL = False
    REGISTER_CLI = False

    ENABLE_SOCKETIO = True
    SOCKETIO_MESSAGE_QUEUE = None

    # The conftest `app` fixture owns schema creation/teardown (create_all
    # once per session, drop_all at the end) so the factory must not also
    # try to create tables itself.
    AUTO_CREATE_ALL = False

    GOOGLE_MAPS_API_KEY = "test-google-maps-key"
