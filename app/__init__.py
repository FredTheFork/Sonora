from flask import Flask
from config import Config
from app.extensions import db, login_manager  # Import FROM extensions

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    # Register Blueprints
    from app.routes.auth import auth_bp
    from app.routes.pool import pool_bp
    from app.routes.vault import vault_bp
    from app.routes.trade import trade_bp
    from app.routes.leaderboard import leaderboard_bp
    from app.routes.main import main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(pool_bp)
    app.register_blueprint(leaderboard_bp)
    app.register_blueprint(vault_bp)
    app.register_blueprint(trade_bp)

    with app.app_context():
        from app import models
        db.create_all()

    return app