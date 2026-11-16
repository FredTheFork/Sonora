import pytest
from config import Config


@pytest.fixture
def app(tmp_path):
    # Point the app at a throwaway database so tests never touch instance/sonora.db
    Config.SQLALCHEMY_DATABASE_URI = 'sqlite:///' + str(tmp_path / 'test.db')
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app
