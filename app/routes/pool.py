from flask import Blueprint, render_template
from flask_login import login_required, current_user
from datetime import datetime, date
from app.extensions import db
from app.models import Song, DailyPool, UserInventory
from app.auth.spotify_api import (
    get_valid_access_token, 
    get_user_top_tracks, 
    get_recently_played
)

pool_bp = Blueprint('pool', __name__, url_prefix='/home')

@pool_bp.route('/')
@login_required
def daily_pool():
    # 1. Ensure token is fresh before talking to Spotify
    access_token = get_valid_access_token(current_user)
    if not access_token:
        flash("Spotify session expired. Please log in again.", "error")
        # You'd need to import logout_user and url_for here if not already
        from flask_login import logout_user
        from flask import url_for, redirect
        logout_user()
        return redirect(url_for('main.login'))

    today = date.today()
    
    # PHAsE 1: THE MIDNIGHT RESET & POOL GENERATION ------------------------------------------------------------------------------------------------------------------
    # Check if a pool exists for the specfic user for TODAY.
    existing_pool = DailyPool.query.filter_by(
        user_id=current_user.id, 
        pool_date=today
    ).first()

    if not existing_pool:
        # Fetch top tracks (Spotify limits to 50 per call, so we do short and medium term)
        short_term_tracks = get_user_top_tracks(access_token, time_range='short_term', limit=50)
        medium_term_tracks = get_user_top_tracks(access_token, time_range='medium_term', limit=50)
        
        # Combine and remove duplicates by putting them in a dictionary keyed by Spotify ID
        all_tracks_dict = {}
        for track in short_term_tracks + medium_term_tracks:
            if track['id'] not in all_tracks_dict:
                all_tracks_dict[track['id']] = track
                
        # Take exactly 100 songs (or however many we managed to get)
        final_100_tracks = list(all_tracks_dict.values())[:100]

        # Save to database
        for track in final_100_tracks:
            # 1. Save to global Song dictionary if it doesn't exist
            if not Song.query.get(track['id']):
                album = track.get('album', {})
                new_song = Song(
                    spotify_song_id=track['id'],
                    song_name=track['name'],
                    artist_name=track['artists'][0]['name'],
                    spotify_album_id=album.get('id'),
                    album_name=album.get('name'),
                    album_artwork_url=album.get('images', [{}])[0].get('url') if album.get('images') else None
                )
                db.session.add(new_song)

            # 2. Add to User's Daily Pool
            pool_entry = DailyPool(
                user_id=current_user.id,
                spotify_song_id=track['id'],
                pool_date=today
            )
            db.session.add(pool_entry)
            
        db.session.commit()

    # PHASE 2: THE LISTENING ACTIVITY MATCH CHECK -----------------------------------------------------------------------------------------------------------------------
    recently_played = get_recently_played(access_token, limit=20)
    newly_revealed_songs = []

    for track in recently_played:
        track_id = track['id']
        
        # Did this song play match a song in today's pool?
        pool_match = DailyPool.query.filter_by(
            user_id=current_user.id,
            spotify_song_id=track_id,
            pool_date=today,
            revealed=False # Only check unrevealed songs!
        ).first()

        if pool_match:
            # MATCH FOUND! 
            # 1. Mark as revealed in the daily pool
            pool_match.revealed = True
            pool_match.revealed_at = datetime.utcnow()

            # 2. Add to permanent User Inventory
            already_in_inventory = UserInventory.query.filter_by(
                user_id=current_user.id, 
                spotify_song_id=track_id
            ).first()

            if not already_in_inventory:
                new_inventory_item = UserInventory(
                    user_id=current_user.id,
                    spotify_song_id=track_id,
                    rarity_tier='Common' # We will add rarity logic later!
                )
                db.session.add(new_inventory_item)

            # 3. Get full song details to send to the frontend for animation
            song_details = Song.query.get(track_id)
            if song_details:
                newly_revealed_songs.append({
                    'name': song_details.song_name,
                    'artist': song_details.artist_name,
                    'image': song_details.album_artwork_url
                })

    # Save all the matches we just found
    if newly_revealed_songs:
        db.session.commit()

    # PHASE 3: FETCH DATA FOR THE UI ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # Get all of today's pool entries for this user
    todays_pool = DailyPool.query.filter_by(
        user_id=current_user.id, 
        pool_date=today
    ).all()

    total_songs = len(todays_pool)
    revealed_songs_data = []
    
    # Loop through the pool and manually grab the Song details for revealed tracks
    for entry in todays_pool:
        if entry.revealed:
            song = Song.query.get(entry.spotify_song_id)
            if song:
                revealed_songs_data.append({
                    'name': song.song_name,
                    'artist': song.artist_name,
                    'image': song.album_artwork_url
                })

    revealed_count = len(revealed_songs_data)
    remaining_count = total_songs - revealed_count

    return render_template(
        'home.html', 
        user=current_user, 
        newly_revealed=newly_revealed_songs,
        revealed_songs=revealed_songs_data,
        total_songs=total_songs,
        revealed_count=revealed_count,
        remaining_count=remaining_count
    )