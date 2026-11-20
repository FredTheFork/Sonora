# Rarity Assignment Module (replaces design section 2.4.4 / Algorithm 2)
#
# The tier is decided by how many Sonora users have the song: the fewer
# people who own it, the rarer it is.

LEGENDARY_THRESHOLD = 2
EPIC_THRESHOLD = 5
RARE_THRESHOLD = 15


def assign_rarity(owner_count):
    """Return the rarity tier for a song owned by this many Sonora users.

    owner_count counts every inventory row for the song, including the user
    who just collected it. Anything we cannot count is treated as Common so
    nobody gets a free Legendary out of a missing number.
    """
    if owner_count is None:
        return 'Common'
    if owner_count <= LEGENDARY_THRESHOLD:
        return 'Legendary'
    elif owner_count <= EPIC_THRESHOLD:
        return 'Epic'
    elif owner_count <= RARE_THRESHOLD:
        return 'Rare'
    else:
        return 'Common'
