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
    make_track('t1', 'Tiny Song', 'a_tiny', 'Garage Band', 'alb1', 12),
    make_track('t2', 'Mid Song', 'a_mid', 'Indie Band', 'alb2', 9),
    make_track('t3', 'Huge Song', 'a_huge', 'Stadium Band', 'alb3', 14),
    make_track('t4', 'Tiny Song 2', 'a_tiny', 'Garage Band', 'alb1', 12),
]

LISTENERS = {'a_tiny': 400, 'a_mid': 45000, 'a_huge': 9000000}


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


@pytest.fixture
def client(app):
    with app.app_context():
        add_user('u1')
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = 'u1'
        sess['_fresh'] = True
    return client


def load_home(client, recently_played, listeners=LISTENERS, tracks=None):
    """Load /home/ with every Spotify call replaced by fake data"""
    tracks = tracks or {}
    with patch('app.routes.pool.get_user_top_tracks', return_value=TOP_TRACKS), \
         patch('app.routes.pool.get_recently_played', return_value=recently_played), \
         patch('app.routes.pool.get_artist_listeners', side_effect=lambda tok, aid: listeners.get(aid)) as artist_mock, \
         patch('app.routes.pool.get_track', side_effect=lambda tok, tid: tracks.get(tid)):
        response = client.get('/home/')
    return response, artist_mock


def rarity_of(app, user_id, song_id):
    with app.app_context():
        item = UserInventory.query.filter_by(user_id=user_id, spotify_song_id=song_id).first()
        return item.rarity_tier if item else None


def test_pool_generation_stores_album_total_tracks(app, client):
    response, _ = load_home(client, [])
    assert response.status_code == 200
    with app.app_context():
        assert Song.query.get('t1').album_total_tracks == 12
        assert Song.query.get('t2').album_total_tracks == 9


def test_pool_generation_fills_in_old_songs(app, client):
    # a song row from before this change: no album size
    with app.app_context():
        db.session.add(Song(spotify_song_id='t1', song_name='Tiny Song', spotify_album_id='alb1'))
        db.session.commit()
    load_home(client, [])
    with app.app_context():
        assert Song.query.get('t1').album_total_tracks == 12


def test_reveal_assigns_rarity_from_listeners(app, client):
    load_home(client, TOP_TRACKS[:3])
    assert rarity_of(app, 'u1', 't1') == 'Legendary'
    assert rarity_of(app, 'u1', 't2') == 'Rare'
    assert rarity_of(app, 'u1', 't3') == 'Common'
    with app.app_context():
        assert Song.query.get('t1').artist_monthly_listeners == 400


def test_same_artist_only_fetched_once(app, client):
    _, artist_mock = load_home(client, [TOP_TRACKS[0], TOP_TRACKS[3]])
    assert artist_mock.call_count == 1
    assert rarity_of(app, 'u1', 't4') == 'Legendary'


def test_reveal_when_spotify_gives_no_listeners(app, client):
    response, _ = load_home(client, TOP_TRACKS[:1], listeners={})
    assert response.status_code == 200
    assert rarity_of(app, 'u1', 't1') == 'Common'


def test_failed_fetch_does_not_wipe_known_listeners(app, client):
    with app.app_context():
        db.session.add(Song(spotify_song_id='t1', song_name='Tiny Song',
                            spotify_album_id='alb1', artist_monthly_listeners=400))
        db.session.commit()
    load_home(client, TOP_TRACKS[:1], listeners={})
    with app.app_context():
        assert Song.query.get('t1').artist_monthly_listeners == 400
    assert rarity_of(app, 'u1', 't1') == 'Legendary'


def test_old_common_inventory_gets_rerated(app, client):
    # state of the real database today: collected, hardcoded Common, no listener count
    with app.app_context():
        db.session.add(Song(spotify_song_id='old1', song_name='Old Song'))
        db.session.add(UserInventory(user_id='u1', spotify_song_id='old1', rarity_tier='Common'))
        db.session.commit()
    tracks = {'old1': make_track('old1', 'Old Song', 'a_tiny', 'Garage Band')}
    load_home(client, [], tracks=tracks)
    assert rarity_of(app, 'u1', 'old1') == 'Legendary'
    with app.app_context():
        assert Song.query.get('old1').album_total_tracks == 12


def test_rerate_covers_every_owner_of_the_song(app, client):
    # two users both collected the same song back when everything was Common
    with app.app_context():
        add_user('u2')
        db.session.add(Song(spotify_song_id='old1', song_name='Old Song'))
        db.session.add(UserInventory(user_id='u1', spotify_song_id='old1', rarity_tier='Common'))
        db.session.add(UserInventory(user_id='u2', spotify_song_id='old1', rarity_tier='Common'))
        db.session.commit()
    tracks = {'old1': make_track('old1', 'Old Song', 'a_tiny', 'Garage Band')}
    load_home(client, [], tracks=tracks)   # u1 loads the page
    assert rarity_of(app, 'u1', 'old1') == 'Legendary'
    assert rarity_of(app, 'u2', 'old1') == 'Legendary'


def test_dead_tracks_do_not_block_the_rerate_queue(app, client):
    # 10 songs Spotify no longer knows about (a full batch) plus one it does
    with app.app_context():
        for i in range(10):
            db.session.add(Song(spotify_song_id=f'dead{i}', song_name='Gone'))
            db.session.add(UserInventory(user_id='u1', spotify_song_id=f'dead{i}', rarity_tier='Common'))
        db.session.add(Song(spotify_song_id='old1', song_name='Old Song'))
        db.session.add(UserInventory(user_id='u1', spotify_song_id='old1', rarity_tier='Common'))
        db.session.commit()
    tracks = {'old1': make_track('old1', 'Old Song', 'a_tiny', 'Garage Band')}
    for _ in range(30):
        load_home(client, [], tracks=tracks)
    assert rarity_of(app, 'u1', 'old1') == 'Legendary'


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
