from datetime import datetime, timedelta, date
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models import User, Song, DailyPool, UserInventory


def make_track(track_id, name, artist_id, artist_name, album_id='alb1', total_tracks=12):
    """A track in the shape Spotify returns from top tracks / recently played"""
    return {
        'id': track_id,
        'name': name,
        'artists': [{'id': artist_id, 'name': artist_name}],
        'album': {
            'id': album_id,
            'name': 'Album ' + album_id,
            'total_tracks': total_tracks,
            'images': [{'url': 'http://img/' + album_id}],
        },
    }


TOP_TRACKS = [
    make_track('t1', 'Track One', 'a1', 'Band One', 'alb1', 12),
    make_track('t2', 'Track Two', 'a2', 'Band Two', 'alb2', 9),
    make_track('t3', 'Track Three', 'a3', 'Band Three', 'alb3', 14),
    make_track('t4', 'Track Four', 'a1', 'Band One', 'alb1', 12),
]


def add_user(user_id):
    user = User(
        id=user_id,
        display_name=user_id,
        spotify_access_token='tok',
        spotify_refresh_token='ref',
        token_expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db.session.add(user)
    db.session.commit()
    return user


def add_inventory_rows(owner_id, song_id, tier='Common'):
    db.session.add(UserInventory(user_id=owner_id, spotify_song_id=song_id, rarity_tier=tier))


@pytest.fixture
def client(app):
    with app.app_context():
        add_user('u1')
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = 'u1'
        sess['_fresh'] = True
    return client


def load_home(client, recently_played):
    """Load /home/ with every Spotify call replaced by fake data"""
    with patch('app.routes.pool.get_user_top_tracks', return_value=TOP_TRACKS), \
         patch('app.routes.pool.get_recently_played', return_value=recently_played):
        response = client.get('/home/')
    return response


def rarity_of(app, user_id, song_id):
    with app.app_context():
        item = UserInventory.query.filter_by(user_id=user_id, spotify_song_id=song_id).first()
        return item.rarity_tier if item else None


def test_pool_generation_stores_album_total_tracks(app, client):
    response = load_home(client, [])
    assert response.status_code == 200
    with app.app_context():
        assert Song.query.get('t1').album_total_tracks == 12
        assert Song.query.get('t2').album_total_tracks == 9


def test_pool_generation_fills_in_old_songs(app, client):
    # a song row from before we stored album sizes: no total tracks
    with app.app_context():
        db.session.add(Song(spotify_song_id='t1', song_name='Track One', spotify_album_id='alb1'))
        db.session.commit()
    load_home(client, [])
    with app.app_context():
        assert Song.query.get('t1').album_total_tracks == 12


def test_reveal_assigns_rarity_from_owner_count(app, client):
    load_home(client, TOP_TRACKS[:3])
    # u1 is the only owner of each song so far
    assert rarity_of(app, 'u1', 't1') == 'Legendary'
    assert rarity_of(app, 'u1', 't2') == 'Legendary'
    assert rarity_of(app, 'u1', 't3') == 'Legendary'


def test_rarity_depends_on_existing_owners(app, client):
    # 4 other people already have t2 before u1 collects it -> u1's copy is Epic
    with app.app_context():
        for uid in ['u2', 'u3', 'u4', 'u5']:
            add_user(uid)
            add_inventory_rows(uid, 't2')
        db.session.commit()
    load_home(client, [TOP_TRACKS[1]])
    assert rarity_of(app, 'u1', 't2') == 'Epic'


def test_tier_updates_for_every_owner_as_collection_grows(app, client):
    # u1 collects t1 while alone -> Legendary for u1
    load_home(client, [TOP_TRACKS[0]])
    assert rarity_of(app, 'u1', 't1') == 'Legendary'

    # u2..u6 collect the same song; once the 6th copy exists every copy is Rare
    with app.app_context():
        for uid in ['u2', 'u3', 'u4', 'u5']:
            add_user(uid)
            add_inventory_rows(uid, 't1', 'Legendary')
        db.session.commit()
    load_home(client, [])   # home load re-syncs stored tiers with real counts
    assert rarity_of(app, 'u1', 't1') == 'Epic'   # 5 owners

    with app.app_context():
        add_user('u6')
        add_inventory_rows('u6', 't1', 'Epic')
        db.session.commit()
    load_home(client, [])
    for uid in ['u1', 'u2', 'u6']:
        assert rarity_of(app, uid, 't1') == 'Rare'  # 6 owners


def test_legacy_hardcoded_common_rows_are_resynced_on_home_load(app, client):
    # state of the real database today: collected, hardcoded Common
    with app.app_context():
        db.session.add(Song(spotify_song_id='old1', song_name='Old Song'))
        add_inventory_rows('u1', 'old1', 'Common')
        db.session.commit()
    load_home(client, [])   # no reveals at all, resync still fixes the tier
    assert rarity_of(app, 'u1', 'old1') == 'Legendary'


def test_resync_marks_mass_owned_songs_common(app, client):
    with app.app_context():
        for i in range(16):
            add_user(f'other{i}')
            add_inventory_rows(f'other{i}', 'big1', 'Legendary')
        add_inventory_rows('u1', 'big1', 'Legendary')
        db.session.commit()
    load_home(client, [])
    assert rarity_of(app, 'u1', 'big1') == 'Common'   # 17 owners


def test_expired_session_redirects_to_login(app, client):
    with patch('app.routes.pool.get_valid_access_token', return_value=None):
        response = client.get('/home/')
    assert response.status_code == 302


def test_vault_shows_real_album_percentage(app, client):
    load_home(client, TOP_TRACKS[:1])      # collects 1 song from a 12 track album
    response = client.get('/vault/')
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert '1/12' in page or '1 / 12' in page
    assert '8%' in page


def test_home_page_shows_rarity_badge_on_reveal(app, client):
    response = load_home(client, TOP_TRACKS[:1])   # TOP_TRACKS[0] revealed
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'song-rarity' in page
    assert 'LEGENDARY' in page
