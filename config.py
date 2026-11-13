import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-fallback-key')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///sonora.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
    SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
    SPOTIFY_REDIRECT_URI = os.environ.get('SPOTIFY_REDIRECT_URI')
    SPOTIFY_AUTH_URL = 'https://accounts.spotify.com/authorize'
    SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'
    SPOTIFY_API_URL = 'https://api.spotify.com/v1'

    SPOTIFY_SCOPES = ' '.join([
        'user-library-read',            
        'user-read-recently-played',     
        'user-read-playback-state',      
        'user-top-read',                
        'playlist-read-private',          
        'user-read-email',                
        'user-read-private',              
    ])