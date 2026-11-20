import pytest
from app.rarity import assign_rarity


# Worked examples for the in-app scarcity system
@pytest.mark.parametrize('owners, expected', [
    (1, 'Legendary'),
    (4, 'Epic'),
    (10, 'Rare'),
    (50, 'Common'),
])
def test_worked_examples(owners, expected):
    assert assign_rarity(owners) == expected


# Boundary values either side of every threshold
@pytest.mark.parametrize('owners, expected', [
    (0, 'Legendary'),
    (2, 'Legendary'),
    (3, 'Epic'),
    (5, 'Epic'),
    (6, 'Rare'),
    (15, 'Rare'),
    (16, 'Common'),
])
def test_boundaries(owners, expected):
    assert assign_rarity(owners) == expected


# A count we cannot get is treated as Common
def test_unknown_owner_count():
    assert assign_rarity(None) == 'Common'
