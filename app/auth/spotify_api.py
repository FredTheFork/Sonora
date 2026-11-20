import requests
from urllib.parse import urlencode
from flask import current_app
from datetime import datetime, timedelta

def get_spotify_auth_url():
    """Generate the Spotify authorisation URL"""
    params = {
        'client_id': current_app.config['SPOTIFY_CLIENT_ID'],
        'response_type': 'code',
        'redirect_uri': current_app.config['SPOTIFY_REDIRECT_URI'],
        'scope': 'user-read-private user-read-email user-top-read user-read-recently-played',
        'show_dialog': False
    }
    
    base_url = 'https://accounts.spotify.com/authorize'
    return f"{base_url}?{urlencode(params)}"


def exchange_code_for_tokens(code):
    """Exchange the authorisation code for access and refresh tokens"""
    token_url = 'https://accounts.spotify.com/api/token'
    
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': current_app.config['SPOTIFY_REDIRECT_URI'],
        'client_id': current_app.config['SPOTIFY_CLIENT_ID'],
        'client_secret': current_app.config['SPOTIFY_CLIENT_SECRET']
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    response = requests.post(token_url, data=payload, headers=headers)
    
    if response.status_code != 200:
        return None
    
    data = response.json()
    return {
        'access_token': data['access_token'],
        'refresh_token': data.get('refresh_token'),
        'expires_in': data['expires_in'],
        'token_type': data['token_type']
    }


def get_spotify_user_profile(access_token):
    """Get the user's Spotify profile information"""
    profile_url = 'https://api.spotify.com/v1/me'
    
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    response = requests.get(profile_url, headers=headers)
    
    if response.status_code != 200:
        return None
    
    return response.json()


def refresh_access_token(refresh_token):
    """Get a new access token using the refresh token"""
    token_url = 'https://accounts.spotify.com/api/token'
    
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': current_app.config['SPOTIFY_CLIENT_ID'],
        'client_secret': current_app.config['SPOTIFY_CLIENT_SECRET']
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    response = requests.post(token_url, data=payload, headers=headers)
    
    if response.status_code != 200:
        return None
    
    data = response.json()
    return {
        'access_token': data['access_token'],
        'expires_in': data.get('expires_in', 3600)
    }


def is_token_expired(user):
    """Check if the user's access token has expired"""
    if not user.token_expires_at:
        return True
    return datetime.utcnow() >= user.token_expires_at


def get_valid_access_token(user):
    """Get a valid access token, refreshing if necessary"""
    from app.auth.spotify_api import refresh_access_token
    
    if is_token_expired(user):
        if not user.spotify_refresh_token:
            return None
        
        new_tokens = refresh_access_token(user.spotify_refresh_token)
        if not new_tokens:
            return None
        
        user.spotify_access_token = new_tokens['access_token']
        user.token_expires_at = datetime.utcnow() + timedelta(seconds=new_tokens['expires_in'])
        
        from app import db
        db.session.commit()
    
    return user.spotify_access_token

def get_user_top_tracks(access_token, limit=50, time_range='medium_term'):
    """Get the user's top tracks from Spotify to build the daily pool"""
    url = 'https://api.spotify.com/v1/me/top/tracks'
    headers = {'Authorization': f'Bearer {access_token}'}
    params = {'limit': limit, 'time_range': time_range} 
    
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        return []
    
    return response.json().get('items', [])

def get_recently_played(access_token, limit=50):
    """Get tracks the user has actually listened to very recently"""
    url = 'https://api.spotify.com/v1/me/player/recently-played'
    headers = {'Authorization': f'Bearer {access_token}'}
    params = {'limit': limit}
    
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        return []
    
    # Recently played returns a unique format, we just want the track data
    return [item['track'] for item in response.json().get('items', [])]

