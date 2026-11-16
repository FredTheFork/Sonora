from unittest.mock import patch, Mock
from app.auth import spotify_api


def fake_response(status, body=None):
    r = Mock()
    r.status_code = status
    r.json.return_value = body
    return r


# Shape of GET /v1/artists/{id} as documented by Spotify
ARTIST = {
    'id': '0k17h0D3J5VfsdmQ1iZtE9',
    'name': 'Pink Floyd',
    'followers': {'href': None, 'total': 21000000},
    'popularity': 80,
}

# Since Feb 2026 newer development-mode apps get the artist WITHOUT
# followers / popularity
ARTIST_NO_FOLLOWERS = {
    'id': '0k17h0D3J5VfsdmQ1iZtE9',
    'name': 'Pink Floyd',
}


def test_listeners_from_followers():
    with patch.object(spotify_api.requests, 'get', return_value=fake_response(200, ARTIST)):
        assert spotify_api.get_artist_listeners('tok', 'abc') == 21000000


def test_listeners_when_request_fails():
    with patch.object(spotify_api.requests, 'get', return_value=fake_response(429)):
        assert spotify_api.get_artist_listeners('tok', 'abc') is None


def test_listeners_when_field_missing():
    with patch.object(spotify_api.requests, 'get', return_value=fake_response(200, ARTIST_NO_FOLLOWERS)):
        assert spotify_api.get_artist_listeners('tok', 'abc') is None
