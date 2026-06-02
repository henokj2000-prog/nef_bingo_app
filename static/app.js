// ── Telegram WebApp init ─────────────────────────────
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

// ── Global state ─────────────────────────────────────
let state = {
  user: null,
  balance: 0,
  gameId: null,
  stake: 0,
  myCards: [],
  lang: 'en',
  games_played: 0,
  wins: 0,
  total_won: 0,
  myCardData: []       // stores full card objects from server
};

let pollInterval = null;
let countdownInterval = null;

// ── Translations (simplified) ────────────────────────
const TEXTS = {
  en: {
    balance: 'Your Balance',
    deposit: 'Deposit',
    withdraw: 'Withdraw',
    playNow: '🎮 PLAY NOW',
    insufficient: 'Insufficient balance!',
    cardTaken: 'Card already taken',
    maxCards: 'Maximum 4 cards per game'
  },
  am: {
    balance: 'ሂሳብዎ',
    deposit: 'ተቀምጦ',
    withdraw: 'አውጣ',
    playNow: '🎮 አሁን ጫወት',
    insufficient: 'በቂ ሂሳብ የለም!',
    cardTaken: 'ካርዱ ተወስዷል',
    maxCards: 'በአንድ ጨዋታ ከ4 ካርድ በላይ አይቻልም'
  }
};
function T(key) { return TEXTS[state.lang][key] || key; }
function toggleLang() {
  state.lang = state.lang === 'en' ? 'am' : 'en';
  renderUI();
}

// ── Helper: API call ─────────────────────────────────
async function apiCall(path, method = 'GET', body = null) {
  try {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    return await res.json();
  } catch (e) {
    console.error('API error:', e);
    return null;
  }
}

// ── Load user from backend ───────────────────────────
async function loadUser() {
  const userId = tg?.initDataUnsafe?.user?.id || parseInt(localStorage.getItem('userId') || '99999');
  const username = tg?.initDataUnsafe?.user?.username || 'user';
  const fullName = tg?.initDataUnsafe?.user?.first_name || 'Player';
  if (!tg?.initDataUnsafe?.user?.id) localStorage.setItem('userId', userId);

  const data = await apiCall(`/api/player/${userId}?username=${encodeURIComponent(username)}&full_name=${encodeURIComponent(fullName)}`);
  if (data && !data.error) {
    state.user = data;
    state.balance = data.balance || 0;
    state.games_played = data.games_played || 0;
    state.wins = data.wins || 0;
    state.total_won = data.total_won || 0;

    if (data.active_game && !state.gameId) {
      state.gameId = data.active_game.game_id;
      state.stake = data.active_game.stake;
      await loadMyCards();
      if (data.active_game.status === 'running') {
        startGamePolling();
        goPage('pg-game');
      } else {
        goPage('pg-select');
        await refreshGameInfo();
      }
    }
    renderUI();
    return true;
  }
  return false;
}

function renderUI() {
  const balanceEl = document.getElementById('balanceDisplay');
  if (balanceEl) balanceEl.innerText = (state.balance || 0).toFixed(2) + ' ETB';
  const wdBalance = document.getElementById('wdBalanceShow');
  if (wdBalance) wdBalance.innerText = (state.balance || 0).toFixed(2) + ' ETB';
  const gamesEl = document.getElementById('stat-games');
  if (gamesEl) gamesEl.innerText = state.games_played || 0;
  const winsEl = document.getElementById('stat-wins');
  if (winsEl) winsEl.innerText = state.wins || 0;
  const wonEl = document.getElementById('stat-won');
  if (wonEl) wonEl.innerText = (state.total_won || 0).toFixed(0);
}

// ── Navigation ───────────────────────────────────────
function goPage(pageId) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const target = document.getElementById(pageId);
  if (target) target.classList.add('active');
  window.scrollTo(0, 0);
  if (pageId === 'pg-home') {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = null;
    loadUser();
  }
  if (pageId === 'pg-select') refreshGameInfo();
  if (pageId === 'pg-game') startGamePolling();
}

function navTo(pageId, el) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  el.classList.add('active');
  goPage(pageId);
}

// ── Stake selection ──────────────────────────────────
function buildStakeGrid() {
  const grid = document.getElementById('stakeGrid');
  if (!grid) return;
  grid.innerHTML = '';
  [10, 20, 50, 100].forEach(s => {
    const btn = document.createElement('div');
    btn.className = 'amount-btn';
    btn.innerText = s + ' ETB';
    btn.onclick = () => joinGame(s);
    grid.appendChild(btn);
  });
}

async function joinGame(stake) {
  if (state.balance < stake) {
    alert(T('insufficient'));
    return;
  }
  if (pollInterval) clearInterval(pollInterval);
  if (countdownInterval) clearInterval(countdownInterval);
  state.stake = stake;
  state.myCards = [];
  state.myCardData = [];
  state.gameId = null;

  const res = await apiCall('/api/join_game', 'POST', {
    user_id: state.user.user_id,
    stake: stake
  });
  if (!res || res.error) {
    alert(res?.error || 'Failed to join game');
    return;
  }
  state.gameId = res.game_id;
  // update UI
  document.getElementById('sel-prize').innerText = Math.floor((res.prize_pool || 0) * 0.8) + ' ETB';
  document.getElementById('sel-players').innerText = res.players;
  document.getElementById('sel-stake').innerText = stake + ' ETB';
  buildCardGrid(res.taken_cards || []);
  if (res.status === 'running') {
    goPage('pg-game');
  } else {
    startCountdown(res.countdown || 30);
    goPage('pg-select');
  }
  startGamePolling(); // will also handle game state updates
}

// ── Card grid (cards 1..200) ─────────────────────────
function buildCardGrid(takenCards) {
  const grid = document.getElementById('selGrid');
  if (!grid) return;
  grid.innerHTML = '';
  for (let i = 1; i <= 200; i++) {
    const isMine = state.myCards.includes(i);
    const isTaken = takenCards.includes(i) && !isMine;
    const btn = document.createElement('div');
    btn.className = 'cgrid-btn';
    if (isMine) btn.classList.add('mine');
    if (isTaken) btn.classList.add('taken');
    btn.innerText = isMine ? `🟡${i}` : isTaken ? `🔴${i}` : `${i}`;
    btn.id = `card-btn-${i}`;
    if (!isMine && !isTaken) {
      btn.onclick = () => pickCard(i);
    }
    grid.appendChild(btn);
  }
  document.getElementById('myCardCount').innerText = `${state.myCards.length}/4`;
}

async function pickCard(cardNumber) {
  if (state.myCards.length >= 4) {
    alert(T('maxCards'));
    return;
  }
  const btn = document.getElementById(`card-btn-${cardNumber}`);
  if (!btn || btn.classList.contains('taken') || btn.classList.contains('mine')) return;

  const res = await apiCall('/api/pick_card', 'POST', {
    user_id: state.user.user_id,
    game_id: state.gameId,
    card_number: cardNumber,
    stake: state.stake
  });
  if (!res || res.error) {
    alert(res?.error || 'Failed to pick card');
    return;
  }
  state.myCards.push(cardNumber);
  state.balance = res.balance;
  renderUI();
  // refresh the grid and my cards from server
  await refreshGameInfo();
  await loadMyCards();
  buildCardGrid(state.takenCards || []);
}

async function refreshGameInfo() {
  if (!state.gameId) return;
  const res = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
  if (res && !res.error) {
    state.takenCards = res.taken_cards || [];
    document.getElementById('sel-prize').innerText = Math.floor((res.prize_pool || 0) * 0.8) + ' ETB';
    document.getElementById('sel-players').innerText = res.players;
    buildCardGrid(state.takenCards);
  }
}

async function loadMyCards() {
  if (!state.gameId || !state.user) return;
  const res = await apiCall(`/api/my_cards/${state.gameId}?user_id=${state.user.user_id}`);
  if (res && res.cards) {
    state.myCardData = res.cards;
    state.myCards = res.cards.map(c => c.card_index);
  }
}

// ── Countdown ────────────────────────────────────────
function startCountdown(seconds) {
  if (countdownInterval) clearInterval(countdownInterval);
  let remaining = seconds;
  const cdEl = document.getElementById('cd1');
  const progEl = document.getElementById('prog1');
  if (cdEl) cdEl.innerText = remaining;
  if (progEl) progEl.style.width = '0%';
  countdownInterval = setInterval(() => {
    remaining--;
    if (cdEl) cdEl.innerText = Math.max(0, remaining);
    if (progEl) progEl.style.width = ((seconds - remaining) / seconds * 100) + '%';
    if (remaining <= 0) {
      clearInterval(countdownInterval);
      countdownInterval = null;
    }
  }, 1000);
}

// ── Game polling (critical for auto-advance) ─────────
function startGamePolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    if (!state.gameId) return;
    const res = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
    if (!res || res.error) return;
    if (res.status === 'waiting') {
      // still in selection phase – update prize/players
      const displayPrize = res.winners_share || Math.floor((res.prize_pool || 0) * 0.8);
      document.getElementById('sel-prize').innerText = displayPrize + ' ETB';
      document.getElementById('sel-players').innerText = res.players;
      // update taken cards if needed
      if (JSON.stringify(state.takenCards) !== JSON.stringify(res.taken_cards)) {
        state.takenCards = res.taken_cards;
        buildCardGrid(state.takenCards);
      }
    } else if (res.status === 'running') {
      if (countdownInterval) clearInterval(countdownInterval);
      countdownInterval = null;
      // update game screen
      updateGameUI(res);
      if (document.getElementById('pg-select')?.classList.contains('active')) {
        goPage('pg-game');
      }
    } else if (res.status === 'finished') {
      // Game finished – show winner and auto-redirect using next_game_id
      clearInterval(pollInterval);
      pollInterval = null;
      await loadMyCards();  // ensure latest card data
      showWinner(res);
    }
  }, 1500);
}

function updateGameUI(gameState) {
  const drawn = gameState.drawn_balls || [];
  const last = drawn[drawn.length - 1];
  if (last) {
    const letter = last[0];
    const num = last.slice(1);
    document.getElementById('bLetter').innerText = letter;
    document.getElementById('bNum').innerText = num;
  }
  document.getElementById('game-called').innerText = drawn.length + '/75';
  const displayPrize = gameState.winners_share || Math.floor((gameState.prize_pool || 0) * 0.8);
  document.getElementById('game-prize').innerText = displayPrize + ' ETB';
  const playersEl = document.getElementById('game-players');
  if (playersEl) playersEl.innerText = gameState.players;
  const recentChips = document.getElementById('recentChips');
  if (recentChips) {
    recentChips.innerHTML = drawn.slice(-6).reverse().map(b => `<div class="chip">${b}</div>`).join('');
  }
  renderMyCards(drawn);
}

// ★★★ FIXED FUNCTIONS: Convert ball strings to numbers for card marking ★★★
async function renderMyCards(drawnBalls) {
  await loadMyCards(); // refresh from server
  const wrap = document.getElementById('bingoCardsWrap');
  if (!wrap) return;
  if (!state.myCardData.length) {
    wrap.innerHTML = '<div style="text-align:center;color:var(--sub);padding:20px">No cards selected</div>';
    return;
  }
  // Convert drawn ball strings (e.g., "B12") to numbers (12)
  const drawnNumbers = drawnBalls.map(ball => {
    const num = parseInt(ball.slice(1));
    return isNaN(num) ? null : num;
  }).filter(n => n !== null);
  const drawnSet = new Set(drawnNumbers);
  wrap.innerHTML = '';
  for (const card of state.myCardData) {
    wrap.innerHTML += buildCardHTML(card.card_data, drawnSet, card.card_index);
  }
}

function buildCardHTML(cardData, drawnNumbersSet, cardIndex) {
  let html = `<div class="bingo-card-box">
    <div class="bcard-header"><div class="bcard-title">🎴 Card #${cardIndex}</div></div>
    <div class="bcol-headers"><div class="bcol-h">B</div><div class="bcol-h">I</div><div class="bcol-h">N</div><div class="bcol-h">G</div><div class="bcol-h">O</div></div>`;
  for (let r = 0; r < 5; r++) {
    html += '<div class="brow">';
    for (let c = 0; c < 5; c++) {
      let cell = cardData[r][c];
      if (cell === 'FREE') {
        html += '<div class="bcell free">FREE</div>';
      } else if (drawnNumbersSet.has(cell)) {
        html += '<div class="bcell hit">⭐</div>';
      } else {
        html += `<div class="bcell">${cell}</div>`;
      }
    }
    html += '</div>';
  }
  html += '</div>';
  return html;
}

// ── Winner screen with auto‑advance using next_game_id ──
function showWinner(gameState) {
  const prizeEach = gameState.prize_each || 0;
  const winners = gameState.winners || [];
  const winnerDiv = document.getElementById('winnerCards');
  if (winnerDiv) {
    if (!winners.length) {
      winnerDiv.innerHTML = '<div style="color:var(--sub);text-align:center;padding:10px">No winner this round</div>';
    } else {
      winnerDiv.innerHTML = winners.map(w => `
        <div class="w-card">
          <div class="w-name">👤 ${w.name}</div>
          <div style="font-size:11px;color:var(--sub)">Card #${w.card_number}</div>
          <div class="w-prize">+${w.prize || prizeEach} ETB</div>
        </div>`).join('');
    }
  }
  goPage('pg-winner');
  // reload balance
  loadUser().then(() => renderUI());
  // countdown and then use next_game_id if available
  let seconds = 5;
  const nextNum = document.getElementById('nextNum');
  if (nextNum) nextNum.innerText = seconds;
  const timer = setInterval(() => {
    seconds--;
    if (nextNum) nextNum.innerText = Math.max(0, seconds);
    if (seconds <= 0) {
      clearInterval(timer);
      if (gameState.next_game_id) {
        // join the next waiting game automatically
        state.gameId = gameState.next_game_id;
        state.myCards = [];
        state.myCardData = [];
        startGamePolling();
        goPage('pg-select');
        refreshGameInfo();
        startCountdown(30); // assume new game has 30s countdown
      } else {
        // fallback to stake selection
        state.gameId = null;
        goPage('pg-stake');
      }
    }
  }, 1000);
}

// ── Deposit / Withdraw / Inquiry (unchanged logic but using apiCall) ──
let selectedDepositAmount = 50;
function buildDepositAmountGrid() {
  const grid = document.getElementById('depAmtGrid');
  if (!grid) return;
  grid.innerHTML = '';
  [50, 100, 200, 500].forEach(amt => {
    const btn = document.createElement('div');
    btn.className = 'amount-btn' + (amt === 50 ? ' selected' : '');
    btn.innerText = amt + ' ETB';
    btn.onclick = () => {
      document.querySelectorAll('#depAmtGrid .amount-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      selectedDepositAmount = amt;
    };
    grid.appendChild(btn);
  });
}

let selectedPlatform = 'telebirr';
function selectPlatform(platform) {
  selectedPlatform = platform;
  const custom = parseFloat(document.getElementById('depCustomAmt')?.value);
  const amount = (custom && custom > 0) ? custom : selectedDepositAmount;
  document.getElementById('depAmountShow').innerText = amount + ' ETB';
  const platformNum = platform === 'telebirr' ? '0929 001 000' : '1000061737212';
  document.getElementById('depPlatformNum').innerText = platformNum;
  document.getElementById('depRef').innerText = 'BINGO-' + (state.user?.user_id || 'XXX');
  goPage('pg-dep-confirm');
}

async function submitDeposit() {
  const proof = document.getElementById('depProof').value.trim();
  const custom = parseFloat(document.getElementById('depCustomAmt')?.value);
  const amount = (custom && custom > 0) ? custom : selectedDepositAmount;
  if (!proof) {
    alert('Please paste transaction reference or SMS content');
    return;
  }
  const res = await apiCall('/api/deposit', 'POST', {
    user_id: state.user.user_id,
    amount: amount,
    platform: selectedPlatform,
    tx_ref: proof
  });
  if (!res) alert('Network error');
  else if (res.error) alert('❌ ' + res.error);
  else {
    if (res.approved) {
      state.balance = res.balance;
      renderUI();
      alert('✅ ' + res.message);
    } else {
      alert('⏳ ' + res.message);
    }
    document.getElementById('depProof').value = '';
    goPage('pg-home');
  }
}

function setWdPlatform(platform, el) {
  document.getElementById('wd-platform').value = platform;
  document.querySelectorAll('#pg-withdraw .platform-btn').forEach(b => b.style.borderColor = '');
  el.style.borderColor = 'var(--gold)';
}

async function submitWithdraw() {
  const amount = parseFloat(document.getElementById('wdAmount').value);
  const account = document.getElementById('wdAccount').value.trim();
  const platform = document.getElementById('wd-platform').value;
  if (isNaN(amount) || amount < 50) {
    alert('Minimum withdrawal 50 ETB');
    return;
  }
  if (!account) {
    alert('Enter account number');
    return;
  }
  if (amount > state.balance) {
    alert(T('insufficient'));
    return;
  }
  const res = await apiCall('/api/withdraw', 'POST', {
    user_id: state.user.user_id,
    amount: amount,
    platform: platform,
    account_no: account
  });
  if (res && res.success) {
    state.balance -= amount;
    renderUI();
    alert('✅ Withdrawal requested. Processed within 24h.');
    goPage('pg-home');
  } else {
    alert('❌ ' + (res?.error || 'Request failed'));
  }
}

async function submitInquiry() {
  const subject = document.getElementById('inqSubject').value.trim();
  const message = document.getElementById('inqMessage').value.trim();
  if (!subject || !message) {
    alert('Please fill subject and message');
    return;
  }
  const res = await apiCall('/api/inquiry', 'POST', {
    user_id: state.user.user_id,
    subject: subject,
    message: message
  });
  if (res && res.success) {
    alert('✅ Inquiry sent. Admin will respond soon.');
    document.getElementById('inqSubject').value = '';
    document.getElementById('inqMessage').value = '';
    goPage('pg-help');
  } else {
    alert('❌ Failed to send');
  }
}

function showAdminPanel() {
  window.open('/admin', '_blank');
}

// ── Initialization ───────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  buildStakeGrid();
  buildDepositAmountGrid();
  await loadUser();
  renderUI();
  goPage('pg-home');
});
