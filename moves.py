from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

from constants import WHITE, BLACK, CR_WK, CR_WQ, CR_BK, CR_BQ
from attacks import KNIGHT_ATTACKS, KING_ATTACKS, PAWN_ATTACKS, rook_attacks, bishop_attacks, queen_attacks

if TYPE_CHECKING:
    from .position import Position


@dataclass(frozen=True)
class Move:
    from_sq: int
    to_sq: int
    piece: int
    capture_piece: Optional[int] = None
    promotion: Optional[int] = None
    is_en_passant: bool = False
    is_castling: bool = False
    is_double_push: bool = False

def _iter_bits(bb: int):
    while bb:
        lsb = bb & -bb
        sq = lsb.bit_length() - 1
        yield sq
        bb &= bb - 1


def _piece_at(pos: 'Position', sq: int) -> Optional[int]:
    return pos.piece_at(sq)


def is_square_attacked_by(side: int, sq: int, pos: 'Position') -> bool:
    occ = pos.all_occupancy
    # Pawns
    if side == WHITE:
        # White pawns attack upward, so sources are down-left/down-right from sq
        r = sq // 8
        f = sq % 8
        if r > 0:
            if f > 0 and ((pos.bitboards[0] >> (sq - 9)) & 1):
                return True
            if f < 7 and ((pos.bitboards[0] >> (sq - 7)) & 1):
                return True
    else:
        r = sq // 8
        f = sq % 8
        if r < 7:
            if f > 0 and ((pos.bitboards[6] >> (sq + 7)) & 1):
                return True
            if f < 7 and ((pos.bitboards[6] >> (sq + 9)) & 1):
                return True
    # Knights
    if side == WHITE:
        if KNIGHT_ATTACKS[sq] & pos.bitboards[1]:
            return True
    else:
        if KNIGHT_ATTACKS[sq] & pos.bitboards[7]:
            return True
    # King
    if side == WHITE:
        if KING_ATTACKS[sq] & pos.bitboards[5]:
            return True
    else:
        if KING_ATTACKS[sq] & pos.bitboards[11]:
            return True
    # Diagonals (bishops/queens)
    diag = bishop_attacks(sq, occ)
    if side == WHITE:
        if diag & (pos.bitboards[2] | pos.bitboards[4]):
            return True
    else:
        if diag & (pos.bitboards[8] | pos.bitboards[10]):
            return True
    # Orthogonals (rooks/queens)
    ortho = rook_attacks(sq, occ)
    if side == WHITE:
        if ortho & (pos.bitboards[3] | pos.bitboards[4]):
            return True
    else:
        if ortho & (pos.bitboards[9] | pos.bitboards[10]):
            return True
    return False


def _own_occ(pos: 'Position') -> int:
    return pos.white_occupancy if pos.side_to_move == WHITE else pos.black_occupancy


def _opp_occ(pos: 'Position') -> int:
    return pos.black_occupancy if pos.side_to_move == WHITE else pos.white_occupancy


PROMOTION_MAP = {
    WHITE: [4, 3, 2, 1],  # Q, R, B, N
    BLACK: [10, 9, 8, 7],  # q, r, b, n
}


def generate_pseudo_legal_moves(pos: 'Position') -> List[Move]:
    moves: List[Move] = []
    side = pos.side_to_move
    own = _own_occ(pos)
    opp = _opp_occ(pos)
    occ = pos.all_occupancy

    # Pawns
    if side == WHITE:
        pawns = pos.bitboards[0]
        for sq in _iter_bits(pawns):
            r = sq // 8
            # Push
            to1 = sq + 8
            if to1 < 64 and not ((occ >> to1) & 1):
                if r == 6:  # promotion rank (moving to rank 8)
                    for promo in PROMOTION_MAP[WHITE]:
                        moves.append(Move(sq, to1, 0, promotion=promo))
                else:
                    moves.append(Move(sq, to1, 0))
                    # Double push
                    if r == 1:
                        to2 = sq + 16
                        if not ((occ >> to2) & 1):
                            moves.append(Move(sq, to2, 0, is_double_push=True))
            # Captures
            for dest in [sq + 7, sq + 9]:
                if 0 <= dest < 64:
                    df = abs((dest % 8) - (sq % 8))
                    if df == 1 and ((opp >> dest) & 1):
                        cap = _piece_at(pos, dest)
                        if r == 6:
                            for promo in PROMOTION_MAP[WHITE]:
                                moves.append(Move(sq, dest, 0, capture_piece=cap, promotion=promo))
                        else:
                            moves.append(Move(sq, dest, 0, capture_piece=cap))
            # En passant
            if pos.ep_square is not None:
                if pos.ep_square in [sq + 7, sq + 9] and abs((pos.ep_square % 8) - (sq % 8)) == 1:
                    moves.append(Move(sq, pos.ep_square, 0, capture_piece=6, is_en_passant=True))
    else:
        pawns = pos.bitboards[6]
        for sq in _iter_bits(pawns):
            r = sq // 8
            # Push
            to1 = sq - 8
            if to1 >= 0 and not ((occ >> to1) & 1):
                if r == 1:  # promotion rank (moving to rank 1)
                    for promo in PROMOTION_MAP[BLACK]:
                        moves.append(Move(sq, to1, 6, promotion=promo))
                else:
                    moves.append(Move(sq, to1, 6))
                    # Double push
                    if r == 6:
                        to2 = sq - 16
                        if to2 >= 0 and not ((occ >> to2) & 1):
                            moves.append(Move(sq, to2, 6, is_double_push=True))
            # Captures
            for dest in [sq - 7, sq - 9]:
                if 0 <= dest < 64:
                    df = abs((dest % 8) - (sq % 8))
                    if df == 1 and ((opp >> dest) & 1):
                        cap = _piece_at(pos, dest)
                        if r == 1:
                            for promo in PROMOTION_MAP[BLACK]:
                                moves.append(Move(sq, dest, 6, capture_piece=cap, promotion=promo))
                        else:
                            moves.append(Move(sq, dest, 6, capture_piece=cap))
            # En passant
            if pos.ep_square is not None:
                if pos.ep_square in [sq - 7, sq - 9] and abs((pos.ep_square % 8) - (sq % 8)) == 1:
                    moves.append(Move(sq, pos.ep_square, 6, capture_piece=0, is_en_passant=True))

    # Knights
    knights = pos.bitboards[1 if side == WHITE else 7]
    for sq in _iter_bits(knights):
        dests = KNIGHT_ATTACKS[sq] & ~own
        for dest in _iter_bits(dests):
            cap = _piece_at(pos, dest) if ((opp >> dest) & 1) else None
            moves.append(Move(sq, dest, 1 if side == WHITE else 7, capture_piece=cap))

    # Bishops
    bishops = pos.bitboards[2 if side == WHITE else 8]
    for sq in _iter_bits(bishops):
        dests = bishop_attacks(sq, occ) & ~own
        for dest in _iter_bits(dests):
            cap = _piece_at(pos, dest) if ((opp >> dest) & 1) else None
            moves.append(Move(sq, dest, 2 if side == WHITE else 8, capture_piece=cap))

    # Rooks
    rooks = pos.bitboards[3 if side == WHITE else 9]
    for sq in _iter_bits(rooks):
        dests = rook_attacks(sq, occ) & ~own
        for dest in _iter_bits(dests):
            cap = _piece_at(pos, dest) if ((opp >> dest) & 1) else None
            moves.append(Move(sq, dest, 3 if side == WHITE else 9, capture_piece=cap))

    # Queens
    queens = pos.bitboards[4 if side == WHITE else 10]
    for sq in _iter_bits(queens):
        dests = queen_attacks(sq, occ) & ~own
        for dest in _iter_bits(dests):
            cap = _piece_at(pos, dest) if ((opp >> dest) & 1) else None
            moves.append(Move(sq, dest, 4 if side == WHITE else 10, capture_piece=cap))

    # King (non-castling)
    king_sq = (pos.bitboards[5 if side == WHITE else 11]).bit_length() - 1
    dests = KING_ATTACKS[king_sq] & ~own
    for dest in _iter_bits(dests):
        cap = _piece_at(pos, dest) if ((opp >> dest) & 1) else None
        moves.append(Move(king_sq, dest, 5 if side == WHITE else 11, capture_piece=cap))

    # Castling generation
    moves.extend(_generate_castling(pos))

    return moves


def _generate_castling(pos: 'Position') -> List[Move]:
    side = pos.side_to_move
    occ = pos.all_occupancy
    moves: List[Move] = []
    if side == WHITE:
        e1, f1, g1, d1, c1, b1, a1, h1 = 4, 5, 6, 3, 2, 1, 0, 7
        # King side
        if pos.castling_rights & CR_WK:
            path_empty = not ((occ >> f1) & 1) and not ((occ >> g1) & 1)
            rook_on_h1 = ((pos.bitboards[3] >> h1) & 1) == 1
            if path_empty and rook_on_h1 and not is_square_attacked_by(BLACK, e1, pos) and not is_square_attacked_by(BLACK, f1, pos) and not is_square_attacked_by(BLACK, g1, pos):
                moves.append(Move(e1, g1, 5, is_castling=True))
        # Queen side
        if pos.castling_rights & CR_WQ:
            path_empty = not ((occ >> d1) & 1) and not ((occ >> c1) & 1) and not ((occ >> b1) & 1)
            rook_on_a1 = ((pos.bitboards[3] >> a1) & 1) == 1
            if path_empty and rook_on_a1 and not is_square_attacked_by(BLACK, e1, pos) and not is_square_attacked_by(BLACK, d1, pos) and not is_square_attacked_by(BLACK, c1, pos):
                moves.append(Move(e1, c1, 5, is_castling=True))
    else:
        e8, f8, g8, d8, c8, b8, a8, h8 = 60, 61, 62, 59, 58, 57, 56, 63
        # King side
        if pos.castling_rights & CR_BK:
            path_empty = not ((occ >> f8) & 1) and not ((occ >> g8) & 1)
            rook_on_h8 = ((pos.bitboards[9] >> h8) & 1) == 1
            if path_empty and rook_on_h8 and not is_square_attacked_by(WHITE, e8, pos) and not is_square_attacked_by(WHITE, f8, pos) and not is_square_attacked_by(WHITE, g8, pos):
                moves.append(Move(e8, g8, 11, is_castling=True))
        # Queen side
        if pos.castling_rights & CR_BQ:
            path_empty = not ((occ >> d8) & 1) and not ((occ >> c8) & 1) and not ((occ >> b8) & 1)
            rook_on_a8 = ((pos.bitboards[9] >> a8) & 1) == 1
            if path_empty and rook_on_a8 and not is_square_attacked_by(WHITE, e8, pos) and not is_square_attacked_by(WHITE, d8, pos) and not is_square_attacked_by(WHITE, c8, pos):
                moves.append(Move(e8, c8, 11, is_castling=True))
    return moves


def apply_move_clone(pos: 'Position', mv: Move) -> 'Position':
    new = pos.clone()
    side = pos.side_to_move
    # Clear EP by default; set only when double push is made
    new.ep_square = None

    from_bit = 1 << mv.from_sq
    to_bit = 1 << mv.to_sq

    # Remove moving piece
    new.bitboards[mv.piece] &= ~from_bit

    # Handle captures
    if mv.is_en_passant:
        if side == WHITE:
            cap_sq = mv.to_sq - 8
            new.bitboards[6] &= ~(1 << cap_sq)
        else:
            cap_sq = mv.to_sq + 8
            new.bitboards[0] &= ~(1 << cap_sq)
    elif mv.capture_piece is not None:
        new.bitboards[mv.capture_piece] &= ~to_bit

    # Place moving or promoted piece
    dst_piece = mv.promotion if mv.promotion is not None else mv.piece
    new.bitboards[dst_piece] |= to_bit

    # Castling: move rook
    if mv.is_castling:
        if side == WHITE:
            if mv.to_sq == 6:  # e1->g1
                # rook h1->f1
                new.bitboards[3] &= ~(1 << 7)
                new.bitboards[3] |= (1 << 5)
            else:  # e1->c1
                new.bitboards[3] &= ~(1 << 0)
                new.bitboards[3] |= (1 << 3)
        else:
            if mv.to_sq == 62:  # e8->g8
                new.bitboards[9] &= ~(1 << 63)
                new.bitboards[9] |= (1 << 61)
            else:  # e8->c8
                new.bitboards[9] &= ~(1 << 56)
                new.bitboards[9] |= (1 << 59)

    # Update castling rights (basic): moving king or rook loses rights; rook captures handled by occupancy recompute
    if side == WHITE:
        if mv.piece == 5:
            new.castling_rights &= ~(CR_WK | CR_WQ)
        elif mv.piece == 3:
            if mv.from_sq == 0:
                new.castling_rights &= ~CR_WQ
            elif mv.from_sq == 7:
                new.castling_rights &= ~CR_WK
        if mv.capture_piece == 9:  # captured black rook on a8/h8
            if mv.to_sq == 56:
                new.castling_rights &= ~CR_BQ
            elif mv.to_sq == 63:
                new.castling_rights &= ~CR_BK
    else:
        if mv.piece == 11:
            new.castling_rights &= ~(CR_BK | CR_BQ)
        elif mv.piece == 9:
            if mv.from_sq == 56:
                new.castling_rights &= ~CR_BQ
            elif mv.from_sq == 63:
                new.castling_rights &= ~CR_BK
        if mv.capture_piece == 3:
            if mv.to_sq == 0:
                new.castling_rights &= ~CR_WQ
            elif mv.to_sq == 7:
                new.castling_rights &= ~CR_WK

    # Set EP square after double pawn push
    if mv.is_double_push:
        if side == WHITE:
            new.ep_square = mv.from_sq + 8
        else:
            new.ep_square = mv.from_sq - 8

    # Update occupancies
    new.white_occupancy = (
        new.bitboards[0] | new.bitboards[1] | new.bitboards[2] |
        new.bitboards[3] | new.bitboards[4] | new.bitboards[5]
    )
    new.black_occupancy = (
        new.bitboards[6] | new.bitboards[7] | new.bitboards[8] |
        new.bitboards[9] | new.bitboards[10] | new.bitboards[11]
    )
    new.all_occupancy = new.white_occupancy | new.black_occupancy

    # Clocks
    if mv.piece in (0, 6) or mv.capture_piece is not None or mv.is_en_passant:
        new.halfmove_clock = 0
    else:
        new.halfmove_clock += 1
    if side == BLACK:
        new.fullmove_number += 1

    # Toggle side
    new.side_to_move = 1 - side

    # Zobrist recompute (simple)
    new.zobrist = new.zobrist_table.compute(new)

    return new


def generate_legal_moves(pos: 'Position') -> List[Move]:
    legal: List[Move] = []
    for mv in generate_pseudo_legal_moves(pos):
        after = apply_move_clone(pos, mv)
        # Check side not in check after move
        if after.side_to_move == WHITE:
            # we just moved BLACK
            king_sq = (after.bitboards[11]).bit_length() - 1
            if not is_square_attacked_by(WHITE, king_sq, after):
                legal.append(mv)
        else:
            king_sq = (after.bitboards[5]).bit_length() - 1
            if not is_square_attacked_by(BLACK, king_sq, after):
                legal.append(mv)
    return legal

