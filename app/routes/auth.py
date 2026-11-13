from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, current_user
from app.extensions import db  # Import FROM extensions
from app.models import User
from app.auth.spotify_api import (
    get_spotify_auth_url,
    exchange_code_for_tokens,
    get_spotify_user_profile
)
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('pool.daily_pool'))
    
    auth_url = get_spotify_auth_url()
    return redirect(auth_url)


@auth_bp.route('/callback')
def callback():
    error = request.args.get('error')
    if error:
        flash(f'Spotify authorisation failed: {error}', 'error')
        return redirect(url_for('main.login'))
    
    code = request.args.get('code')
    if not code:
        flash('No authorisation code received', 'error')
        return redirect(url_for('main.login'))
    
    tokens = exchange_code_for_tokens(code)
    if not tokens:
        flash('Failed to exchange authorisation code for tokens', 'error')
        return redirect(url_for('main.login'))
    
    profile = get_spotify_user_profile(tokens['access_token'])
    if not profile:
        flash('Failed to get Spotify profile', 'error')
        return redirect(url_for('main.login'))
    
    user = User.query.get(profile['id'])
    
    if not user:
        user = User(
            id=profile['id'],
            display_name=profile.get('display_name', 'Spotify User'),
            profile_image_url=profile.get('images', [{}])[0].get('url') if profile.get('images') else None,
            spotify_access_token=tokens['access_token'],
            spotify_refresh_token=tokens.get('refresh_token'),
            token_expires_at=datetime.utcnow() + timedelta(seconds=tokens['expires_in']),
            created_at=datetime.utcnow()
        )
        db.session.add(user)
    else:
        user.spotify_access_token = tokens['access_token']
        if tokens.get('refresh_token'):
            user.spotify_refresh_token = tokens['refresh_token']
        user.token_expires_at = datetime.utcnow() + timedelta(seconds=tokens['expires_in'])
        user.display_name = profile.get('display_name', user.display_name)
        user.profile_image_url = profile.get('images', [{}])[0].get('url') if profile.get('images') else user.profile_image_url
    
    db.session.commit()
    login_user(user, remember=True)
    
    return redirect(url_for('pool.daily_pool'))


@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.login'))