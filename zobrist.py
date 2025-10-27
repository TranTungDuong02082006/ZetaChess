import random


def _iter_bits(bb: int):
    while bb:
        lsb = bb & -bb
        sq = lsb.bit_length() - 1
        yield sq
        bb &= bb - 1


class Zobrist:
    def __init__(self, seed: int = 2021):
        rng = random.Random(seed)
        # 12 piece types x 64 squares
        self.piece_square = [[rng.getrandbits(64) for _ in range(64)] for _ in range(12)]
        self.side = rng.getrandbits(64)
        # Castling keys: WK, WQ, BK, BQ
        self.castling_keys = [rng.getrandbits(64) for _ in range(4)]
        # EP file keys: a..h
        self.ep_file_keys = [rng.getrandbits(64) for _ in range(8)]

    def compute(self, pos) -> int:
        h = 0
        for p in range(12):
            for sq in _iter_bits(pos.bitboards[p]):
                h ^= self.piece_square[p][sq]
        if pos.side_to_move == 1:
            h ^= self.side
        cr = pos.castling_rights
        if cr & 1:
            h ^= self.castling_keys[0]
        if cr & 2:
            h ^= self.castling_keys[1]
        if cr & 4:
            h ^= self.castling_keys[2]
        if cr & 8:
            h ^= self.castling_keys[3]
        if pos.ep_square is not None:
            h ^= self.ep_file_keys[pos.ep_square % 8]
        return h