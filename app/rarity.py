# Rarity Assignment Module (design section 2.4.4 / Algorithm 2)
#
# The tier is decided by how big the artist is: the smaller the audience,
# the rarer the song.

LEGENDARY_THRESHOLD = 1000
EPIC_THRESHOLD = 10000
RARE_THRESHOLD = 100000


def assign_rarity(listeners):
    """Return the rarity tier for an artist with this many listeners.

    listeners is None when Spotify gave us no number for the artist. An
    unknown artist is treated as Common so nobody gets a free Legendary
    out of missing data.
    """
    if listeners is None:
        return 'Common'
    if listeners < LEGENDARY_THRESHOLD:
        return 'Legendary'
    elif listeners < EPIC_THRESHOLD:
        return 'Epic'
    elif listeners < RARE_THRESHOLD:
        return 'Rare'
    else:
        return 'Common'
