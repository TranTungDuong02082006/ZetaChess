from typing import Optional
from dataclasses import dataclass

from .zobrist import Zobrist
from .eval import eval_components, apply_move_eval_delta

WHITE, BLACK = 0, 1

# Piece indices: 0..11 (WP, WN, WB, WR, WQ, WK, BP, BN, BB, BR, BQ, BK)
PIECE_TO_INDEX = {
    'P': 0, 'N': 1, 'B': 2, 'R': 3, 'Q': 4, 'K': 5,
    'p': 6, 'n': 7, 'b': 8, 'r': 9, 'q': 10, 'k': 11,
}
INDEX_TO_PIECE_CHAR = {
    0: 'P', 1: 'N', 2: 'B', 3: 'R', 4: 'Q', 5: 'K',
    6: 'p', 7: 'n', 8: 'b', 9: 'r', 10: 'q', 11: 'k',
}

# Castling rights bit flags
CR_WK, CR_WQ, CR_BK, CR_BQ = 1, 2, 4, 8

@dataclass
class UndoEntry:
    move: 'Move'
    prev_ep_square: Optional[int]
    prev_castling_rights: int
    prev_halfmove_clock: int
    prev_fullmove_number: int
    prev_zobrist: int
    prev_mg: int
    prev_eg: int
    prev_phase: int
    prev_side_to_move: int


def _square_index(file_idx: int, rank_idx: int) -> int:
    return (rank_idx - 1) * 8 + file_idx


def _parse_square(sq: str) -> int:
    file_idx = ord(sq[0]) - ord('a')
    rank_idx = int(sq[1])
    return _square_index(file_idx, rank_idx)


class Position:
    __slots__ = (
        'bitboards', 'white_occupancy', 'black_occupancy', 'all_occupancy',
        'side_to_move', 'castling_rights', 'ep_square', 'halfmove_clock',
        'fullmove_number', 'zobrist_table', 'zobrist', 'mg', 'eg', 'phase',
        'move_stack'
    )

    def __init__(self):
        self.bitboards = [0] * 12
        self.white_occupancy = 0
        self.black_occupancy = 0
        self.all_occupancy = 0
        self.side_to_move = WHITE
        self.castling_rights = 0
        self.ep_square: Optional[int] = None
        self.halfmove_clock = 0
        self.fullmove_number = 1
        self.zobrist_table = Zobrist()
        self.zobrist = 0
        self.mg = 0
        self.eg = 0
        self.phase = 0
        self.move_stack = []

    @classmethod
    def from_fen(cls, fen: str) -> 'Position':
        pos = cls()
        parts = fen.strip().split()
        if len(parts) != 6:
            raise ValueError('Invalid FEN: expected 6 space-separated fields')
        placement, stm, castling, ep, halfmove, fullmove = parts

        # Piece placement
        rank = 8
        file_idx = 0
        for ch in placement:
            if ch == '/':
                rank -= 1
                file_idx = 0
                continue
            if ch.isdigit():
                file_idx += int(ch)
                continue
            if ch not in PIECE_TO_INDEX:
                raise ValueError(f'Invalid FEN piece: {ch}')
            sq = _square_index(file_idx, rank)
            self_idx = PIECE_TO_INDEX[ch]
            pos.bitboards[self_idx] |= (1 << sq)
            file_idx += 1

        # Side to move
        pos.side_to_move = WHITE if stm == 'w' else BLACK

        # Castling rights
        cr = 0
        if castling != '-':
            if 'K' in castling:
                cr |= CR_WK
            if 'Q' in castling:
                cr |= CR_WQ
            if 'k' in castling:
                cr |= CR_BK
            if 'q' in castling:
                cr |= CR_BQ
        pos.castling_rights = cr

        # En passant
        pos.ep_square = None if ep == '-' else _parse_square(ep)

        # Clocks
        pos.halfmove_clock = int(halfmove)
        pos.fullmove_number = int(fullmove)

        # Occupancies
        pos.white_occupancy = (
            pos.bitboards[0] | pos.bitboards[1] | pos.bitboards[2] |
            pos.bitboards[3] | pos.bitboards[4] | pos.bitboards[5]
        )
        pos.black_occupancy = (
            pos.bitboards[6] | pos.bitboards[7] | pos.bitboards[8] |
            pos.bitboards[9] | pos.bitboards[10] | pos.bitboards[11]
        )
        pos.all_occupancy = pos.white_occupancy | pos.black_occupancy

        # Zobrist
        pos.zobrist = pos.zobrist_table.compute(pos)
        # Eval components
        pos.mg, pos.eg, pos.phase = eval_components(pos)
        return pos

    def to_fen(self) -> str:
        rows = []
        for rank in range(8, 0, -1):
            empties = 0
            row = []
            for file_idx in range(8):
                sq = _square_index(file_idx, rank)
                ch = None
                for p in range(12):
                    if (self.bitboards[p] >> sq) & 1:
                        ch = INDEX_TO_PIECE_CHAR[p]
                        break
                if ch is None:
                    empties += 1
                else:
                    if empties:
                        row.append(str(empties))
                        empties = 0
                    row.append(ch)
            if empties:
                row.append(str(empties))
            rows.append(''.join(row))
        placement = '/'.join(rows)
        stm = 'w' if self.side_to_move == WHITE else 'b'
        castling = self._castling_string()
        ep = '-' if self.ep_square is None else self._square_name(self.ep_square)
        return f"{placement} {stm} {castling} {ep} {self.halfmove_clock} {self.fullmove_number}"

    def _square_name(self, sq: int) -> str:
        file_idx = sq % 8
        rank_idx = sq // 8 + 1
        return chr(ord('a') + file_idx) + str(rank_idx)

    def _castling_string(self) -> str:
        if self.castling_rights == 0:
            return '-'
        s = ''
        if self.castling_rights & CR_WK:
            s += 'K'
        if self.castling_rights & CR_WQ:
            s += 'Q'
        if self.castling_rights & CR_BK:
            s += 'k'
        if self.castling_rights & CR_BQ:
            s += 'q'
        return s
    def piece_at(self, sq: int):
        for p in range(12):
            if (self.bitboards[p] >> sq) & 1:
                return p

    def clone(self) -> 'Position':
        c = Position()
        c.bitboards = self.bitboards[:]
        c.white_occupancy = self.white_occupancy
        c.black_occupancy = self.black_occupancy
        c.all_occupancy = self.all_occupancy
        c.side_to_move = self.side_to_move
        c.castling_rights = self.castling_rights
        c.ep_square = self.ep_square
        c.halfmove_clock = self.halfmove_clock
        c.fullmove_number = self.fullmove_number
        c.zobrist_table = self.zobrist_table
        c.zobrist = self.zobrist
        c.mg = self.mg
        c.eg = self.eg
        c.phase = self.phase
        # Note: move_stack not cloned for pure position snapshot
        return c

    def make_move(self, mv):
        table = self.zobrist_table
        side = self.side_to_move
        # Save undo snapshot
        undo = UndoEntry(
            move=mv,
            prev_ep_square=self.ep_square,
            prev_castling_rights=self.castling_rights,
            prev_halfmove_clock=self.halfmove_clock,
            prev_fullmove_number=self.fullmove_number,
            prev_zobrist=self.zobrist,
            prev_mg=self.mg,
            prev_eg=self.eg,
            prev_phase=self.phase,
            prev_side_to_move=side,
        )
        self.move_stack.append(undo)

        # Remove EP from Zobrist
        if self.ep_square is not None:
            self.zobrist ^= table.ep_file_keys[self.ep_square % 8]
        self.ep_square = None

        from_bit = 1 << mv.from_sq
        to_bit = 1 << mv.to_sq

        # Zobrist: toggle moving piece from square
        self.zobrist ^= table.piece_square[mv.piece][mv.from_sq]
        # Remove moving piece
        self.bitboards[mv.piece] &= ~from_bit

        # Handle captures
        if mv.is_en_passant:
            if side == WHITE:
                cap_sq = mv.to_sq - 8
                self.bitboards[6] &= ~(1 << cap_sq)
                self.zobrist ^= table.piece_square[6][cap_sq]
            else:
                cap_sq = mv.to_sq + 8
                self.bitboards[0] &= ~(1 << cap_sq)
                self.zobrist ^= table.piece_square[0][cap_sq]
        elif mv.capture_piece is not None:
            self.bitboards[mv.capture_piece] &= ~to_bit
            self.zobrist ^= table.piece_square[mv.capture_piece][mv.to_sq]

        # Place moving or promoted piece
        dst_piece = mv.promotion if mv.promotion is not None else mv.piece
        self.bitboards[dst_piece] |= to_bit
        self.zobrist ^= table.piece_square[dst_piece][mv.to_sq]

        # Castling rook move
        if mv.is_castling:
            if side == WHITE:
                if mv.to_sq == 6:  # e1->g1
                    self.bitboards[3] &= ~(1 << 7)
                    self.bitboards[3] |= (1 << 5)
                    self.zobrist ^= table.piece_square[3][7]
                    self.zobrist ^= table.piece_square[3][5]
                else:  # e1->c1
                    self.bitboards[3] &= ~(1 << 0)
                    self.bitboards[3] |= (1 << 3)
                    self.zobrist ^= table.piece_square[3][0]
                    self.zobrist ^= table.piece_square[3][3]
            else:
                if mv.to_sq == 62:  # e8->g8
                    self.bitboards[9] &= ~(1 << 63)
                    self.bitboards[9] |= (1 << 61)
                    self.zobrist ^= table.piece_square[9][63]
                    self.zobrist ^= table.piece_square[9][61]
                else:  # e8->c8
                    self.bitboards[9] &= ~(1 << 56)
                    self.bitboards[9] |= (1 << 59)
                    self.zobrist ^= table.piece_square[9][56]
                    self.zobrist ^= table.piece_square[9][59]

        # Update castling rights and Zobrist toggles
        prev_cr = self.castling_rights
        cr = prev_cr
        if side == WHITE:
            if mv.piece == 5:
                cr &= ~(CR_WK | CR_WQ)
            elif mv.piece == 3:
                if mv.from_sq == 0:
                    cr &= ~CR_WQ
                elif mv.from_sq == 7:
                    cr &= ~CR_WK
            if mv.capture_piece == 9:
                if mv.to_sq == 56:
                    cr &= ~CR_BQ
                elif mv.to_sq == 63:
                    cr &= ~CR_BK
        else:
            if mv.piece == 11:
                cr &= ~(CR_BK | CR_BQ)
            elif mv.piece == 9:
                if mv.from_sq == 56:
                    cr &= ~CR_BQ
                elif mv.from_sq == 63:
                    cr &= ~CR_BK
            if mv.capture_piece == 3:
                if mv.to_sq == 0:
                    cr &= ~CR_WQ
                elif mv.to_sq == 7:
                    cr &= ~CR_WK
        # Toggle changed castling rights in Zobrist
        def _toggle_cr(bit: int, key_idx: int):
            if (prev_cr & bit) != (cr & bit):
                self.zobrist ^= table.castling_keys[key_idx]
        _toggle_cr(CR_WK, 0)
        _toggle_cr(CR_WQ, 1)
        _toggle_cr(CR_BK, 2)
        _toggle_cr(CR_BQ, 3)
        self.castling_rights = cr

        # Set EP square after double push (and Zobrist)
        if mv.is_double_push:
            if side == WHITE:
                self.ep_square = mv.from_sq + 8
            else:
                self.ep_square = mv.from_sq - 8
            self.zobrist ^= table.ep_file_keys[self.ep_square % 8]

        # Update occupancies
        self.white_occupancy = (
            self.bitboards[0] | self.bitboards[1] | self.bitboards[2] |
            self.bitboards[3] | self.bitboards[4] | self.bitboards[5]
        )
        self.black_occupancy = (
            self.bitboards[6] | self.bitboards[7] | self.bitboards[8] |
            self.bitboards[9] | self.bitboards[10] | self.bitboards[11]
        )
        self.all_occupancy = self.white_occupancy | self.black_occupancy

        # Clocks
        if mv.piece in (0, 6) or mv.capture_piece is not None or mv.is_en_passant:
            self.halfmove_clock = 0
        else:
            self.halfmove_clock += 1
        if side == BLACK:
            self.fullmove_number += 1

        # Incremental eval components update (material/PST/phase)
        self.mg, self.eg, self.phase = apply_move_eval_delta(self, mv, self.mg, self.eg, self.phase)

        # Toggle side in Zobrist and state
        self.side_to_move = 1 - side
        self.zobrist ^= table.side

    def undo_move(self):
        if not self.move_stack:
            raise IndexError('No moves to undo')
        u = self.move_stack.pop()
        mv = u.move
        side = u.prev_side_to_move

        from_bit = 1 << mv.from_sq
        to_bit = 1 << mv.to_sq

        # Reverse castling rook move
        if mv.is_castling:
            if side == WHITE:
                if mv.to_sq == 6:
                    self.bitboards[3] &= ~(1 << 5)
                    self.bitboards[3] |= (1 << 7)
                else:
                    self.bitboards[3] &= ~(1 << 3)
                    self.bitboards[3] |= (1 << 0)
            else:
                if mv.to_sq == 62:
                    self.bitboards[9] &= ~(1 << 61)
                    self.bitboards[9] |= (1 << 63)
                else:
                    self.bitboards[9] &= ~(1 << 59)
                    self.bitboards[9] |= (1 << 56)

        # Remove moved piece from destination (promotion-aware)
        dst_piece = mv.promotion if mv.promotion is not None else mv.piece
        self.bitboards[dst_piece] &= ~to_bit

        # Restore captured piece
        if mv.is_en_passant:
            if side == WHITE:
                cap_sq = mv.to_sq - 8
                self.bitboards[6] |= (1 << cap_sq)
            else:
                cap_sq = mv.to_sq + 8
                self.bitboards[0] |= (1 << cap_sq)
        elif mv.capture_piece is not None:
            self.bitboards[mv.capture_piece] |= to_bit

        # Restore moving piece to from_sq
        self.bitboards[mv.piece] |= from_bit

        # Restore state from undo snapshot
        self.ep_square = u.prev_ep_square
        self.castling_rights = u.prev_castling_rights
        self.halfmove_clock = u.prev_halfmove_clock
        self.fullmove_number = u.prev_fullmove_number
        self.side_to_move = u.prev_side_to_move

        # Recompute occupancies
        self.white_occupancy = (
            self.bitboards[0] | self.bitboards[1] | self.bitboards[2] |
            self.bitboards[3] | self.bitboards[4] | self.bitboards[5]
        )
        self.black_occupancy = (
            self.bitboards[6] | self.bitboards[7] | self.bitboards[8] |
            self.bitboards[9] | self.bitboards[10] | self.bitboards[11]
        )
        self.all_occupancy = self.white_occupancy | self.black_occupancy

        # Restore eval components and Zobrist
        self.mg = u.prev_mg
        self.eg = u.prev_eg
        self.phase = u.prev_phase
        self.zobrist = u.prev_zobrist