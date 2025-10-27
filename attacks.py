from typing import List

WHITE, BLACK = 0, 1

KNIGHT_DELTAS = [
    (-2, -1), (-2, 1), (-1, -2), (-1, 2),
    (1, -2), (1, 2), (2, -1), (2, 1),
]
KING_DELTAS = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
]

# Precomputed masks
KNIGHT_ATTACKS: List[int] = [0] * 64
KING_ATTACKS: List[int] = [0] * 64
PAWN_ATTACKS = [[0] * 64 for _ in range(2)]  # [side][sq]


def _sq(file_idx: int, rank_idx: int) -> int:
    return rank_idx * 8 + file_idx


def _in_board(file_idx: int, rank_idx: int) -> bool:
    return 0 <= file_idx < 8 and 0 <= rank_idx < 8


for sq in range(64):
    f = sq % 8
    r = sq // 8
    # Knight
    mask = 0
    for df, dr in KNIGHT_DELTAS:
        nf, nr = f + df, r + dr
        if _in_board(nf, nr):
            mask |= 1 << _sq(nf, nr)
    KNIGHT_ATTACKS[sq] = mask
    # King
    mask = 0
    for df, dr in KING_DELTAS:
        nf, nr = f + df, r + dr
        if _in_board(nf, nr):
            mask |= 1 << _sq(nf, nr)
    KING_ATTACKS[sq] = mask
    # Pawn attacks
    # White: up-left, up-right
    wm = 0
    if r + 1 < 8:
        if f - 1 >= 0:
            wm |= 1 << _sq(f - 1, r + 1)
        if f + 1 < 8:
            wm |= 1 << _sq(f + 1, r + 1)
    PAWN_ATTACKS[WHITE][sq] = wm
    # Black: down-left, down-right
    bm = 0
    if r - 1 >= 0:
        if f - 1 >= 0:
            bm |= 1 << _sq(f - 1, r - 1)
        if f + 1 < 8:
            bm |= 1 << _sq(f + 1, r - 1)
    PAWN_ATTACKS[BLACK][sq] = bm


def rook_attacks(sq: int, occ: int) -> int:
    attacks = 0
    f = sq % 8
    r = sq // 8
    # East
    for nf in range(f + 1, 8):
        nsq = _sq(nf, r)
        attacks |= 1 << nsq
        if (occ >> nsq) & 1:
            break
    # West
    for nf in range(f - 1, -1, -1):
        nsq = _sq(nf, r)
        attacks |= 1 << nsq
        if (occ >> nsq) & 1:
            break
    # North
    for nr in range(r + 1, 8):
        nsq = _sq(f, nr)
        attacks |= 1 << nsq
        if (occ >> nsq) & 1:
            break
    # South
    for nr in range(r - 1, -1, -1):
        nsq = _sq(f, nr)
        attacks |= 1 << nsq
        if (occ >> nsq) & 1:
            break
    return attacks


def bishop_attacks(sq: int, occ: int) -> int:
    attacks = 0
    f = sq % 8
    r = sq // 8
    # NE
    nf, nr = f + 1, r + 1
    while _in_board(nf, nr):
        nsq = _sq(nf, nr)
        attacks |= 1 << nsq
        if (occ >> nsq) & 1:
            break
        nf += 1
        nr += 1
    # NW
    nf, nr = f - 1, r + 1
    while _in_board(nf, nr):
        nsq = _sq(nf, nr)
        attacks |= 1 << nsq
        if (occ >> nsq) & 1:
            break
        nf -= 1
        nr += 1
    # SE
    nf, nr = f + 1, r - 1
    while _in_board(nf, nr):
        nsq = _sq(nf, nr)
        attacks |= 1 << nsq
        if (occ >> nsq) & 1:
            break
        nf += 1
        nr -= 1
    # SW
    nf, nr = f - 1, r - 1
    while _in_board(nf, nr):
        nsq = _sq(nf, nr)
        attacks |= 1 << nsq
        if (occ >> nsq) & 1:
            break
        nf -= 1
        nr -= 1
    return attacks


def queen_attacks(sq: int, occ: int) -> int:
    return rook_attacks(sq, occ) | bishop_attacks(sq, occ)