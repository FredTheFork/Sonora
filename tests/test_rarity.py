import pytest
from app.rarity import assign_rarity


# The four worked examples from the design (Algorithm 2)
@pytest.mark.parametrize('listeners, expected', [
    (500, 'Legendary'),
    (5000, 'Epic'),
    (50000, 'Rare'),
    (5000000, 'Common'),
])
def test_design_examples(listeners, expected):
    assert assign_rarity(listeners) == expected


# Boundary values either side of every threshold
@pytest.mark.parametrize('listeners, expected', [
    (0, 'Legendary'),
    (999, 'Legendary'),
    (1000, 'Epic'),
    (9999, 'Epic'),
    (10000, 'Rare'),
    (99999, 'Rare'),
    (100000, 'Common'),
])
def test_boundaries(listeners, expected):
    assert assign_rarity(listeners) == expected


# Spotify does not always give us a number for the artist
def test_unknown_listener_count():
    assert assign_rarity(None) == 'Common'
