from app.extensions import db, login_manager  # Import FROM extensions
from flask_login import UserMixin
from datetime import datetime


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String, primary_key=True)
    display_name = db.Column(db.String(100))
    profile_image_url = db.Column(db.String(300))
    spotify_access_token = db.Column(db.String(500))
    spotify_refresh_token = db.Column(db.String(500))
    token_expires_at = db.Column(db.DateTime)
    dark_mode = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    inventory = db.relationship('UserInventory', backref='user', lazy=True)
    pool_entries = db.relationship('DailyPool', backref='user', lazy=True)


#  now uses the same login_manager as __init__.py
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


class Song(db.Model):
    __tablename__ = 'songs'
    spotify_song_id = db.Column(db.String, primary_key=True)
    song_name = db.Column(db.String(200))
    artist_name = db.Column(db.String(200))
    artist_monthly_listeners = db.Column(db.Integer)
    spotify_album_id = db.Column(db.String)
    album_name = db.Column(db.String(200))
    album_total_tracks = db.Column(db.Integer)
    album_artwork_url = db.Column(db.String(300))


class DailyPool(db.Model):
    __tablename__ = 'daily_pool'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    spotify_song_id = db.Column(db.String, db.ForeignKey('songs.spotify_song_id'))
    revealed = db.Column(db.Boolean, default=False)
    revealed_at = db.Column(db.DateTime)
    pool_date = db.Column(db.Date, default=datetime.utcnow)


class UserInventory(db.Model):
    __tablename__ = 'user_inventory'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    spotify_song_id = db.Column(db.String, db.ForeignKey('songs.spotify_song_id'))
    rarity_tier = db.Column(db.String(20))
    collected_at = db.Column(db.DateTime, default=datetime.utcnow)
    in_pending_trade = db.Column(db.Boolean, default=False)


class Trade(db.Model):
    __tablename__ = 'trades'
    id = db.Column(db.String, primary_key=True)
    initiator_user_id = db.Column(db.String, db.ForeignKey('users.id'))
    target_user_id = db.Column(db.String, db.ForeignKey('users.id'))
    offered_song_id = db.Column(db.String, db.ForeignKey('songs.spotify_song_id'))
    requested_song_id = db.Column(db.String, db.ForeignKey('songs.spotify_song_id'))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)


class LeaderboardEntry(db.Model):
    __tablename__ = 'leaderboard_entries'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'))
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
    songs_revealed_today = db.Column(db.Integer, default=0)
    current_rank = db.Column(db.Integer)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)


class Group(db.Model):
    __tablename__ = 'groups'
    id = db.Column(db.Integer, primary_key=True)
    group_name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    memberships = db.relationship('GroupMembership', backref='group', lazy=True)


class GroupMembership(db.Model):
    __tablename__ = 'group_memberships'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'))
    user_id = db.Column(db.String, db.ForeignKey('users.id'))
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)


class AlbumCompletion(db.Model):
    __tablename__ = 'album_completions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey('users.id'))
    spotify_album_id = db.Column(db.String)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)