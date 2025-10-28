# ZetaChess

## Table of Contents
- [Giới thiệu](#giới-thiệu)
- [Cải tiến nổi bật & Chi tiết kỹ thuật](#cải-tiến-nổi-bật--chi-tiết-kỹ-thuật)
  - [Null Move Pruning](#null-move-pruning)
  - [Late Move Pruning](#late-move-pruning)
  - [History Sorting & Butterfly Tables](#history-sorting--butterfly-tables)
  - [Static Exchange Evaluation (SEE)](#static-exchange-evaluation-see)
  - [Late Move Reductions (LMR)](#late-move-reductions-lmr)
- [Kiến trúc & Thiết kế](#kiến-trúc--thiết-kế)
  - [Bảng giá trị & Đánh giá](#bảng-giá-trị--đánh-giá)
  - [Tìm kiếm nước đi (Search)](#tìm-kiếm-nước-đi-search)
  - [Sắp xếp nước đi (Move Ordering)](#sắp-xếp-nước-đi-move-ordering)
- [Hướng dẫn sử dụng](#hướng-dẫn-sử-dụng)

## Giới thiệu
ZetaChess là một chess engine nhẹ nhưng mạnh mẽ với đầy đủ tính năng sinh nước đi hợp lệ, đánh giá được cải tiến, tìm kiếm alpha-beta tối ưu, quiescence search và hỗ trợ giao thức UCI. Được thiết kế với kiến trúc module hóa rõ ràng để dễ dàng thử nghiệm và nâng cấp trong tương lai.

## Cải tiến nổi bật & Chi tiết kỹ thuật

### Null Move Pruning
Một kỹ thuật cắt tỉa mạnh mẽ dựa trên giả định rằng bỏ qua một lượt đi thường sẽ kém hơn việc thực hiện một nước đi tốt.

**Cách triển khai trong ZetaChess:**
- Áp dụng ở độ sâu > 2 và khi bên đi không bị chiếu
- Giảm độ sâu tìm kiếm: $R = \begin{cases} 3 & \text{if } depth \geq 6 \\ 2 & \text{if } depth < 6 \end{cases}$
- Chỉ áp dụng khi vị trí có đủ vật chất (tránh các vị trí endgame)
- Verification search với độ sâu giảm để tránh zugzwang
```python
if depth >= 3 and not in_check and has_non_pawn_material:
    R = 3 if depth >= 6 else 2
    score = -null_move_search(depth - R - 1, -beta, -beta + 1)
    if score >= beta:
        return beta  # Cut-off
```

### Late Move Pruning
Cắt tỉa các nước đi ở cuối danh sách được sắp xếp, dựa trên quan sát rằng các nước đi tốt thường được sắp xếp ở đầu danh sách.

**Chi tiết cải tiến:**
- Số lượng nước đi được xem xét phụ thuộc vào độ sâu tìm kiếm
- Công thức: $LMP(d) = \frac{3 + d^2}{3}$
- Chỉ áp dụng ở non-PV nodes và không áp dụng với các nước ăn quân
```python
moves_searched = 0
for move in moves:
    moves_searched += 1
    if depth <= 3 and moves_searched > depth * depth and !in_check and !is_capture(move):
        continue  # Skip late moves
```

### History Sorting & Butterfly Tables
Cải tiến heuristic history sorting bằng cách sử dụng butterfly tables để theo dõi hiệu quả của các nước đi.

**Cấu trúc và triển khai:**
- Bảng 2 chiều [từ][đến] lưu trữ điểm số lịch sử
- Cập nhật điểm dựa trên độ sâu của nước cắt beta: $score += depth^2$
- Định kỳ chia điểm số cho 2 để ưu tiên lịch sử gần đây
```python
# Butterfly table structure
butterfly_table = [[0 for x in range(64)] for y in range(64)]

# Update history score
def update_history(move, depth):
    from_sq = move.from_square()
    to_sq = move.to_square()
    butterfly_table[from_sq][to_sq] += depth * depth

# Get history score for move ordering
def get_history_score(move):
    return butterfly_table[move.from_square()][move.to_square()]
```

### Static Exchange Evaluation (SEE)
Đánh giá tĩnh chuỗi trao đổi quân có thể xảy ra tại một ô cờ.

**Thuật toán chi tiết:**
1. Xác định tất cả quân có thể tham gia trao đổi
2. Tính toán giá trị trao đổi theo thứ tự giá trị quân tăng dần
3. Sử dụng cấu trúc dữ liệu bit boards để tối ưu hóa
```python
def see(move):
    if not is_capture(move):
        return 0
    
    total = 0
    square = move.to_square()
    value = get_piece_value(captured_piece)
    
    while True:
        # Find least valuable attacker
        attacker = find_least_valuable_attacker(square)
        if not attacker:
            break
            
        total = \max(-total - 1, -value) + get\_piece\_value(attacker)
        
    return total
```

### Late Move Reductions (LMR)
Giảm độ sâu tìm kiếm cho các nước đi ở cuối danh sách trong non-PV nodes.

**Công thức và điều kiện:**
- Áp dụng cho non-PV nodes ở độ sâu > 3
- Reduction: $R = \frac{\ln(depth) \cdot \ln(moveNumber)}{2}$
- Không áp dụng cho:
  - Nước ăn quân
  - Nước thăng cấp tốt
  - Nước chiếu
```python
def get_reduction(depth, move_number):
    if depth >= 3 and move_number >= 4:
        R = int(math.log(depth) * math.log(move_number) / 2)
        return min(depth - 1, max(1, R))
    return 0
```

## Kiến trúc & Thiết kế

### Bảng giá trị & Đánh giá
Engine sử dụng hệ thống đánh giá tiên tiến, kết hợp nhiều yếu tố:
- **Giá trị vật chất của quân:**
  - Tốt: 100
  - Mã/Tượng: 320/330
  - Xe: 500
  - Hậu: 900
- **Bảng giá trị vị trí:**
  - Riêng cho mỗi loại quân
  - Khác nhau giữa tầng giữa và tàn cuộc
- **Đánh giá cấu trúc tốt:**
  - Tốt đôi
  - Tốt cô lập
  - Tốt thông qua
- **An toàn của Vua:**
  - Shield pawns
  - Storm pawns
  - King safety table
- **Cơ động của quân:**
  - Số ô di chuyển được
  - Kiểm soát trung tâm
  - Đe dọa các điểm yếu

### Tìm kiếm nước đi (Search)
Tổng hợp các kỹ thuật tìm kiếm:
- Principal Variation Search
- Aspiration Windows với cửa sổ $\alpha = \alpha_{prev} - 50$, $\beta = \beta_{prev} + 50$
- Internal Iterative Deepening
- Transposition Table với replacement strategy
- Check Extension (+1 ply)
- Quiescence Search với SEE pruning

### Sắp xếp nước đi (Move Ordering)
Thứ tự ưu tiên trong sắp xếp:
1. PV moves từ transposition table
2. Captures được sắp xếp bởi MVV-LVA + SEE
3. Killer moves (2 nước/ply)
4. Counter moves
5. Quiet moves sắp xếp bởi history score
6. Bad captures (SEE < 0)

## Hướng dẫn sử dụng

### Khởi động API Server
1. Cài đặt các thư viện cần thiết:
   ```bash
   pip install fastapi uvicorn pydantic
   ```
2. Khởi động server:
   ```bash
   uvicorn api:app --reload
   ```
   Server sẽ chạy mặc định tại `http://localhost:8000`

### API Endpoints

#### 1. Kiểm tra server
- **GET** `/`
- Kiểm tra trạng thái hoạt động của API
- Response:
  ```json
  {
    "message": "ZetaChess API v1.0 is running"
  }
  ```

#### 2. Tìm nước đi tốt nhất
- **POST** `/move`
- Body request:
  ```json
  {
    "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "depth": 3,
    "method": "best"
  }
  ```
  - `fen`: Chuỗi FEN biểu diễn vị trí hiện tại (bắt buộc)
  - `depth`: Độ sâu tìm kiếm (mặc định: 3)
  - `method`: "best" cho nước đi tốt nhất, "random" cho nước đi ngẫu nhiên

- Response cho nước đi tốt nhất:
  ```json
  {
    "status": "ok",
    "method": "best",
    "move": "e2e4",
    "fen_after": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
    "eval": 0.35,
    "static_eval": 0.2,
    "depth": 3
  }
  ```

### Sử dụng với Web Interface
1. Mở file `gui/index.html` trong trình duyệt
2. Web interface sẽ tự động kết nối với API server
3. Các tính năng:
   - Hiển thị bàn cờ tương tác
   - Cho phép di chuyển quân cờ
   - Hiển thị đánh giá vị trí
   - Tùy chỉnh độ sâu tìm kiếm
