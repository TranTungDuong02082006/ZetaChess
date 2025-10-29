import traceback  # Import traceback để in lỗi chi tiết
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware

from position import Position
from moves import generate_legal_moves, Move
from search import Search
from eval import evaluate
from uci import move_to_uci

app = FastAPI(title="ZetaChess API", version="1.0")
searcher = Search()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class FenRequest(BaseModel):
    fen: str
    depth: Optional[int] = 3
    method: Optional[str] = "best"  # "best" | "random"

@app.get("/")
def root():
    return {"message": "ZetaChess API v1.0 is running"}

# --- Main move endpoint ---
@app.post("/move")
def get_move(request: FenRequest):
    """
    Input: FEN string + search depth
    Output: best move (or random move) + new FEN
    """
    try:
        pos = Position.from_fen(request.fen)
    except Exception as e:
        return {"status": "error", "reason": f"Invalid FEN: {e}"}

    legal_moves = generate_legal_moves(pos)
    if not legal_moves:
        return {"status": "game_over", "reason": "No legal moves"}

    # Random move
    if request.method == "random":
        import random
        move = random.choice(legal_moves)
        pos.make_move(move)
        return {
            "status": "ok",
            "method": "random",
            "move": move_to_uci(move),
            "fen_after": pos.to_fen(),
        }

    # Best move (search)
    depth = max(1, request.depth or 3)
    
    # === KHỐI DEBUG ĐƯỢC THÊM VÀO ===
    try:
        best_move, best_eval, _ = searcher.search(pos, depth)
    except Exception as e:
        tb_str = traceback.format_exc()
        # In lỗi ra terminal của uvicorn
        print(f"!!!!!!!!!!!!!!! LỖI TRONG HÀM SEARCH !!!!!!!!!!!!!!!")
        print(tb_str)
        print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        # Trả lỗi chi tiết về cho frontend
        return {"status": "error", "reason": f"Search failed: {e}", "traceback": tb_str}
    # ==================================

    if best_move is None:
        return {"status": "error", "reason": "No move found"}
    pos.make_move(best_move)

    static_eval = evaluate(pos)

    return {
        "status": "ok",
        "method": "best",
        "move": move_to_uci(best_move),
        "fen_after": pos.to_fen(),
        "eval": best_eval,
        "static_eval": static_eval,
        "depth": depth
    }
