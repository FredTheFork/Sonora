from flask import Blueprint, render_template
from flask_login import login_required, current_user
from sqlalchemy import func
from app.extensions import db
from app.models import UserInventory, Song

vault_bp = Blueprint('vault', __name__, url_prefix='/vault')


@vault_bp.route('/')
@login_required
def vault():
    # All inventory items for the current user, joined to Song for details
    items = (
        db.session.query(UserInventory, Song)
        .join(Song, UserInventory.spotify_song_id == Song.spotify_song_id)
        .filter(UserInventory.user_id == current_user.id)
        .order_by(UserInventory.collected_at.desc())
        .all()
    )

    # Build album progress: group collected songs by album
    album_rows = (
        db.session.query(
            Song.spotify_album_id,
            Song.album_name,
            Song.album_artwork_url,
            func.count(UserInventory.id).label('owned'),
        )
        .join(UserInventory, UserInventory.spotify_song_id == Song.spotify_song_id)
        .filter(
            UserInventory.user_id == current_user.id,
            Song.spotify_album_id.isnot(None),
        )
        .group_by(Song.spotify_album_id)
        .all()
    )

    # For each album, figure out total tracks on the album (from any Song row we have seen)
    album_totals = (
        db.session.query(
            Song.spotify_album_id,
            func.max(Song.album_total_tracks).label('total'),
        )
        .filter(Song.spotify_album_id.isnot(None))
        .group_by(Song.spotify_album_id)
        .all()
    )
    total_map = {aid: t for aid, t in album_totals}

    albums = []
    for aid, name, art, owned in album_rows:
        total = total_map.get(aid) or owned
        pct = int((owned / total) * 100) if total else 0
        albums.append({
            'id': aid,
            'name': name or 'UNKNOWN',
            'art': art,
            'owned': owned,
            'total': total,
            'pct': pct,
            'complete': owned >= total,
        })
    # Completed albums first, then by progress descending
    albums.sort(key=lambda a: (a['complete'], a['pct']), reverse=True)

    # Stats strip
    total_songs = len(items)
    rarity_counts = {'Common': 0, 'Rare': 0, 'Epic': 0, 'Legendary': 0}
    for inv, _ in items:
        r = (inv.rarity_tier or 'Common').capitalize()
        if r not in rarity_counts:
            r = 'Common'
        rarity_counts[r] += 1
    rare_plus = rarity_counts['Rare'] + rarity_counts['Epic'] + rarity_counts['Legendary']
    album_count = len(albums)

    # Streak: count consecutive days (ending today or yesterday) with at least one reveal
    days = (
        db.session.query(UserInventory.collected_at)
        .filter(UserInventory.user_id == current_user.id)
        .order_by(UserInventory.collected_at.desc())
        .all()
    )
    streak = 0
    if days:
        from datetime import date, timedelta
        seen = {d[0].date() for d in days if d[0]}
        today = date.today()
        cursor = today
        if today not in seen:
            cursor = today - timedelta(days=1)
        while cursor in seen:
            streak += 1
            cursor -= timedelta(days=1)

    # Serialize inventory for the template
    inventory = []
    for inv, song in items:
        inventory.append({
            'id': inv.id,
            'name': song.song_name or 'UNKNOWN',
            'artist': song.artist_name or 'UNKNOWN',
            'album': song.album_name or '',
            'image': song.album_artwork_url,
            'rarity': (inv.rarity_tier or 'Common').capitalize(),
        })

    return render_template(
        'vault.html',
        user=current_user,
        inventory=inventory,
        albums=albums,
        total_songs=total_songs,
        rare_songs=rare_plus,
        album_count=album_count,
        streak=streak,
        rarity_counts=rarity_counts,
    )
