# Sonora dev log

Running record of what was built, what broke and how it was fixed. Every
error message and test output in here is copied from an actual run, nothing
is paraphrased. Newest stage at the bottom.

---

## Stage: listener counts, album sizes and the rarity algorithm

Scope of this stage (from "what is left" in 3.4):

1. Populate `artist_monthly_listeners` and `album_total_tracks` on `Song` from the Spotify API.
2. The rarity algorithm, replacing the hardcoded `rarity_tier='Common'`.

Not in this stage: album size as a secondary rarity factor (still undecided),
album completion popups, trades, leaderboard.

### How this was tested

There was no test setup in the project, so this stage adds one: `pytest`,
with a `tests/` folder. Run it with:

```
pip install pytest
python -m pytest tests
```

The tests never touch `instance/sonora.db` (they use a throwaway database
per test) and never call Spotify. Every Spotify function is swapped for a
fake that returns data in the shape Spotify documents.

**Important limit on that:** none of this stage has been run against the
live Spotify API yet. The logic is tested, the real responses are not. See
"Still to check on a real login" at the end.

---

### 0. Problem before writing any code: Spotify has no monthly listeners

The design (2.4.4, Algorithm 2) says rarity comes from the artist's monthly
listener count "from the Spotify API". Checking the artist endpoint
(`GET /v1/artists/{id}`) before writing anything, the fields it returns are:

```
id, name, genres, images, followers.total, popularity, ...
```

There is no monthly listeners field. That number is shown in the Spotify app
but has never been part of the public Web API. The only ways to get it are
scraping the Spotify website or paying a third party, and scraping is against
Spotify's developer terms, so neither is an option for this project.

The closest thing the API does give is `followers.total`, so that is what
this stage uses as the "listener count". The column keeps its name
`artist_monthly_listeners` so the code still lines up with the design
document, but **what is stored in it is the follower count**.

Two consequences to be aware of:

- Followers and monthly listeners are different numbers for the same artist,
  so the 1,000 / 10,000 / 100,000 thresholds were chosen for a different
  scale. They are kept as they are for now and will need tuning once there is
  real data to look at.
- In February 2026 Spotify announced that `followers` and `popularity` are
  removed from the artist object for development-mode apps. This applied to
  newly created apps first and was postponed for existing ones. Whether this
  app still receives `followers` is not known until it is run. The code is
  written so that a missing `followers` is handled (songs stay Common and get
  picked up later) instead of crashing, see section 2.

---

### 1. The rarity function

New file `app/rarity.py`. The first version is the pseudocode from Algorithm 2
turned straight into Python:

```python
LEGENDARY_THRESHOLD = 1000
EPIC_THRESHOLD = 10000
RARE_THRESHOLD = 100000


def assign_rarity(listeners):
    """Return the rarity tier for an artist with this many listeners."""
    if listeners < LEGENDARY_THRESHOLD:
        return 'Legendary'
    elif listeners < EPIC_THRESHOLD:
        return 'Epic'
    elif listeners < RARE_THRESHOLD:
        return 'Rare'
    else:
        return 'Common'
```

The tiers are capitalised (`'Legendary'`, not `'legendary'` as in the design)
because the 58 rows already in `user_inventory` say `'Common'` and the vault
counts tiers by that spelling.

Tests in `tests/test_rarity.py`: the four worked examples from the design
(500, 5000, 50000, 5000000), the boundary values either side of each
threshold (0, 999, 1000, 9999, 10000, 99999, 100000), and one case the design
does not mention: what happens when there is no number at all.

First run:

```
...........F                                                             [100%]
=================================== FAILURES ===================================
_________________________ test_unknown_listener_count __________________________

    def test_unknown_listener_count():
>       assert assign_rarity(None) == 'Common'
               ^^^^^^^^^^^^^^^^^^^

tests/test_rarity.py:32:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

listeners = None

    def assign_rarity(listeners):
        """Return the rarity tier for an artist with this many listeners."""
>       if listeners < LEGENDARY_THRESHOLD:
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: '<' not supported between instances of 'NoneType' and 'int'

app/rarity.py:13: TypeError
=========================== short test summary info ============================
FAILED tests/test_rarity.py::test_unknown_listener_count - TypeError: '<' not...
1 failed, 11 passed in 0.40s
```

The 11 design and boundary cases pass, so the thresholds are right. The
failure is the missing-data case: the pseudocode assumes `monthlyListeners` is
always an integer, but the column is NULL for all 239 songs currently in the
database and Spotify may not return a number (section 0). Python cannot
compare `None < 1000`.

The decision is what an unknown artist should count as. Treating it as 0 would
make every song with missing data Legendary, which hands out the best tier for
free. So unknown means Common:

```python
def assign_rarity(listeners):
    if listeners is None:
        return 'Common'

    if listeners < LEGENDARY_THRESHOLD:
        return 'Legendary'
    ...
```

After the fix: `12 passed`.

---

### 2. Getting the number from Spotify

Two functions added to the bottom of `app/auth/spotify_api.py`. `get_artist`
follows the same pattern as the existing functions (return `None` when the
status is not 200). The first version of the second one:

```python
def get_artist_listeners(access_token, artist_id):
    """Get the audience size for an artist, used to decide rarity"""
    artist = get_artist(access_token, artist_id)
    return artist['followers']['total']
```

Tests in `tests/test_spotify_api.py` cover three responses: a normal artist, a
failed request (429 rate limit), and a 200 response with no `followers` field
(the February 2026 case from section 0).

```
>       return artist['followers']['total']
               ^^^^^^^^^^^^^^^^^^^
E       TypeError: 'NoneType' object is not subscriptable

app/auth/spotify_api.py:160: TypeError
______________________ test_listeners_when_field_missing _______________________
...
>       return artist['followers']['total']
               ^^^^^^^^^^^^^^^^^^^
E       KeyError: 'followers'

app/auth/spotify_api.py:160: KeyError
=========================== short test summary info ============================
FAILED tests/test_spotify_api.py::test_listeners_when_request_fails - TypeErr...
FAILED tests/test_spotify_api.py::test_listeners_when_field_missing - KeyErro...
2 failed, 1 passed in 0.36s
```

Two separate crashes from the same line. It is the same mistake as the profile
picture `IndexError` in the login callback: indexing straight into a Spotify
response and assuming every field is there. Because this function runs inside
the home page route, either of these would have turned one failed artist
lookup into a 500 error on the whole page. Fixed version:

```python
def get_artist_listeners(access_token, artist_id):
    """Get the audience size for an artist, used to decide rarity"""
    artist = get_artist(access_token, artist_id)
    if not artist:
        return None

    # followers is not guaranteed to be on the artist object any more,
    # so never index straight into it
    return (artist.get('followers') or {}).get('total')
```

Both failure cases now return `None`, which `assign_rarity` already turns into
Common. After the fix: `3 passed`.

---

### 3. Wiring it into the daily pool (`app/routes/pool.py`)

**Album total tracks.** This turned out to need no extra API call. Every track
returned by top tracks and recently played already carries
`album.total_tracks`, the pool generation code just was not saving it. The
loop used to skip any song already in the `songs` table, which would have left
the 239 existing rows NULL forever, so it now fills the column in on existing
rows as well:

```python
album = track.get('album', {})
existing_song = Song.query.get(track['id'])
if existing_song:
    # Songs saved before we stored album sizes get filled in here
    if existing_song.album_total_tracks is None:
        existing_song.album_total_tracks = album.get('total_tracks')
else:
    new_song = Song(
        ...
        album_total_tracks=album.get('total_tracks'),
        ...
    )
```

**Rarity at reveal time.** As in the design (2.4.3), the artist is looked up
at the moment a song is revealed, not when the pool is built. Building the
pool would mean one artist request per song, up to 100 on the first page load
of the day; at reveal time it is one request per newly collected song. A small
dictionary makes sure two songs by the same artist in one page load only cost
one request. First version:

```python
artist_id = track['artists'][0]['id']
if artist_id not in artist_listeners:
    artist_listeners[artist_id] = get_artist_listeners(access_token, artist_id)
listeners = artist_listeners[artist_id]

song_details.artist_monthly_listeners = listeners

new_inventory_item = UserInventory(
    user_id=current_user.id,
    spotify_song_id=track_id,
    rarity_tier=assign_rarity(listeners)
)
```

**Songs collected before this stage.** The 58 songs already in the inventory
are all hardcoded Common. Leaving them would mean the vault only ever shows
correct rarities for new songs, so `rerate_old_inventory()` runs on each home
page load. It finds inventory songs with no listener count, and because the
artist id was never stored, asks Spotify for the track first and then the
artist. That is two requests per song, so it is capped at 10 songs per page
load. First version of the loop:

```python
old_items = (
    db.session.query(UserInventory, Song)
    .join(Song, UserInventory.spotify_song_id == Song.spotify_song_id)
    .filter(
        UserInventory.user_id == user.id,
        Song.artist_monthly_listeners.is_(None)
    )
    .limit(RERATE_BATCH_SIZE)
    .all()
)

for item, song in old_items:
    track = get_track(access_token, song.spotify_song_id)
    if not track:
        continue

    listeners = get_artist_listeners(access_token, track['artists'][0]['id'])
    if listeners is None:
        # Spotify is not giving us numbers right now, no point asking again
        break

    song.artist_monthly_listeners = listeners
    item.rarity_tier = assign_rarity(listeners)
```

Tests in `tests/test_pool.py` load `/home/` as a logged-in user with fake
Spotify data. First full run: `2 failed, 22 passed`. The two failures, plus
two more problems found around them, are below.

#### 3a. A failed lookup erased a number that was already stored

```
    def test_failed_fetch_does_not_wipe_known_listeners(app, client):
        with app.app_context():
            db.session.add(Song(spotify_song_id='t1', song_name='Tiny Song',
                                spotify_album_id='alb1', artist_monthly_listeners=400))
            db.session.commit()
        load_home(client, TOP_TRACKS[:1], listeners={})
        with app.app_context():
>           assert Song.query.get('t1').artist_monthly_listeners == 400
E           AssertionError: assert None == 400
```

The song already had 400 stored (another user revealed it earlier). This user
reveals it while the artist request fails, and the line
`song_details.artist_monthly_listeners = listeners` writes the `None` over the
400. The user then also gets Common for a song that is known to be Legendary.
One bad response from Spotify was destroying good data.

#### 3b. Re-rating fixed one owner of a song and stranded the other

```
        tracks = {'old1': make_track('old1', 'Old Song', 'a_tiny', 'Garage Band')}
        load_home(client, [], tracks=tracks)   # u1 loads the page
        assert rarity_of(app, 'u1', 'old1') == 'Legendary'
>       assert rarity_of(app, 'u2', 'old1') == 'Legendary'
E       AssertionError: assert 'Common' == 'Legendary'
E
E         - Legendary
E         + Common
```

Two users own the same old song. When u1 loads the page the song gets its
listener count and u1's copy becomes Legendary. u2's copy stays Common, and it
can never be fixed afterwards: the re-rate finds its work by looking for songs
with no listener count, and this song now has one. The first version only
updated the one inventory row it was looking at (`item.rarity_tier = ...`),
but `Song` is shared between all users. This would also have caused trouble in
trading later, with two copies of the same song at different rarities.

#### Fix for 3a and 3b

Both come from the listener count being written in two places with slightly
different rules, so it is now written in exactly one place:

```python
def store_listeners(song, listeners):
    """Save an artist's listener count on the song.

    A failed fetch (None) never overwrites a number we already have. The first
    time a song gets a number, every copy of it collected back when rarity was
    hardcoded gets its real tier, whoever owns it.
    """
    if listeners is None:
        return

    first_time = song.artist_monthly_listeners is None
    song.artist_monthly_listeners = listeners

    if first_time:
        UserInventory.query.filter_by(spotify_song_id=song.spotify_song_id).update(
            {'rarity_tier': assign_rarity(listeners)}
        )
```

The reveal code calls it and then reads the rarity back from the song, so a
failed fetch falls back to the last known number:

```python
store_listeners(song_details, artist_listeners[artist_id])

# If the fetch failed this falls back to the last number we stored
new_inventory_item = UserInventory(
    user_id=current_user.id,
    spotify_song_id=track_id,
    rarity_tier=assign_rarity(song_details.artist_monthly_listeners)
)
```

Note the `first_time` check: a rarity is only rewritten for songs that never
had a number. Once a song has been properly rated the tier in someone's
inventory is not changed again, even if the artist grows later.

After the fix: `24 passed`.

#### 3c. An old crash on the session-expired path

Not caused by this stage, but found by it. I wrote a test for the "Spotify
session expired" branch at the top of `daily_pool()` because the new code sits
right below it. Against the original `pool.py`:

```
    def daily_pool():
        # 1. Ensure token is fresh before talking to Spotify
        access_token = get_valid_access_token(current_user)
        if not access_token:
>           flash("Spotify session expired. Please log in again.", "error")
            ^^^^^
E       NameError: name 'flash' is not defined
app/routes/pool.py:20: NameError
```

`flash` was used but never imported, so the branch that is supposed to give a
clean re-login was itself a 500 error. It only runs when a token refresh
fails, which is why it had not shown up before. Fix is one word on the import
line:

```python
from flask import Blueprint, render_template, flash
```

#### 3d. Songs Spotify cannot find blocked the whole re-rate queue

The tests all passed at this point, so I ran the home page against a copy of
the real database (`instance/sonora.db` copied to a temp file, Spotify still
faked) to see the re-rate work through the actual 58 songs. Normal case, three
page loads:

```
  inventory tiers: [(1, 'Common', 58)]
  songs with listeners: 0 | with album_total_tracks: 0
load 1 status 200 calls so far {'track': 10, 'artist': 10}
  songs with listeners: 10 | with album_total_tracks: 0
load 2 status 200 calls so far {'track': 20, 'artist': 20}
  songs with listeners: 20 | with album_total_tracks: 0
load 3 status 200 calls so far {'track': 30, 'artist': 30}
  songs with listeners: 30 | with album_total_tracks: 0
```

Ten songs per load, as intended. Then the same run again, but with the track
request failing for the first 10 inventory songs, which is what happens if
Spotify has removed a track since it was collected:

```
  inventory tiers: [(1, 'Common', 58)]
  songs with listeners: 0 | with album_total_tracks: 0
load 1 status 200 calls so far {'track': 10, 'artist': 0}
  inventory tiers: [(1, 'Common', 58)]
  songs with listeners: 0 | with album_total_tracks: 0
load 2 status 200 calls so far {'track': 20, 'artist': 0}
  inventory tiers: [(1, 'Common', 58)]
  songs with listeners: 0 | with album_total_tracks: 0
load 3 status 200 calls so far {'track': 30, 'artist': 0}
  inventory tiers: [(1, 'Common', 58)]
  songs with listeners: 0 | with album_total_tracks: 0
```

No error anywhere, the page returns 200 every time, and nothing ever gets
rated. The query takes the first 10 unrated songs, all 10 fail, they stay
unrated, and the next page load picks the same 10 again. The other 48 songs
are never reached, and 10 requests are wasted on every page load forever. No
unit test caught this because none of them had a full batch of failing songs.

Fix: take the batch in random order, so failing songs cannot hold the front
of the queue.

```python
        # Random order, so a song Spotify cannot find any more does not sit at
        # the front of the queue forever and block everything behind it
        .order_by(func.random())
        .limit(RERATE_BATCH_SIZE)
```

Same run after the fix, 12 page loads:

```
load 12 status 200 calls so far {'track': 120, 'artist': 48}
  inventory tiers: [(1, 'Common', 45), (1, 'Epic', 1), (1, 'Rare', 12)]
  songs with listeners: 48 | with album_total_tracks: 0
```

48 of 58 rated, which is all of them except the 10 that cannot be found. A
test for this case was added (`test_dead_tracks_do_not_block_the_rerate_queue`).
The dead songs are still retried on each load, which costs up to 10 wasted
requests; acceptable for now, noted under known issues.

(The tiers in that output mean nothing. The fake Spotify returns made-up
listener counts.)

#### 3e. Album sizes for old songs

The same output shows `with album_total_tracks: 0` after every load. Album
sizes are only saved when a pool is generated, so songs that have dropped out
of the user's top tracks would never get one and their album would keep
showing 100% in the vault. The re-rate already fetches the full track for
those songs, and the track includes the album, so it now saves the size while
it is there:

```python
        # The track also tells us the album size, which these old rows are missing too
        if song.album_total_tracks is None:
            song.album_total_tracks = track.get('album', {}).get('total_tracks')
```

---

### 4. Album percentages in the vault

No change was needed in `vault.py`. It already reads `album_total_tracks` and
only falls back to owned/owned when the column is NULL (the stopgap from 3.3).
With the column populated the real percentage appears. Checked with a test
that collects 1 song from a 12 track album and loads `/vault/`: the page shows
`1/12` and `8%`.

The fallback stays in place for albums whose size is still unknown.

---

### Result

```
..........................                                               [100%]
26 passed in 1.51s
```

| # | Test | Type | Expected | Result |
|---|------|------|----------|--------|
| 1 | `assign_rarity` with 500 / 5000 / 50000 / 5000000 | Functional | Legendary / Epic / Rare / Common | Pass |
| 2 | `assign_rarity` at 0, 999, 1000, 9999, 10000, 99999, 100000 | Boundary | Tier changes exactly at each threshold | Pass |
| 3 | `assign_rarity(None)` | Erroneous | Common | FIRST RUN: TypeError. Pass after fix (1) |
| 4 | Artist lookup, normal response | Functional | Follower total returned | Pass |
| 5 | Artist lookup, request fails (429) | Erroneous | None, no crash | FIRST RUN: TypeError. Pass after fix (2) |
| 6 | Artist lookup, no `followers` field | Erroneous | None, no crash | FIRST RUN: KeyError. Pass after fix (2) |
| 7 | Pool generation saves `album_total_tracks` | Functional | 12 and 9 stored | Pass |
| 8 | Pool generation fills in a song saved before this stage | Functional | NULL becomes 12 | Pass |
| 9 | Reveal three songs by artists of 400 / 45,000 / 9,000,000 | Functional | Legendary / Rare / Common | Pass |
| 10 | Two reveals by the same artist in one load | Functional | One artist request | Pass |
| 11 | Reveal when Spotify gives no number | Erroneous | Page loads, song is Common | Pass |
| 12 | Failed lookup on a song with a stored number | Erroneous | Stored number kept, tier from it | FIRST RUN: number wiped. Pass after fix (3a) |
| 13 | Old hardcoded-Common song gets re-rated | Functional | Legendary, album size filled | Pass |
| 14 | Old song owned by two users | Functional | Both copies re-rated | FIRST RUN: second owner left Common. Pass after fix (3b) |
| 15 | Full batch of songs Spotify cannot find | Erroneous | Other songs still get rated | Found on real data copy (3d). Pass after fix |
| 16 | Home page with a dead Spotify session | Erroneous | Redirect to login | Original code: NameError. Pass after fix (3c) |
| 17 | Vault with 1 of 12 album songs | Functional | `1/12`, `8%` | Pass |

### Still to check on a real login

Everything above ran against fake Spotify responses. On the first real run:

1. Reveal a song and check its rarity in the vault. If **every** new song is
   Common regardless of artist, Spotify is not sending `followers` to this app
   (section 0) and rarity needs a different data source. That is a design
   decision, not a bug fix.
2. Reload the home page a few times and check the old songs in the vault start
   changing tier, about 10 per load.
3. Check an album card in the vault shows a real total (e.g. 3/12) instead of
   100%.
4. Look at the spread of tiers. If nearly everything is Common, the thresholds
   need raising for follower counts.

### Known issues carried forward

- The "listener count" is the follower count (section 0). Thresholds are not
  tuned for it yet.
- Songs Spotify no longer has are retried by the re-rate on every home page
  load (3d).
- The re-rate adds up to 20 Spotify requests to a home page load while there
  are still old songs to rate. It stops by itself once they are all done.
- If the album size is unknown the vault still shows the album as 100% (3.3
  stopgap).
- Album size as a secondary rarity factor: not implemented, still undecided.
- `pytest` is not in `requirements.txt`. That file is saved as UTF-16, which
  `pip install -r` on Linux/Mac will not read, so I left it alone rather than
  re-encode it as part of this stage.
- `instance/sonora.db` is committed to the repository and contains real
  Spotify access and refresh tokens for two accounts. It should be removed
  from git and added to a `.gitignore`.
