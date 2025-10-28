from typing import Tuple

WHITE, BLACK = 0, 1
from attacks import KNIGHT_ATTACKS, KING_ATTACKS, rook_attacks, bishop_attacks, queen_attacks
from moves import is_square_attacked_by

# Piece values (centipawns) indexed by base type: P, N, B, R, Q, K
PIECE_VALUES = [100, 320, 330, 500, 900, 0]

# Phase weights (Stockfish-style, simplified)
PHASE_WEIGHTS = {
    1: 1,  # N
    2: 1,  # B
    3: 2,  # R
    4: 4,  # Q
}
MAX_PHASE = 24  # 2*(1+1+2+4) * (two sides)


def _iter_bits(bb: int):
    while bb:
        lsb = bb & -bb
        sq = lsb.bit_length() - 1
        yield sq
        bb &= bb - 1


def mirror_sq(sq: int) -> int:
    # Mirror across ranks (a1<->a8)
    return sq ^ 56


def _center_dist(f: int, r: int) -> int:
    # distance from 4 central squares d4/e4/d5/e5
    df = min(abs(f - 3), abs(f - 4))
    dr = min(abs(r - 3), abs(r - 4))
    return df + dr


def _pst_white(piece_base: int, sq: int, endgame: bool) -> int:
    f, r = sq % 8, sq // 8
    cd = _center_dist(f, r)
    if piece_base == 0:  # Pawn
        advance = r  # 0..7 (white moves up)
        return (6 if not endgame else 4) * advance - (8 if not endgame else 6)
    if piece_base == 1:  # Knight
        return (16 if endgame else 12) - 4 * cd
    if piece_base == 2:  # Bishop
        return (14 if endgame else 10) - 3 * cd
    if piece_base == 3:  # Rook
        # Prefer central files lightly
        file_center = 3.5
        return (8 if endgame else 6) - int(abs(f - file_center) * 2)
    if piece_base == 4:  # Queen
        return (8 if endgame else 6) - 2 * cd
    if piece_base == 5:  # King
        # MG: safer in corner; EG: active in center
        return ((18 - 3 * cd) if endgame else -(18 - 3 * cd))
    return 0


def pst(piece_index: int, sq: int, endgame: bool) -> int:
    base = piece_index % 6
    if piece_index <= 5:  # white piece
        return _pst_white(base, sq, endgame)
    else:
        # use mirrored square for black perspective
        return _pst_white(base, mirror_sq(sq), endgame)


def _material_score(pos) -> int:
    score = 0
    for p in range(12):
        base = p % 6
        val = PIECE_VALUES[base]
        count = 0
        bb = pos.bitboards[p]
        while bb:
            bb &= bb - 1
            count += 1
        if p <= 5:
            score += val * count
        else:
            score -= val * count
    return score


def _pst_score(pos, endgame: bool) -> int:
    s = 0
    for p in range(12):
        bb = pos.bitboards[p]
        for sq in _iter_bits(bb):
            s += pst(p, sq, endgame) if p <= 5 else -pst(p, sq, endgame)
    return s


def _mobility_score(pos) -> int:
    # Lightweight mobility for N/B/R/Q
    own = pos.white_occupancy
    opp = pos.black_occupancy
    if pos.side_to_move == BLACK:
        own, opp = opp, own
    occ = pos.all_occupancy
    def count_bits(bb: int) -> int:
        c = 0
        while bb:
            bb &= bb - 1
            c += 1
        return c
    score_w = 0
    score_b = 0
    # White
    for sq in _iter_bits(pos.bitboards[1]):  # N
        score_w += count_bits(KNIGHT_ATTACKS[sq] & ~own)
    for sq in _iter_bits(pos.bitboards[2]):
        score_w += count_bits(bishop_attacks(sq, occ) & ~own)
    for sq in _iter_bits(pos.bitboards[3]):
        score_w += count_bits(rook_attacks(sq, occ) & ~own)
    for sq in _iter_bits(pos.bitboards[4]):
        score_w += count_bits(queen_attacks(sq, occ) & ~own)
    # Black
    own_b = pos.black_occupancy
    for sq in _iter_bits(pos.bitboards[7]):
        score_b += count_bits(KNIGHT_ATTACKS[sq] & ~own_b)
    for sq in _iter_bits(pos.bitboards[8]):
        score_b += count_bits(bishop_attacks(sq, occ) & ~own_b)
    for sq in _iter_bits(pos.bitboards[9]):
        score_b += count_bits(rook_attacks(sq, occ) & ~own_b)
    for sq in _iter_bits(pos.bitboards[10]):
        score_b += count_bits(queen_attacks(sq, occ) & ~own_b)
    # weights
    return 2 * (score_w - score_b)


def _king_safety_mg(pos) -> int:
    # Penalize attacked ring squares around own king (midgame only)
    w_king_sq = (pos.bitboards[5]).bit_length() - 1
    b_king_sq = (pos.bitboards[11]).bit_length() - 1
    w_ring = KING_ATTACKS[w_king_sq]
    b_ring = KING_ATTACKS[b_king_sq]
    w_pen = 0
    b_pen = 0
    for sq in _iter_bits(w_ring):
        if is_square_attacked_by(BLACK, sq, pos):
            w_pen += 1
    for sq in _iter_bits(b_ring):
        if is_square_attacked_by(WHITE, sq, pos):
            b_pen += 1
    return -8 * (w_pen - b_pen)


def game_phase_value(pos) -> int:
    phase = 0
    # accumulate weights for both sides
    for p in range(12):
        bb = pos.bitboards[p]
        base = p % 6
        w = PHASE_WEIGHTS.get(base, 0)
        while bb:
            bb &= bb - 1
            phase += w
    if phase > MAX_PHASE:
        phase = MAX_PHASE
    return phase


def evaluate(pos) -> int:
    # Compute midgame and endgame components and blend
    mat = _material_score(pos)
    pst_mg = _pst_score(pos, endgame=False)
    pst_eg = _pst_score(pos, endgame=True)
    mob = _mobility_score(pos)
    safety = _king_safety_mg(pos)
    phase = game_phase_value(pos)  # 0..24
    mg = mat + pst_mg + mob + safety
    eg = mat + pst_eg + (mob // 2)  # lighter mobility in endgame
    # Blend: higher phase → favor MG
    score = (mg * phase + eg * (MAX_PHASE - phase)) // MAX_PHASE
    # Return from side-to-move perspective
    return score if pos.side_to_move == WHITE else -score


def eval_components(pos) -> Tuple[int, int, int]:
    mat = _material_score(pos)
    pst_mg = _pst_score(pos, endgame=False)
    pst_eg = _pst_score(pos, endgame=True)
    mob = _mobility_score(pos)
    safety = _king_safety_mg(pos)
    phase = game_phase_value(pos)
    mg = mat + pst_mg + mob + safety
    eg = mat + pst_eg + (mob // 2)
    return mg, eg, phase


def apply_move_eval_delta(pos, mv, mg: int, eg: int, phase: int) -> Tuple[int, int, int]:
    # Incremental update for material/PST/phase only (mobility/safety recomputed later)
    side = pos.side_to_move
    # helper for sign
    def add_piece(piece_index: int, sq: int, end: bool) -> Tuple[int, int]:
        v = PIECE_VALUES[piece_index % 6]
        ps = pst(piece_index, sq, end)
        if piece_index <= 5:
            return v + ps, v + pst(piece_index, sq, True)
        else:
            return -v - ps, -v - pst(piece_index, sq, True)

    def remove_piece(piece_index: int, sq: int) -> Tuple[int, int]:
        v = PIECE_VALUES[piece_index % 6]
        ps_mg = pst(piece_index, sq, False)
        ps_eg = pst(piece_index, sq, True)
        if piece_index <= 5:
            return -(v + ps_mg), -(v + ps_eg)
        else:
            return (v + ps_mg), (v + ps_eg)

    mg_delta = 0
    eg_delta = 0
    phase_delta = 0

    # Move piece from -> to
    mg_r, eg_r = remove_piece(mv.piece, mv.from_sq)
    mg_delta += mg_r
    eg_delta += eg_r
    dst_piece = mv.promotion if mv.promotion is not None else mv.piece
    mg_a, eg_a = add_piece(dst_piece, mv.to_sq, False)
    mg_delta += mg_a
    eg_delta += eg_a

    # Capture
    if mv.is_en_passant:
        if side == WHITE:
            cap_sq = mv.to_sq - 8
            mg_c, eg_c = remove_piece(6, cap_sq)
        else:
            cap_sq = mv.to_sq + 8
            mg_c, eg_c = remove_piece(0, cap_sq)
        mg_delta += mg_c
        eg_delta += eg_c
        phase_delta += PHASE_WEIGHTS.get(0, 0)
    elif mv.capture_piece is not None:
        mg_c, eg_c = remove_piece(mv.capture_piece, mv.to_sq)
        mg_delta += mg_c
        eg_delta += eg_c
        phase_delta += PHASE_WEIGHTS.get(mv.capture_piece % 6, 0)

    # Castling rook move PST adjust
    if mv.is_castling:
        if side == WHITE:
            if mv.to_sq == 6:  # e1->g1, rook h1->f1
                r_from, r_to = 7, 5
                mg_delta += pst(3, r_to, False) - pst(3, r_from, False)
                eg_delta += pst(3, r_to, True) - pst(3, r_from, True)
            else:  # e1->c1, rook a1->d1
                r_from, r_to = 0, 3
                mg_delta += pst(3, r_to, False) - pst(3, r_from, False)
                eg_delta += pst(3, r_to, True) - pst(3, r_from, True)
        else:
            if mv.to_sq == 62:  # e8->g8, rook h8->f8
                r_from, r_to = 63, 61
                mg_delta += -pst(9, r_to, False) + pst(9, r_from, False)
                eg_delta += -pst(9, r_to, True) + pst(9, r_from, True)
            else:  # e8->c8, rook a8->d8
                r_from, r_to = 56, 59
                mg_delta += -pst(9, r_to, False) + pst(9, r_from, False)
                eg_delta += -pst(9, r_to, True) + pst(9, r_from, True)

    # Promotion phase change
    if mv.promotion is not None:
        # remove pawn, add promoted piece already handled in mg/eg
        phase_delta += PHASE_WEIGHTS.get(mv.promotion % 6, 0) - PHASE_WEIGHTS.get(0, 0)

    new_mg = mg + mg_delta
    new_eg = eg + eg_delta
    new_phase = max(0, min(MAX_PHASE, phase + phase_delta))
    return new_mg, new_eg, new_phase

from typing import Optional, Tuple
from attacks import PAWN_ATTACKS, KNIGHT_ATTACKS, KING_ATTACKS, rook_attacks, bishop_attacks, queen_attacks
from constants import WHITE, BLACK

# Ánh xạ side -> (start_idx, end_idx) cho các bitboards của bên đó
SIDE_PIECES = {
    WHITE: (0, 6), # WP, WN, WB, WR, WQ, WK
    BLACK: (6, 12) # BP, BN, BB, BR, BQ, BK
}

def _get_smallest_attacker(pos, sq: int, side: int, occ: int) -> Optional[tuple[int, int]]:
    """
    Tìm quân tấn công có giá trị nhỏ nhất của 'side' đến ô 'sq',
    với 'occ' là bàn cờ (occupancy) hiện tại trong mô phỏng.
    Trả về (piece_index, from_square) hoặc None.
    Lưu ý: occ là occupancy *đã bị thay đổi* trong vòng lặp SEE.
    """
    start, end = SIDE_PIECES[side]

    # 1. Tốt (Pawns)
    pawn_idx = start
    # Lấy các đòn tấn công của Tốt (của bên đối thủ) *vào* ô sq
    attacks_to_sq = PAWN_ATTACKS[1 - side][sq] 
    attackers = attacks_to_sq & pos.bitboards[pawn_idx] & occ
    if attackers:
        # Trả về Tốt đầu tiên tìm thấy
        return pawn_idx, (attackers & -attackers).bit_length() - 1

    # 2. Mã (Knights)
    knight_idx = start + 1
    attacks_to_sq = KNIGHT_ATTACKS[sq]
    attackers = attacks_to_sq & pos.bitboards[knight_idx] & occ
    if attackers:
        return knight_idx, (attackers & -attackers).bit_length() - 1

    # 3. Tượng (Bishops) - Quân trượt
    bishop_idx = start + 2
    # Lấy các đòn tấn công *từ* ô sq, với occupancy mô phỏng
    attacks_from_sq = bishop_attacks(sq, occ)
    attackers = attacks_from_sq & pos.bitboards[bishop_idx] & occ
    if attackers:
        return bishop_idx, (attackers & -attackers).bit_length() - 1

    # 4. Xe (Rooks) - Quân trượt
    rook_idx = start + 3
    attacks_from_sq = rook_attacks(sq, occ)
    attackers = attacks_from_sq & pos.bitboards[rook_idx] & occ
    if attackers:
        return rook_idx, (attackers & -attackers).bit_length() - 1

    # 5. Hậu (Queens) - Quân trượt
    queen_idx = start + 4
    attacks_from_sq = queen_attacks(sq, occ)
    attackers = attacks_from_sq & pos.bitboards[queen_idx] & occ
    if attackers:
        return queen_idx, (attackers & -attackers).bit_length() - 1

    # 6. Vua (King)
    king_idx = start + 5
    attacks_to_sq = KING_ATTACKS[sq]
    attackers = attacks_to_sq & pos.bitboards[king_idx] & occ
    if attackers:
        return king_idx, (attackers & -attackers).bit_length() - 1

    return None

def see(pos, mv) -> int:
    """
    Thực hiện Đánh giá Trao đổi Tĩnh (Static Exchange Evaluation) cho một nước đi.
    Trả về điểm số (dương là lời, âm là lỗ).
    """
    gain = [0] * 32  # Một stack để lưu giá trị vật chất
    d = 0            # Độ sâu của chuỗi trao đổi
    
    from_sq = mv.from_sq
    to_sq = mv.to_sq
    side = pos.side_to_move
    
    # Xử lý En Passant
    if mv.is_en_passant:
        captured_piece_idx = 0 if side == WHITE else 6 # Tốt của đối phương
    else:
        captured_piece_idx = mv.capture_piece

    # Nếu không phải là nước bắt quân (ví dụ bắt Vua, hoặc lỗi)
    if captured_piece_idx is None:
        return 0
        
    # Quân cờ di chuyển ban đầu
    attacker_piece_idx = mv.piece
    
    # Bàn cờ (occupancy) để mô phỏng, bắt đầu bằng cách xóa quân tấn công
    occ = pos.all_occupancy ^ (1 << from_sq)
    
    # Giá trị của quân bị bắt đầu tiên
    gain[d] = PIECE_VALUES[captured_piece_idx % 6]
    
    while True:
        d += 1
        side = 1 - side # Đổi lượt

        # Tìm quân tấn công tiếp theo (giá trị nhỏ nhất)
        attacker_data = _get_smallest_attacker(pos, to_sq, side, occ)
        
        if attacker_data is None:
            break # Không còn ai bắt lại

        next_attacker_piece_idx, next_from_sq = attacker_data
        
        # "Loại bỏ" quân tấn công khỏi bàn cờ mô phỏng
        occ ^= (1 << next_from_sq)
        
        # Cập nhật gain
        # gain[d] = (giá trị quân vừa bắt của lượt trước) - (gain của lượt trước)
        gain[d] = PIECE_VALUES[attacker_piece_idx % 6] - gain[d-1]
        
        # Tối ưu hóa: nếu nước đi này lỗ và nước trước cũng lỗ,
        # bên này sẽ chọn không bắt tiếp
        if gain[d] < 0 and gain[d-1] < 0:
            break
            
        attacker_piece_idx = next_attacker_piece_idx

    # "Unroll" stack để tìm kết quả cuối cùng
    # (Bên nào không bắt sẽ có max(0, -gain[d]))
    while d > 1:
        d -= 1
        gain[d-1] = -max(-gain[d-1], gain[d])
        
    return gain[0]