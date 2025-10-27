from dataclasses import dataclass
from typing import Optional, List, Callable
import time

from .constants import WHITE, BLACK
from .moves import Move, generate_legal_moves, is_square_attacked_by
from .eval import evaluate, PIECE_VALUES

MATE_SCORE = 1000000
EXACT, LOWER, UPPER = 0, 1, 2


@dataclass
class TTEntry:
    key: int
    depth: int
    score: int
    flag: int
    best_move: Optional[Move]


def _sq_name(sq: int) -> str:
    return chr(ord('a') + (sq % 8)) + str((sq // 8) + 1)


class Search:
    def __init__(self):
        self.tt: dict[int, TTEntry] = {}
        self.nodes: int = 0
        self.deadline: Optional[float] = None
        # Killer moves: up to two quiet moves per ply
        self.killers: dict[int, list[tuple[int, int, Optional[int]]]] = {}
        # History heuristic: key=(from,to), value accumulated weight
        self.history: dict[tuple[int, int], int] = {}
        # Stop control flags
        self.stop_requested: bool = False
        self.out_of_time: bool = False

    def _in_check(self, pos) -> bool:
        side = pos.side_to_move
        king_sq = (pos.bitboards[5 if side == WHITE else 11]).bit_length() - 1
        return is_square_attacked_by(1 - side, king_sq, pos)

    def _is_quiet(self, mv: Move) -> bool:
        return mv.capture_piece is None and not mv.is_en_passant and mv.promotion is None

    def _has_non_pawn_material(self, pos, side: int) -> bool:
        if side == WHITE:
            return (pos.bitboards[1] | pos.bitboards[2] | pos.bitboards[3] | pos.bitboards[4]) != 0
        else:
            return (pos.bitboards[7] | pos.bitboards[8] | pos.bitboards[9] | pos.bitboards[10]) != 0

    def _move_order(self, pos, moves: List[Move], tt_move: Optional[Move], ply: int) -> List[Move]:
        def score(mv: Move) -> int:
            s = 0
            # TT move first
            if tt_move is not None and mv.from_sq == tt_move.from_sq and mv.to_sq == tt_move.to_sq and mv.promotion == tt_move.promotion:
                s += 100000
            # Promotions
            if mv.promotion is not None:
                s += 500 + PIECE_VALUES[mv.promotion % 6]
            # Captures (MVV-LVA style)
            if mv.capture_piece is not None:
                s += 1000 + PIECE_VALUES[mv.capture_piece % 6] - PIECE_VALUES[mv.piece % 6]
            # Castling bonus
            if mv.is_castling:
                s += 50
            # Quiet ordering: killers and history
            if self._is_quiet(mv):
                km = self.killers.get(ply)
                if km:
                    if mv.from_sq == km[0][0] and mv.to_sq == km[0][1] and mv.promotion == km[0][2]:
                        s += 80000
                    elif len(km) > 1 and mv.from_sq == km[1][0] and mv.to_sq == km[1][1] and mv.promotion == km[1][2]:
                        s += 70000
                s += self.history.get((mv.from_sq, mv.to_sq), 0)
            return s
        return sorted(moves, key=score, reverse=True)

    def _ordered_captures(self, pos, moves: List[Move]) -> List[Move]:
        caps = [m for m in moves if m.capture_piece is not None or m.is_en_passant or m.promotion is not None]
        return sorted(caps, key=lambda m: (PIECE_VALUES[m.capture_piece % 6] if m.capture_piece is not None else 0) - PIECE_VALUES[m.piece % 6], reverse=True)

    def request_stop(self) -> None:
        self.stop_requested = True

    def qsearch(self, pos, alpha: int, beta: int) -> int:
        # Simple stand-pat quiescence with captures/promotions only
        self.nodes += 1
        # Early abort on stop/time
        if self.stop_requested or (self.deadline is not None and self.nodes % 2048 == 0 and time.monotonic() > self.deadline):
            self.out_of_time = True
            return alpha
        stand_pat = evaluate(pos)
        if stand_pat >= beta:
            return beta
        if alpha < stand_pat:
            alpha = stand_pat
        legal = generate_legal_moves(pos)
        for mv in self._ordered_captures(pos, legal):
            pos.make_move(mv)
            score = -self.qsearch(pos, -beta, -alpha)
            pos.undo_move()
            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
        return alpha

    def alphabeta(self, pos, depth: int, alpha: int, beta: int, ply: int = 0, progress_cb: Optional[Callable[[Move, int, int], None]] = None) -> int:
        # Early abort on explicit stop
        if self.stop_requested:
            self.out_of_time = True
            return alpha
        # Optional time check
        if self.deadline is not None and self.nodes % 2048 == 0:
            if time.monotonic() > self.deadline:
                self.out_of_time = True
                return alpha
        self.nodes += 1
        key = pos.zobrist
        tt = self.tt.get(key)
        if tt is not None and tt.depth >= depth:
            if tt.flag == EXACT:
                return tt.score
            if tt.flag == LOWER:
                alpha = max(alpha, tt.score)
            elif tt.flag == UPPER:
                beta = min(beta, tt.score)
            if alpha >= beta:
                return tt.score
        tt_move = tt.best_move if tt is not None else None

        # In-check flag; no check extension to avoid pathological deep recursion
        in_check = self._in_check(pos)
        if depth <= 0:
            return self.qsearch(pos, alpha, beta)

        # Null-move pruning: try skipping a turn when not in check and with material
        if depth >= 2 and not in_check and self._has_non_pawn_material(pos, pos.side_to_move):
            R = 3 if depth >= 5 else 2
            side = pos.side_to_move
            null_pos = pos.clone()
            # Clear en passant and advance clocks appropriately
            null_pos.ep_square = None
            null_pos.halfmove_clock += 1
            if side == BLACK:
                null_pos.fullmove_number += 1
            # Toggle side and recompute Zobrist
            null_pos.side_to_move = 1 - side
            null_pos.zobrist = null_pos.zobrist_table.compute(null_pos)
            # Null-window search to detect fail-high quickly
            score = -self.alphabeta(null_pos, depth - R - 1, -beta, -beta + 1, ply + 1, progress_cb)
            if score >= beta:
                return beta

        legal = generate_legal_moves(pos)
        if not legal:
            # terminal: mate or stalemate
            if in_check:
                return -MATE_SCORE + ply
            return 0

        best_score = -MATE_SCORE
        best_move = None
        ordered = self._move_order(pos, legal, tt_move, ply)
        stand_pat = evaluate(pos)
        a0 = alpha
        move_index = 0
        for mv in ordered:
            move_index += 1
            # Root progress info
            if ply == 0 and progress_cb is not None:
                progress_cb(mv, move_index, depth)
            # Late move reductions: reduce depth for late quiet moves
            reduce = False
            r = 0
            if depth >= 3 and self._is_quiet(mv) and not in_check and move_index > 4:
                reduce = True
                r = max(r, 1)
            # Futility reductions at shallow depths for quiet moves
            if depth <= 2 and not in_check and self._is_quiet(mv):
                margin = 150 if depth == 1 else 250
                if stand_pat + margin <= alpha:
                    reduce = True
                    r = max(r, 1)
            pos.make_move(mv)
            # Principal Variation Search: full window on first move, zero-window on others
            if move_index == 1:
                score = -self.alphabeta(pos, depth - 1, -beta, -alpha, ply + 1, progress_cb)
            else:
                # zero-window probe
                score = -self.alphabeta(pos, depth - 1 - r, -alpha - 1, -alpha, ply + 1, progress_cb)
                if score > alpha:
                    # re-search with full window (still with reduction r)
                    score = -self.alphabeta(pos, depth - 1 - r, -beta, -alpha, ply + 1, progress_cb)
            pos.undo_move()
            # If reduced search (LMR/futility) improved alpha, re-search at full depth
            if reduce and score > alpha:
                pos.make_move(mv)
                score = -self.alphabeta(pos, depth - 1, -beta, -alpha, ply + 1, progress_cb)
                pos.undo_move()
            if score > best_score:
                best_score = score
                best_move = mv
            # Fail-high: record killer/history on quiet move
            if score >= beta:
                if self._is_quiet(mv):
                    km = self.killers.get(ply, [])
                    key_tpl = (mv.from_sq, mv.to_sq, mv.promotion)
                    if not km or km[0] != key_tpl:
                        km = [key_tpl] + [k for k in km if k != key_tpl]
                    if len(km) > 2:
                        km = km[:2]
                    self.killers[ply] = km
                    self.history[(mv.from_sq, mv.to_sq)] = self.history.get((mv.from_sq, mv.to_sq), 0) + depth * depth
                break
            if score > alpha:
                alpha = score
        # store in TT
        flag = EXACT
        if best_score <= a0:
            flag = UPPER
        elif best_score >= beta:
            flag = LOWER
        self.tt[key] = TTEntry(key=key, depth=depth, score=best_score, flag=flag, best_move=best_move)
        return best_score

    def get_pv(self, pos, max_len: int) -> List[Move]:
        pv: List[Move] = []
        seen = set()
        while len(pv) < max_len:
            tt = self.tt.get(pos.zobrist)
            if tt is None or tt.best_move is None:
                break
            mv = tt.best_move
            # avoid loops
            key = (mv.from_sq, mv.to_sq, mv.promotion)
            if key in seen:
                break
            seen.add(key)
            pv.append(mv)
            pos.make_move(mv)
        # undo applied PV moves
        for _ in range(len(pv)):
            pos.undo_move()
        return pv

    def search(self, pos, depth: int, time_ms: Optional[int] = None, info_cb: Optional[Callable[[int, int, int, int, List[Move], Optional[str]], None]] = None, progress_cb: Optional[Callable[[Move, int, int, int, int], None]] = None) -> tuple[Optional[Move], int, int]:
        best_move = None
        score = 0
        self.nodes = 0
        self.deadline = time.monotonic() + (time_ms / 1000.0) if time_ms else None
        self.stop_requested = False
        self.out_of_time = False
        start_time = time.monotonic()
        prev_score = 0

        for d in range(1, depth + 1):
            # Decay history occasionally to avoid overflow/bias
            if d % 2 == 0 and self.history:
                for k in list(self.history.keys()):
                    self.history[k] //= 2
            # Aspiration window around previous score with iterative widening
            if d > 1:
                delta = 50
                a = prev_score - delta
                b = prev_score + delta
            else:
                a = -MATE_SCORE
                b = MATE_SCORE

            # Root progress wrapper to enrich with nodes/time
            def root_progress_cb(mv: Move, idx: int, depth_now: int):
                if progress_cb is not None:
                    elapsed = time.monotonic() - start_time
                    time_report = int(elapsed * 1000)
                    progress_cb(mv, idx, depth_now, self.nodes, time_report)

            while True:
                s = self.alphabeta(pos, d, a, b, ply=0, progress_cb=root_progress_cb)
                # Emit bound info per attempt
                if info_cb is not None:
                    elapsed = time.monotonic() - start_time
                    time_report = int(elapsed * 1000)
                    pv_moves = self.get_pv(pos, max_len=d)
                # Fail-low: widen lower bound
                if s <= a and a > -MATE_SCORE:
                    if info_cb is not None:
                        info_cb(d, self.nodes, time_report, s, pv_moves, 'upperbound')
                    delta *= 2
                    a = max(-MATE_SCORE, a - delta)
                    continue
                # Fail-high: widen upper bound
                if s >= b and b < MATE_SCORE:
                    if info_cb is not None:
                        info_cb(d, self.nodes, time_report, s, pv_moves, 'lowerbound')
                    delta *= 2
                    b = min(MATE_SCORE, b + delta)
                    continue
                break
            score = s
            prev_score = score
            tt = self.tt.get(pos.zobrist)
            if tt is not None and tt.best_move is not None:
                best_move = tt.best_move
            # emit per-iteration info
            if info_cb is not None:
                elapsed = time.monotonic() - start_time
                time_report = int(elapsed * 1000)
                pv_moves = self.get_pv(pos, max_len=d)
                info_cb(d, self.nodes, time_report, score, pv_moves, 'exact')
            # optional early break if time exceeded or stop requested
            if self.out_of_time or self.stop_requested or (self.deadline is not None and time.monotonic() > self.deadline):
                break
        return best_move, score, self.nodes