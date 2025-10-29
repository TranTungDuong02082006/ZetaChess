// Khởi tạo bàn cờ và trò chơi
let board = null;
let game = new Chess();
let capturedWhite = []; // Danh sách các quân TRẮNG bị bắt 
let capturedBlack = []; // Danh sách các quân ĐEN bị bắt
let moveStartTime = Date.now();
let moveHistory = [];
let gameStarted = false;
let playerColor = "w";
let currentTurn = "w";

// thời gian ban đầu (giây)
let whiteTime = 600;
let blackTime = 600;
let whiteClock;
let blackClock ;
let timerInterval = null;

const statusEl = document.getElementById("status");
const API_URL = "http://127.0.0.1:8000/move";

// =================== DRAG & MOVE ======================
function onDragStart(source, piece) {
  if (!gameStarted || game.game_over()) return false;
  if (game.turn() !== playerColor || piece[0] !== playerColor) return false;
}

// Xử lý khi người chơi thả quân (Lượt Trắng)
async function onDrop(source, target) {
  const move = game.move({ from: source, to: target, promotion: "q" });
  if (!move) return "snapback";

  updateCapturedPieces(move);
  board.position(game.fen());
  updateStatus(); 

  // Dừng đồng hồ Trắng và ghi thời gian
  clearInterval(timerInterval); 
  const duration = ((Date.now() - moveStartTime) / 1000).toFixed(2);
  updateMoveHistory(move, duration, playerColor);
  moveStartTime = Date.now();

  currentTurn = playerColor === "w" ? "b" : "w"; 
  startClock(); 

  // Gọi Bot
  await requestBotMove();
}

// Cập nhật vị trí sau khi quân được thả
function onSnapEnd() {
  board.position(game.fen());
}

// =================== BOT MOVE =========================
// Gửi FEN cho bot và xử lý phản hồi (Lượt Đen)
async function requestBotMove() {
  const fen = game.fen();
  statusEl.textContent = "Bot is thinking...";

  try {
    console.log("Sending request to bot with FEN:", fen);
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fen, method: "best" }),
    });
    console.log("Response received from bot");
    console.log("Received response from bot:", response);
    if (!response.ok) {
      statusEl.textContent = `Error: HTTP status ${response.status}. Cannot reach API server.`;
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    console.log("Parsing bot response as JSON");
    const data = await response.json();
    console.log("Bot response data:", data);
    if (data.status === "ok" && data.move) {
      const botMove = game.move(data.move, { sloppy: true });
      updateCapturedPieces(botMove);
      board.position(game.fen());
      updateStatus();

      // Dừng đồng hồ Đen và ghi thời gian
      clearInterval(timerInterval);
      const duration = ((Date.now() - moveStartTime) / 1000).toFixed(2);
      updateMoveHistory(botMove, duration, game.turn() === "w" ? "b" : "w");
      moveStartTime = Date.now();

      currentTurn = playerColor;
      startClock();
    } else {
      const reason = data.reason || "unknown";
      statusEl.textContent = data.status === "game_over"
        ? `Game over: ${reason}`
        : `Error: Bot response status: ${reason}`;
      console.error("Bot response error:", data);
      clearInterval(timerInterval); 
    }
  } catch (error) {
    console.error("API fetch failed:", error);
    statusEl.textContent = "Cannot reach API server. Check your bot server/CORS.";
    clearInterval(timerInterval); 
  }
}

// =================== GAME CONTROL =====================
function resetGame() {
  clearInterval(timerInterval);
  game.reset();
  board.start();
  capturedWhite = [];
  capturedBlack = [];
  moveHistory = [];
  whiteTime = 600;
  blackTime = 600;
  currentTurn = "w";
  moveStartTime = Date.now();
  gameStarted = false;

  updateClockDisplay();
  renderCaptured();
  renderMoveHistory();
  updateStatus();

  document.getElementById("startBtn").textContent = "Start Game";
}


function startGame() {
  const startBtn = document.getElementById("startBtn");

  if (!gameStarted) {
    gameStarted = true;
    startBtn.textContent = "Restart Game";

    // Lấy màu người chơi từ radio button
    const selectedColor = document.querySelector('input[name="color"]:checked').value;
    if (selectedColor === "black") playerColor = "b";
    else if (selectedColor === "random") playerColor = Math.random() < 0.5 ? "w" : "b";
    else playerColor = "w";

    const topRow = document.getElementById("topRow");
    const bottomRow = document.getElementById("bottomRow");
    const boardEl = document.getElementById("board");


    board.orientation(playerColor === "w" ? "white" : "black");
    game.reset();
    board.start();
    capturedWhite = [];
    capturedBlack = [];
    moveHistory = [];
    whiteTime = 600;
    blackTime = 600;
    moveStartTime = Date.now();

    updateClockDisplay();
    renderCaptured();
    renderMoveHistory();
    updateStatus();

    if (playerColor === "b") {
      // Bot đi trước
      topRow.remove();
      bottomRow.remove();
      boardEl.insertAdjacentElement("beforebegin", bottomRow);
      boardEl.insertAdjacentElement("afterend", topRow);
      currentTurn = "w";
      startClock();
      requestBotMove();
    } else {
      // Người chơi đi trước
      currentTurn = "w";
      startClock();
    }
  } else {
    restartGame(); // restart toàn bộ
  }
}


// ======================== CLOCK ===========================
function updateClockDisplay() {
  whiteClock.textContent = formatTime(whiteTime);
  blackClock.textContent = formatTime(blackTime);
}

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function startClock() {
  clearInterval(timerInterval); // Đảm bảo chỉ có một interval chạy
  timerInterval = setInterval(() => {
    if (currentTurn === "w") {
      whiteTime--;
      if (whiteTime <= 0) endGame("⏰ White ran out of time — Black wins!");
    } else {
      blackTime--;
      if (blackTime <= 0) endGame("⏰ Black ran out of time — White wins!");
    }
    updateClockDisplay();
  }, 1000);
}

function endGame(msg) {
  clearInterval(timerInterval);
  alert(msg);
  statusEl.textContent = msg;
}

// ==================== CAPTURED PIECES =====================
function updateCapturedPieces(move) {
  if (move.captured) {
    const piece = move.captured.toUpperCase(); // Tên quân cờ in hoa
    const colorOfMover = move.color; // 'w' (Trắng) hoặc 'b' (Đen)
    
    // Tên file ảnh: bR, wP, v.v. (Màu quân bị bắt + Tên quân in hoa)
    const pieceImgName = `w${piece}`; 

    if (colorOfMover === 'w') {
      // Trắng ăn -> Đen bị bắt -> Thêm vào danh sách Trắng bắt (capturedWhite)
      capturedWhite.push(pieceImgName); 
    } else {
      // Đen ăn -> Trắng bị bắt -> Thêm vào danh sách Đen bắt (capturedBlack)
      capturedBlack.push(pieceImgName); 
    }
    renderCaptured();
  }
}

function renderCaptured() {
  const pieceImg = (piece) =>
    `<img src="./chessboardjs/img/chesspieces/wikipedia/${piece}.png" />`;

  // Xóa nội dung cũ trước khi render
  document.getElementById("capturedWhite").innerHTML = "";
  document.getElementById("capturedBlack").innerHTML = "";

  // Render các quân bị bắt bởi Trắng (quân Đen)
  capturedWhite.forEach(piece => {
    document.getElementById("capturedWhite").insertAdjacentHTML("beforeend", pieceImg(piece));
  });

  // Render các quân bị bắt bởi Đen (quân Trắng)
  capturedBlack.forEach(piece => {
    document.getElementById("capturedBlack").insertAdjacentHTML("beforeend", pieceImg(piece));
  });
}

// ==================== MOVE HISTORY =======================
function updateMoveHistory(move, duration, color) {
  const historyLength = game.history().length;
  const turnIndex = Math.floor((historyLength - 1) / 2);

  if (color === "w") {
    moveHistory[turnIndex] = {
      turn: turnIndex + 1,
      white: move.san,
      whiteTime: `${duration}s`,
      black: "",
      blackTime: ""
    };
  } else {
    if (!moveHistory[turnIndex]) {
      moveHistory[turnIndex] = { turn: turnIndex + 1, white: "", whiteTime: "", black: "", blackTime: "" };
    }
    moveHistory[turnIndex].black = move.san;
    moveHistory[turnIndex].blackTime = `${duration}s`;
  }

  renderMoveHistory();
}

function renderMoveHistory() {
  const tbody = document.querySelector("#moveHistory tbody");
  tbody.innerHTML = "";

  moveHistory.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.turn}</td>
      <td>${row.white}</td>
      <td>${row.whiteTime}</td>
      <td>${row.black}</td>
      <td>${row.blackTime}</td>
    `;
    tbody.appendChild(tr);
  });
}

// ==================== STATUS =============================
function updateStatus() {
  const moveColor = game.turn() === "w" ? "White" : "Black";
  let status = `${moveColor} to move`;

  if (game.in_checkmate()) {
    const winner = moveColor === 'White' ? 'Black' : 'White';
    status = `Game over, ${winner} wins by checkmate!`;
    endGame(`🏁 ${winner} wins by checkmate!`);
    clearInterval(timerInterval);
  } else if (game.in_draw()) {
    status = "Game over, drawn position.";
    endGame(status);
    clearInterval(timerInterval);
  } else if (game.in_check()) {
    status += `, ${moveColor} is in check.`;
  }

  statusEl.textContent = status;
}

// ==================== BOARD INIT =========================
function init() {
  whiteClock = document.getElementById("whiteClock");
  blackClock = document.getElementById("blackClock");

  board = Chessboard("board", {
    draggable: true,
    position: "start",
    onDragStart,
    onDrop,
    onSnapEnd,
    moveSpeed: "slow",
    pieceTheme: "./chessboardjs/img/chesspieces/wikipedia/{piece}.png"
  });
  
  renderCaptured(); // Đảm bảo hiển thị ban đầu sạch sẽ
  updateClockDisplay();
}

document.addEventListener("DOMContentLoaded", init);
document.getElementById("startBtn").addEventListener("click", () => {
  if (gameStarted) {
    resetGame(); // chỉ reset, không khởi động lại
  } else {
    startGame(); // bắt đầu ván mới
  }
});
