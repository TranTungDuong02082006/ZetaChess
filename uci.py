import sys
import time
import threading
from typing import Optional

from position import Position
from search import Search, MATE_SCORE
from moves import Move, generate_legal_moves
import INITIAL_FEN


def move_to_uci(m: Move) -> str:
    s = f"{chr(ord('a') + (m.from_sq % 8))}{(m.from_sq // 8) + 1}{chr(ord('a') + (m.to_sq % 8))}{(m.to_sq // 8) + 1}"
    if m.promotion is not None:
        promo = 'q' if m.promotion % 6 == 4 else 'r' if m.promotion % 6 == 3 else 'b' if m.promotion % 6 == 2 else 'n'
        s += promo
    return s


def find_legal_move(pos: Position, uci: str) -> Optional[Move]:
    from_sq = (ord(uci[0]) - ord('a')) + (int(uci[1]) - 1) * 8
    to_sq = (ord(uci[2]) - ord('a')) + (int(uci[3]) - 1) * 8
    promo = None
    if len(uci) == 5:
        ch = uci[4]
        promo = {'q': 4, 'r': 3, 'b': 2, 'n': 1}.get(ch)
    for m in generate_legal_moves(pos):
        if m.from_sq == from_sq and m.to_sq == to_sq and (promo is None or m.promotion == promo):
            return m
    return None


def run_uci_loop():
    pos = Position.from_fen(INITIAL_FEN)
    search = Search()
    search_thread: Optional[threading.Thread] = None

    def start_search(depth: Optional[int], time_ms: Optional[int]):
        nonlocal search_thread
        # If a previous search is running, stop it first
        if search_thread is not None and search_thread.is_alive():
            search.request_stop()
            search_thread.join()

        def worker():
            local_depth = depth if depth is not None else 10
            start = time.monotonic()
            # per-iteration info callback
            def info_callback(d: int, nodes: int, ms: int, score: int, pv_moves: list[Move], bound: Optional[str] = None):
                elapsed_s = ms / 1000.0 if ms > 0 else 0.0
                nps = int(nodes / elapsed_s) if elapsed_s > 0 else nodes
                # Report score: mate if near MATE_SCORE, else centipawns
                if abs(score) > MATE_SCORE - 10000:
                    mate_moves = (MATE_SCORE - abs(score) + 1) // 2
                    mate_val = mate_moves if score > 0 else -mate_moves
                    info_score = f"score mate {mate_val}"
                else:
                    info_score = f"score cp {score}"
                if bound == 'upperbound':
                    info_score += " upperbound"
                elif bound == 'lowerbound':
                    info_score += " lowerbound"
                pv_str = ' '.join(move_to_uci(m) for m in pv_moves)
                print(f"info depth {d} nodes {nodes} time {ms} nps {nps} {info_score} pv {pv_str}")
                sys.stdout.flush()

            # root move progress callback
            def progress_callback(mv: Move, idx: int, d: int, nodes: int, ms: int):
                elapsed_s = ms / 1000.0 if ms > 0 else 0.0
                nps = int(nodes / elapsed_s) if elapsed_s > 0 else nodes
                print(f"info currmove {move_to_uci(mv)} currmovenumber {idx} depth {d} nodes {nodes} time {ms} nps {nps}")
                sys.stdout.flush()

            best, score, nodes = search.search(pos, depth=local_depth, time_ms=time_ms, info_cb=info_callback, progress_cb=progress_callback)
            elapsed = (time.monotonic() - start)
            time_report = int(elapsed * 1000)
            nps = int(nodes / elapsed) if elapsed > 0 else nodes

            # Report score: mate if near MATE_SCORE, else centipawns
            info_score = ''
            if abs(score) > MATE_SCORE - 10000:
                sign = 1 if score > 0 else -1
                mate_dist = sign * (MATE_SCORE - abs(score))
                info_score = f"score mate {mate_dist}"
            else:
                info_score = f"score cp {score}"

            pv_moves = search.get_pv(pos, max_len=local_depth)
            pv_str = ' '.join(move_to_uci(m) for m in pv_moves)
            print(f"info depth {local_depth} nodes {nodes} time {time_report} nps {nps} {info_score} pv {pv_str}")
            sys.stdout.flush()
            if best is None:
                print("bestmove 0000")
            else:
                print(f"bestmove {move_to_uci(best)}")
            sys.stdout.flush()

        search_thread = threading.Thread(target=worker, daemon=True)
        search_thread.start()

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if line == 'uci':
            print('id name SunfishPro')
            print('id author TraeAI')
            print('uciok')
            sys.stdout.flush()
            continue
        if line == 'isready':
            print('readyok')
            sys.stdout.flush()
            continue
        if line == 'ucinewgame':
            # stop any running search
            if search_thread is not None and search_thread.is_alive():
                search.request_stop()
                search_thread.join()
            pos = Position.from_fen(INITIAL_FEN)
            search.tt.clear()
            search.killers.clear()
            search.history.clear()
            continue
        if line.startswith('position'):
            # position [fen <fenstring> | startpos ] moves <move1> .... <movei>
            parts = line.split()
            idx = 1
            if idx < len(parts) and parts[idx] == 'startpos':
                pos = Position.from_fen(INITIAL_FEN)
                idx += 1
            elif idx < len(parts) and parts[idx] == 'fen':
                fen = ' '.join(parts[idx + 1:])
                # FEN may end before 'moves'
                fen_parts = fen.split(' moves')
                fen = fen_parts[0].strip()
                pos = Position.from_fen(fen)
                if len(fen_parts) > 1:
                    moves_str = fen_parts[1].strip()
                    moves_list = moves_str.split()
                    for u in moves_list:
                        m = find_legal_move(pos, u)
                        if m:
                            pos.make_move(m)
                continue
            # Apply subsequent moves if any
            if idx < len(parts) and parts[idx] == 'moves':
                for u in parts[idx + 1:]:
                    m = find_legal_move(pos, u)
                    if m:
                        pos.make_move(m)
            continue
        if line.startswith('go'):
            # go depth N | go movetime M | go wtime WT btime BT winc WI binc BI [movestogo MT]
            tokens = line.split()
            depth = None
            movetime = None
            wtime = btime = winc = binc = movestogo = None
            i = 1
            while i < len(tokens):
                t = tokens[i]
                if t == 'depth':
                    depth = int(tokens[i + 1])
                    i += 2
                elif t == 'movetime':
                    movetime = int(tokens[i + 1])
                    i += 2
                elif t == 'wtime':
                    wtime = int(tokens[i + 1])
                    i += 2
                elif t == 'btime':
                    btime = int(tokens[i + 1])
                    i += 2
                elif t == 'winc':
                    winc = int(tokens[i + 1])
                    i += 2
                elif t == 'binc':
                    binc = int(tokens[i + 1])
                    i += 2
                elif t == 'movestogo':
                    movestogo = int(tokens[i + 1])
                    i += 2
                else:
                    i += 1

            time_ms = None
            if movetime is not None:
                time_ms = movetime
            elif wtime is not None and btime is not None:
                # simple time management: allocate a fraction of remaining time
                remaining = wtime if pos.side_to_move == 0 else btime
                inc = winc if pos.side_to_move == 0 else binc
                mtg = movestogo if movestogo is not None else 30
                base = remaining / max(mtg, 1)
                budget = base + (inc or 0) * 0.8
                # keep a small safety margin
                time_ms = int(max(1, budget * 0.8))

            start_search(depth, time_ms)
            continue
        if line == 'stop':
            if search_thread is not None and search_thread.is_alive():
                search.request_stop()
                search_thread.join()
            continue
        if line == 'quit':
            if search_thread is not None and search_thread.is_alive():
                search.request_stop()
                search_thread.join()
            break


if __name__ == '__main__':
    run_uci_loop()


    def start_search(args):
        pos, depth, movetime = args
        search = Search()
        start = time.monotonic()

        def info_callback(d: int, nodes: int, time_ms: int, score: int, pv_moves: list[Move], bound: Optional[str] = None):
            # Compute NPS safely
            nps = int(nodes * 1000 / max(time_ms, 1))
            # Score formatting: cp or mate
            MATE_SCORE = 1000000
            score_str: str
            if abs(score) > MATE_SCORE - 10000:
                # Convert mate score to moves-to-mate (approximate from score)
                # UCI expects 'score mate N' where N > 0 is mate for side to move
                # and N < 0 is mate for the opponent.
                mate_moves = (MATE_SCORE - abs(score) + 1) // 2
                mate_val = mate_moves if score > 0 else -mate_moves
                score_str = f"score mate {mate_val}"
            else:
                score_str = f"score cp {score}"
            if bound == 'upperbound':
                score_str += " upperbound"
            elif bound == 'lowerbound':
                score_str += " lowerbound"
            # PV formatting
            pv_str = " ".join(mv.uci() for mv in pv_moves) if pv_moves else ""
            print(f"info depth {d} nodes {nodes} time {time_ms} nps {nps} {score_str} pv {pv_str}", flush=True)

        def progress_callback(mv: Move, idx: int, depth_now: int, nodes: int, time_ms: int):
            nps = int(nodes * 1000 / max(time_ms, 1))
            print(f"info currmove {mv.uci()} currmovenumber {idx} depth {depth_now} nodes {nodes} time {time_ms} nps {nps}", flush=True)

        best, score, nodes = search.search(pos, depth=depth, time_ms=movetime, info_cb=info_callback, progress_cb=progress_callback)
        elapsed = int((time.monotonic() - start) * 1000)
        nps = int(nodes * 1000 / max(elapsed, 1))
        print(f"info depth {depth} nodes {nodes} time {elapsed} nps {nps}", flush=True)
        bm = best.uci() if best else "0000"
        print(f"bestmove {bm}", flush=True)