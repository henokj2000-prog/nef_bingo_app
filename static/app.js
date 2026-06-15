// Telegram WebApp init
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

// Global state
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
  myCardData: [],
  takenCards: [],
  allowedStakes: [10, 20, 50, 100]
};

let pollInterval = null;
let countdownPollInterval = null;

// ---------- Translations (EN and AM) ----------
const LANG = {
  en: {
    'balance': 'Your Balance', 'deposit': 'Deposit', 'withdraw': 'Withdraw',
    'games': 'Games', 'wins': 'Wins', 'won': 'Won ETB',
    'playNow': 'PLAY NOW', 'selectStake': 'Select Stake',
    'gameStartsIn': 'Game starts in', 'yourCards': 'Your cards',
    'prizePool': 'Prize Pool', 'players': 'Players', 'stake': 'Stake',
    'called': 'Called', 'recent': 'Recent', 'bingo': 'BINGO!',
    'nextGame': 'Next game', 'seconds': 'seconds', 'back': 'Back',
    'insufficient': 'Insufficient balance',
    'maxCards': 'Max 4 cards per game', 'depositSuccess': '✅ {amount} ETB credited!',
    'depositPending': '⏳ Deposit submitted for admin review.',
    'withdrawSuccess': 'Withdrawal request submitted.', 'inquirySuccess': 'Inquiry sent.',
    'gameCancelled': 'Game cancelled due to insufficient players. Refunded.',
    'howToPlay': 'How to Play', 'help': 'Help', 'faq': 'FAQ',
    'sendInquiry': 'Send Inquiry', 'subject': 'Subject', 'message': 'Message',
    'amount': 'Amount', 'accountNumber': 'Account Number', 'platform': 'Platform',
    'transactionRef': 'Transaction Reference', 'your_referral_link': '🔗 Your Referral Link',
    'copy_link': '📋 Copy Link',
    'referral_bonus_text': '✨ Share this link with friends. When they register, you get <strong>{bonus} ETB</strong> instantly!',
    'referral_commission_text': '🎁 Plus, you earn <strong>{percent}% of the prize pool</strong> every time they win a game.',
    'copy_success': 'Link copied!', 'copy_fail': 'Failed to copy', 'leave_game': 'Leave Game'
  },
  am: {
    'balance': 'የእርስዎ ቀሪ ሒሳብ', 'deposit': 'ተቀማጭ', 'withdraw': 'ማውጣት',
    'games': 'ጨዋታዎች', 'wins': 'ድሎች', 'won': 'አሸንፈዋል ETB',
    'playNow': 'አሁን ተጫወት', 'selectStake': 'ውርርድ ይምረጡ',
    'gameStartsIn': 'ጨዋታ የሚጀምረው በ', 'yourCards': 'ካርዶችዎ',
    'prizePool': 'ሽልማት ገንዘብ', 'players': 'ተጫዋቾች', 'stake': 'ውርርድ',
    'called': 'የተጠራ', 'recent': 'የቅርብ ጊዜ', 'bingo': 'ቢንጎ!',
    'nextGame': 'ቀጣይ ጨዋታ', 'seconds': 'ሰከንዶች', 'back': 'ተመለስ',
    'insufficient': 'በቂ ገንዘብ የለም',
    'maxCards': 'በአንድ ጨዋታ ከ4 ካርዶች መጠቀም አይቻልም', 'depositSuccess': '✅ {amount} ETB ተጨምሯል!',
    'depositPending': '⏳ ተቀማጭ ገንዘብ ለማጽደቅ ቀርቧል።',
    'withdrawSuccess': 'የማውጣት ጥያቄ ተልኳል።', 'inquirySuccess': 'መልእክት ተልኳል።',
    'gameCancelled': 'ጨዋታው በበቂ ተጫዋቾች እጥረት ተሰርዟል። ገንዘብዎ ተመልሷል።',
    'howToPlay': 'እንዴት መጫወት ይቻላል', 'help': 'እርዳታ', 'faq': 'በየጥ',
    'sendInquiry': 'መልእክት ላክ', 'subject': 'ርዕስ', 'message': 'መልእክት',
    'amount': 'መጠን', 'accountNumber': 'የሂሳብ ቁጥር', 'platform': 'መድረክ',
    'transactionRef': 'የግብይት ማጣቀሻ', 'your_referral_link': '🔗 የእርስዎ ማጣቀሻ ሊንክ',
    'copy_link': '📋 ሊንኩን ቅዳ',
    'referral_bonus_text': '✨ ይህን ሊንክ ከጓደኞችዎ ጋር ያጋሩ። ሲመዘገቡ እርስዎ <strong>{bonus} ETB</strong> ወዲያውኑ ያገኛሉ!',
    'referral_commission_text': '🎁 በተጨማሪም እርስዎ በሚያሸንፉበት ጊዜ ከሽልማቱ ገንዘብ <strong>{percent}%</strong> ያገኛሉ።',
    'copy_success': 'ሊንክ ተቀድቷል!', 'copy_fail': 'መቅዳት አልተሳካም', 'leave_game': 'ጨዋታ ለቀቅ'
  }
};

function T(key, vars = {}) {
  let text = (LANG[state.lang] && LANG[state.lang][key]) || (LANG.en && LANG.en[key]) || key;
  for (let [k, v] of Object.entries(vars)) text = text.replace(`{${k}}`, v);
  return text;
}

function updateUILanguage() {
  const elements = document.querySelectorAll('[data-i18n]');
  for (let el of elements) {
    const key = el.getAttribute('data-i18n');
    if (key) el.innerText = T(key);
  }
  const ids = {
    'balanceLabel': 'balance', 'depositBtnText': 'deposit', 'withdrawBtnText': 'withdraw',
    'statGamesLbl': 'games', 'statWinsLbl': 'wins', 'statWonLbl': 'won',
    'playBtn': 'playNow', 'stakeTitle': 'selectStake', 'gameStartsLabel': 'gameStartsIn',
    'yourCardsLabel': 'yourCards', 'selPrizeLbl': 'prizePool', 'selPlayersLbl': 'players',
    'selStakeLbl': 'stake', 'gamePrizeLbl': 'prizePool', 'gamePlayersLbl': 'players',
    'gameCalledLbl': 'called', 'recentLabel': 'recent', 'winnerTitle': 'bingo',
    'nextGameLabel': 'nextGame', 'secondsLabel': 'seconds', 'stakeBackText': 'back',
    'selectHomeBtn': 'back', 'gameHomeBtn': 'back', 'winnerHomeBtn': 'back',
    'depBackText': 'back', 'confBackText': 'back', 'wdBackText': 'back',
    'inqBackText': 'back', 'submitDepositBtn': 'deposit', 'requestWithdrawBtn': 'withdraw',
    'sendInquiryBtn': 'sendInquiry', 'subjectLabel': 'subject', 'messageLabel': 'message',
    'amountLabel': 'amount', 'accountNumberLabel': 'accountNumber',
    'wdPlatformTitle': 'platform', 'referenceLabel': 'transactionRef', 'leaveGameBtn': 'leave_game'
  };
  for (let [id, key] of Object.entries(ids)) {
    const el = document.getElementById(id);
    if (el) el.innerText = T(key);
  }
}

// ---------- API helper ----------
async function apiCall(path, method = 'GET', body = null) {
  try {
    const headers = { 'Content-Type': 'application/json' };
    if (window.Telegram?.WebApp?.initData) {
      headers['X-Telegram-Init-Data'] = window.Telegram.WebApp.initData;
    }
    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    return await res.json();
  } catch (e) {
    console.error('API error:', e);
    return null;
  }
}

// ---------- Load allowed stakes from server ----------
async function loadStakes() {
  const res = await apiCall('/api/settings/stakes');
  if (res && res.stakes && Array.isArray(res.stakes)) {
    state.allowedStakes = res.stakes;
  }
}

// ---------- Load user & registration ----------
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

    if (!state.user.phone) {
      goPage('pg-register');
      autoFillReferralCode();
      return;
    }
    if (state.user.language && LANG[state.user.language]) state.lang = state.user.language;
    else state.lang = 'en';
    updateUILanguage();

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
        startCountdownPolling();
      }
    }
    renderUI();
    displayReferralInfo();
    loadLeaderboard();
    loadRecentGames();
    loadLatestNotification();
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

function toggleLang() {
  state.lang = state.lang === 'en' ? 'am' : 'en';
  updateUILanguage();
  displayReferralInfo();
  apiCall('/api/update_profile', 'POST', { user_id: state.user.user_id, language: state.lang });
}

// ---------- Navigation ----------
function goPage(pageId) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const target = document.getElementById(pageId);
  if (target) target.classList.add('active');
  window.scrollTo(0, 0);
  if (pageId === 'pg-register') autoFillReferralCode();
  if (pageId === 'pg-home') {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    if (countdownPollInterval) { clearInterval(countdownPollInterval); countdownPollInterval = null; }
    loadUser();
    loadLeaderboard();
    loadRecentGames();
    displayReferralInfo();
  }
  if (pageId === 'pg-select') startCountdownPolling();
  if (pageId === 'pg-game') startGamePolling();
}

function navTo(pageId, el) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  el.classList.add('active');
  goPage(pageId);
}

// ---------- Registration ----------
let selectedRegLang = 'en';
function selectRegLang(lang) {
  selectedRegLang = lang;
  document.querySelectorAll('.reg-lang-btn').forEach(btn => {
    btn.style.borderColor = 'rgba(255,215,0,0.3)';
    btn.style.background = 'var(--card)';
  });
  const selected = document.querySelector(`.reg-lang-btn[data-lang="${lang}"]`);
  if (selected) {
    selected.style.borderColor = 'var(--gold)';
    selected.style.background = 'rgba(255,215,0,0.2)';
  }
}

function getReferralCodeFromUrl() {
  const urlParams = new URLSearchParams(window.location.search);
  return urlParams.get('ref');
}

function autoFillReferralCode() {
  const refCode = getReferralCodeFromUrl();
  if (refCode) {
    const inputField = document.getElementById('regReferralCode');
    if (inputField) inputField.value = refCode;
  }
}

async function completeRegistration() {
  const phone = document.getElementById('regPhone').value.trim();
  const referralCode = document.getElementById('regReferralCode')?.value.trim() || '';
  if (!phone || phone.length < 9) {
    alert('Please enter a valid phone number (e.g., 0912345678)');
    return;
  }
  const res = await apiCall('/api/update_profile', 'POST', {
    user_id: state.user.user_id,
    phone,
    language: selectedRegLang,
    referral_code: referralCode
  });
  if (res && res.success) {
    state.user.phone = phone;
    state.user.language = selectedRegLang;
    state.lang = selectedRegLang;
    updateUILanguage();
    goPage('pg-home');
    displayReferralInfo();
  } else {
    alert(res?.error || 'Registration failed. Please try again.');
  }
}

// ---------- Game functions ----------
function buildStakeGrid() {
  const grid = document.getElementById('stakeGrid');
  if (!grid) return;
  grid.innerHTML = '';
  state.allowedStakes.forEach(s => {
    const btn = document.createElement('div');
    btn.className = 'amount-btn';
    btn.innerText = s + ' ETB';
    btn.onclick = () => joinGame(s);
    grid.appendChild(btn);
  });
}

async function joinGame(stake) {
  if (!state.user) return;
  if (state.balance < stake) { alert(T('insufficient')); return; }
  if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
  if (countdownPollInterval) { clearInterval(countdownPollInterval); countdownPollInterval = null; }

  state.stake = stake;
  state.myCards = [];
  state.myCardData = [];
  state.takenCards = [];
  state.gameId = null;

  const res = await apiCall('/api/join_game', 'POST', { stake });
  if (!res || res.error) { alert(res?.error || 'Failed to join game'); return; }

  if (res.game_in_progress) {
    state.gameId = res.game_id;
    updateGameUI(res);
    startGamePolling();
    goPage('pg-game');
    const banner = document.getElementById('notificationBanner');
    const notifyText = document.getElementById('notifyText');
    if (banner && notifyText) {
      notifyText.innerHTML = '🎲 A game is in progress. You are watching the current round.';
      banner.style.display = 'block';
      setTimeout(() => banner.style.display = 'none', 8000);
    }
    return;
  }

  state.gameId = res.game_id;

  // Show initial countdown
  const remaining = res.countdown_remaining || 30;
  const cdEl = document.getElementById('cd1');
  const progEl = document.getElementById('prog1');
  if (cdEl) cdEl.innerText = remaining;
  if (progEl) progEl.style.width = ((30 - remaining) / 30 * 100) + '%';

  document.getElementById('sel-prize').innerText = '0 ETB';
  const playersEl = document.getElementById('sel-players');
  if (playersEl) playersEl.innerText = 'Waiting for players…';
  document.getElementById('sel-stake').innerText = stake + ' ETB';

  await refreshGameInfo();
  await loadMyCards();
  buildCardGrid(state.takenCards || []);
  startCountdownPolling();
  goPage('pg-select');
}

function buildCardGrid(takenCards) {
  const grid = document.getElementById('selGrid');
  if (!grid) return;
  grid.innerHTML = '';
  for (let i = 1; i <= 500; i++) {
    const isMine = state.myCards.includes(i);
    const isTaken = takenCards.includes(i) && !isMine;
    const btn = document.createElement('div');
    btn.className = 'cgrid-btn';
    if (isMine) btn.classList.add('mine');
    if (isTaken) btn.classList.add('taken');
    btn.innerText = isMine ? `🟡${i}` : isTaken ? `🔴${i}` : `${i}`;
    btn.id = `card-btn-${i}`;
    if (!isMine && !isTaken) btn.onclick = () => pickCard(i);
    grid.appendChild(btn);
  }
  document.getElementById('myCardCount').innerText = `${state.myCards.length}/4`;
}

async function pickCard(cardNumber) {
  if (!state.user || !state.gameId) return;
  if (state.myCards.length >= 4) { alert(T('maxCards')); return; }
  const btn = document.getElementById(`card-btn-${cardNumber}`);
  if (!btn || btn.classList.contains('taken') || btn.classList.contains('mine')) return;

  // Optimistic UI — update button immediately, no pre-check API call needed
  btn.classList.add('mine');
  btn.classList.remove('taken');
  btn.innerText = `🟡${cardNumber}`;
  btn.onclick = null;

  const res = await apiCall('/api/pick_card', 'POST', {
    game_id: state.gameId,
    card_number: cardNumber,
    stake: state.stake
  });

  if (!res || res.error) {
    // Revert optimistic update on failure
    btn.classList.remove('mine');
    btn.innerText = `${cardNumber}`;
    btn.onclick = () => pickCard(cardNumber);
    if (res?.error === 'Game has already started or finished') {
      alert('Game already started! Please wait for the next game.');
      location.reload();
    } else {
      alert(res?.error || 'Failed to pick card');
    }
    return;
  }

  // Update state without rebuilding 500 buttons
  state.myCards.push(cardNumber);
  if (res.balance !== undefined) {
    state.balance = res.balance;
    renderUI();
  }
  // Only update newly taken buttons from server response
  if (res.taken_cards) {
    const newTaken = res.taken_cards.filter(n => !state.takenCards.includes(n) && n !== cardNumber);
    newTaken.forEach(n => {
      const takenBtn = document.getElementById(`card-btn-${n}`);
      if (takenBtn && !takenBtn.classList.contains('mine')) {
        takenBtn.classList.add('taken');
        takenBtn.innerText = `🔴${n}`;
        takenBtn.onclick = null;
      }
    });
    state.takenCards = res.taken_cards;
  }
  document.getElementById('myCardCount').innerText = `${state.myCards.length}/4`;
}

async function leaveGame() {
  if (!state.gameId || !state.user) return;
  if (confirm(T('leave_game') + '? You will be refunded for unpicked cards.')) {
    const res = await apiCall('/api/withdraw_from_game', 'POST', {
      user_id: state.user.user_id,
      game_id: state.gameId
    });
    if (res && res.success) {
      alert(res.message || 'Left game. Refunded.');
      if (res.balance !== undefined) {
        state.balance = res.balance;
        renderUI();
      }
      state.gameId = null;
      state.myCards = [];
      state.myCardData = [];
      if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
      if (countdownPollInterval) { clearInterval(countdownPollInterval); countdownPollInterval = null; }
      goPage('pg-home');
      loadUser();
    } else {
      alert('Failed to leave: ' + (res?.error || 'Unknown error'));
    }
  }
}

async function refreshGameInfo() {
  if (!state.gameId || !state.user) return;
  const res = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
  if (res && !res.error) {
    state.takenCards = res.taken_cards || [];
    const prize = res.total_winners_prize || Math.floor((res.prize_pool || 0) * 0.8);
    document.getElementById('sel-prize').innerText = prize + ' ETB';
    const playersEl = document.getElementById('sel-players');
    if (playersEl) {
      playersEl.innerText = (res.players || 0) === 0 ? 'Waiting for players…' : res.players;
    }
    buildCardGrid(state.takenCards);
  }
}

async function loadMyCards() {
  if (!state.gameId || !state.user) return;
  const res = await apiCall(`/api/my_cards/${state.gameId}?user_id=${state.user.user_id}`);
  if (res && res.cards) {
    state.myCardData = res.cards;
    // FIX: was c.card_index — backend returns card_number
    state.myCards = res.cards.map(c => c.card_number).filter(n => n != null);
  }
}

// ---------- Countdown polling ----------
function startCountdownPolling() {
  if (countdownPollInterval) clearInterval(countdownPollInterval);
  const cdEl = document.getElementById('cd1');
  const progEl = document.getElementById('prog1');

  countdownPollInterval = setInterval(async () => {
    if (!state.gameId || !state.user) {
      clearInterval(countdownPollInterval);
      countdownPollInterval = null;
      return;
    }
    const gameState = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
    if (!gameState || gameState.error) {
      clearInterval(countdownPollInterval);
      countdownPollInterval = null;
      state.gameId = null;
      state.myCards = [];
      goPage('pg-home');
      loadUser();
      return;
    }
    if (gameState.status === 'running') {
      clearInterval(countdownPollInterval);
      countdownPollInterval = null;
      goPage('pg-game');
      startGamePolling();
      return;
    }
    if (gameState.status === 'cancelled' || (gameState.status === 'finished' && gameState.cancelled === 1)) {
      clearInterval(countdownPollInterval);
      countdownPollInterval = null;
      alert(T('gameCancelled'));
      state.gameId = null;
      state.myCards = [];
      goPage('pg-home');
      loadUser();
      return;
    }
    if (gameState.status === 'finished') {
      clearInterval(countdownPollInterval);
      countdownPollInterval = null;
      await loadMyCards();
      showWinner(gameState);
      return;
    }
    // FIX: was gameState.countdown — backend returns countdown_remaining
    if (gameState.status === 'waiting') {
      const remaining = typeof gameState.countdown_remaining === 'number' ? gameState.countdown_remaining : 0;
      if (cdEl) cdEl.innerText = remaining;
      if (progEl) progEl.style.width = (Math.max(0, (30 - remaining) / 30 * 100)) + '%';

      // Update prize and players
      const prize = gameState.total_winners_prize || Math.floor((gameState.prize_pool || 0) * 0.8);
      const selPrize = document.getElementById('sel-prize');
      if (selPrize) selPrize.innerText = prize + ' ETB';
      const selPlayers = document.getElementById('sel-players');
      if (selPlayers) selPlayers.innerText = (gameState.players || 0) === 0 ? 'Waiting for players…' : gameState.players;

      // Update card grid if taken cards changed
      const newTaken = gameState.taken_cards || [];
      if (JSON.stringify(state.takenCards) !== JSON.stringify(newTaken)) {
        state.takenCards = newTaken;
        buildCardGrid(state.takenCards);
      }
    }
  }, 1000);
}

// ---------- Game polling ----------
function startGamePolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    if (!state.gameId || !state.user) return;
    const res = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
    if (!res || res.error) return;

    if (res.status === 'waiting') {
      if (document.getElementById('pg-select')?.classList.contains('active')) {
        if (!countdownPollInterval) startCountdownPolling();
      }
    } else if (res.status === 'running') {
      updateGameUI(res);
      if (document.getElementById('pg-select')?.classList.contains('active')) goPage('pg-game');
    } else if (res.status === 'cancelled' || (res.status === 'finished' && res.cancelled === 1)) {
      clearInterval(pollInterval);
      pollInterval = null;
      alert(T('gameCancelled'));
      state.gameId = null;
      state.myCards = [];
      state.myCardData = [];
      goPage('pg-home');
      loadUser();
    } else if (res.status === 'finished') {
      clearInterval(pollInterval);
      pollInterval = null;
      await loadMyCards();
      showWinner(res);
    }
  }, 1500);
}

function updateGameUI(gameState) {
  const drawn = gameState.drawn_balls || [];
  const last = drawn[drawn.length - 1];
  if (last) {
    const letterEl = document.getElementById('bLetter');
    const numEl = document.getElementById('bNum');
    if (letterEl) letterEl.innerText = last[0];
    if (numEl) numEl.innerText = last.slice(1);
  }
  const calledEl = document.getElementById('game-called');
  if (calledEl) calledEl.innerText = drawn.length + '/75';

  const displayPrize = gameState.total_winners_prize || Math.floor((gameState.prize_pool || 0) * 0.8);
  const prizeEl = document.getElementById('game-prize');
  if (prizeEl) prizeEl.innerText = displayPrize + ' ETB';

  const playersEl = document.getElementById('game-players');
  // FIX: was gameState.players — backend now returns players
  if (playersEl) playersEl.innerText = gameState.players || 0;

  const chipsEl = document.getElementById('recentChips');
  if (chipsEl) chipsEl.innerHTML = drawn.slice(-6).reverse().map(b => `<div class="chip">${b}</div>`).join('');

  renderMyCards(drawn);
}

async function renderMyCards(drawnBalls) {
  const wrap = document.getElementById('bingoCardsWrap');
  if (!wrap) return;
  await loadMyCards();
  if (!state.myCardData || !state.myCardData.length) {
    wrap.innerHTML = '<div style="text-align:center;color:var(--sub);padding:20px">No cards selected</div>';
    return;
  }
  // Parse drawn numbers from ball strings like "B15", "N32"
  const drawnNumbers = (drawnBalls || []).map(b => {
    const num = parseInt(b.replace(/[^0-9]/g, ''));
    return isNaN(num) ? null : num;
  }).filter(n => n !== null);
  const drawnSet = new Set(drawnNumbers);

  // FIX: was card.card_data and card.card_index — backend returns card.card and card.card_number
  const cardsHtml = state.myCardData.map(card => buildCardHTML(card.card, drawnSet, card.card_number)).join('');
  const cardCount = state.myCardData.length;
  let gridClass = 'cards-1';
  if (cardCount === 2) gridClass = 'cards-2';
  else if (cardCount === 3) gridClass = 'cards-3';
  else if (cardCount === 4) gridClass = 'cards-4';
  wrap.innerHTML = `<div class="bingo-grid ${gridClass}">${cardsHtml}</div>`;
}

function buildCardHTML(cardData, drawnNumbersSet, cardNumber) {
  if (!cardData) return '<div class="bingo-card-box"><p style="color:var(--sub);padding:10px">Card data unavailable</p></div>';
  let html = `<div class="bingo-card-box">
    <div class="bcard-header"><div class="bcard-title">🎴 Card #${cardNumber || '?'}</div></div>
    <div class="bcol-headers">`;
  ['B','I','N','G','O'].forEach(l => html += `<div class="bcol-h">${l}</div>`);
  html += '</div>';
  // cardData is 5x5 array; center cell (row 2, col 2) is FREE
  for (let r = 0; r < 5; r++) {
    html += '<div class="brow">';
    for (let c = 0; c < 5; c++) {
      const cell = cardData[r] ? cardData[r][c] : null;
      if (cell === 'FREE' || cell === null) {
        html += '<div class="bcell free">FREE</div>';
      } else if (drawnNumbersSet.has(Number(cell))) {
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

function showWinner(gameState) {
  const winnerDiv = document.getElementById('winnerCards');
  if (winnerDiv) {
    const details = gameState.winner_details || [];
    if (details.length) {
      const prizePool = gameState.total_winners_prize || Math.floor((gameState.prize_pool || 0) * 0.8);
      const prizePerWinner = prizePool / details.length;
      winnerDiv.innerHTML = details.map(w => `
        <div style="background:rgba(255,215,0,0.2);margin:6px;padding:8px;border-radius:8px;">
          🏆 ${w.username || 'Player'} - Card #${w.card_number} +${prizePerWinner.toFixed(2)} ETB
        </div>
      `).join('');
    } else {
      winnerDiv.innerHTML = '<div style="color:var(--sub);text-align:center;padding:10px">No winner this round</div>';
    }
  }
  goPage('pg-winner');
  loadUser().then(() => renderUI());

  let seconds = 5;
  const nextNum = document.getElementById('nextNum');
  if (nextNum) nextNum.innerText = seconds;

  if (window.winnerTimer) clearInterval(window.winnerTimer);
  window.winnerTimer = setInterval(async () => {
    seconds--;
    if (nextNum) nextNum.innerText = Math.max(0, seconds);
    if (seconds <= 0) {
      clearInterval(window.winnerTimer);
      window.winnerTimer = null;
      state.myCards = [];
      state.myCardData = [];
      state.takenCards = [];
      if (gameState.next_game_id) {
        state.gameId = gameState.next_game_id;
        state.stake = gameState.stake || state.stake;
        await refreshGameInfo();
        await loadMyCards();
        startCountdownPolling();
        goPage('pg-select');
      } else {
        state.gameId = null;
        await joinGame(state.stake);
      }
    }
  }, 1000);
}

// ---------- Deposit / Withdraw / Inquiry ----------
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
  // FIX: API returns {key, value} — was reading tele.telebirr_number (undefined)
  const platformNum = platform === 'telebirr'
    ? (window.telebirrNumber || '0929 001 000')
    : (window.cbeNumber || '1000061737212');
  document.getElementById('depPlatformNum').innerText = platformNum;
  document.getElementById('depRef').innerText = 'BINGO-' + (state.user?.user_id || 'XXX');
  goPage('pg-dep-confirm');
}

async function submitDeposit() {
  const proof = document.getElementById('depProof').value.trim();
  const custom = parseFloat(document.getElementById('depCustomAmt')?.value);
  const amount = (custom && custom > 0) ? custom : selectedDepositAmount;
  if (!proof) { alert('Please paste transaction reference or SMS content'); return; }
  const res = await apiCall('/api/deposit', 'POST', {
    user_id: state.user.user_id,
    amount,
    platform: selectedPlatform,
    proof
  });
  if (!res) alert('Network error');
  else if (res.error) alert('❌ ' + res.error);
  else {
    alert(T('depositPending'));
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
  if (isNaN(amount) || amount < 50) { alert('Minimum withdrawal 50 ETB'); return; }
  if (!account) { alert('Enter account number'); return; }
  if (amount > state.balance) { alert(T('insufficient')); return; }
  const res = await apiCall('/api/withdraw', 'POST', {
    user_id: state.user.user_id,
    amount,
    method: platform,
    account_no: account
  });
  if (res && res.success) {
    state.balance -= amount;
    renderUI();
    alert(T('withdrawSuccess'));
    goPage('pg-home');
  } else {
    alert('❌ ' + (res?.error || 'Request failed'));
  }
}

async function submitInquiry() {
  const subject = document.getElementById('inqSubject').value.trim();
  const message = document.getElementById('inqMessage').value.trim();
  if (!subject || !message) { alert('Please fill subject and message'); return; }
  const res = await apiCall('/api/inquiry', 'POST', { user_id: state.user.user_id, subject, message });
  if (res && res.success) {
    alert(T('inquirySuccess'));
    document.getElementById('inqSubject').value = '';
    document.getElementById('inqMessage').value = '';
    goPage('pg-help');
  } else {
    alert('❌ Failed to send');
  }
}

async function loadLatestNotification() {
  try {
    const res = await fetch('/api/notifications/latest');
    const data = await res.json();
    if (data.message) {
      const banner = document.getElementById('notificationBanner');
      const text = document.getElementById('notifyText');
      if (banner && text) {
        text.innerText = data.message;
        banner.style.display = 'block';
        setTimeout(() => banner.style.display = 'none', 10000);
      }
    }
  } catch(e) { console.error(e); }
}

function showAdminPanel() { window.open('/admin', '_blank'); }

async function loadPlatformNumbers() {
  try {
    // FIX: API returns {key, value} — was reading tele.telebirr_number (undefined)
    const tele = await apiCall('/api/settings/telebirr_number');
    const cbe = await apiCall('/api/settings/cbe_number');
    if (tele && tele.value) window.telebirrNumber = tele.value;
    if (cbe && cbe.value) window.cbeNumber = cbe.value;
    const telePlace = document.getElementById('telebirrNumberPlaceholder');
    const cbePlace = document.getElementById('cbeNumberPlaceholder');
    if (telePlace) telePlace.innerText = window.telebirrNumber || '0929 001 000';
    if (cbePlace) cbePlace.innerText = window.cbeNumber || '1000061737212';
  } catch(e) { console.error(e); }
}

// ---------- Referral ----------
async function displayReferralInfo() {
  if (!state.user || !state.user.user_id) return;
  const data = await apiCall(`/api/referral_stats/${state.user.user_id}`);
  if (data && data.referral_code) {
    const baseUrl = window.location.origin;
    const fullLink = `${baseUrl}?ref=${data.referral_code}`;
    const linkElem = document.getElementById('referralLinkAnchor');
    if (linkElem) { linkElem.href = fullLink; linkElem.innerText = fullLink; }
    const card = document.getElementById('referralCard');
    if (card) card.style.display = 'block';
    const bonusAmount = 10;
    const commissionPercent = 5;
    const msgElem = document.getElementById('referralMessage');
    if (msgElem) msgElem.innerHTML = `${T('referral_bonus_text', { bonus: bonusAmount })}<br>${T('referral_commission_text', { percent: commissionPercent })}`;
  }
}

function copyReferralLink() {
  const link = document.getElementById('referralLinkAnchor')?.href;
  if (!link) return;
  navigator.clipboard.writeText(link)
    .then(() => alert(T('copy_success')))
    .catch(() => alert(T('copy_fail')));
}

// ---------- Leaderboard ----------
async function loadLeaderboard() {
  const res = await apiCall('/api/leaderboard');
  if (res && Array.isArray(res)) {
    const container = document.getElementById('leaderboardList');
    if (!container) return;
    const top5 = res.slice(0, 5);
    if (!top5.length) {
      container.innerHTML = '<div style="text-align:center;color:var(--sub);padding:10px">No players yet</div>';
    } else {
      container.innerHTML = top5.map((p, idx) => `
        <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05)">
          <span>${idx+1}. ${p.full_name || p.username || 'Player'}</span>
          <span style="color:var(--gold)">${(p.total_won || p.balance || 0).toFixed(0)} ETB</span>
        </div>
      `).join('');
    }
  }
}

// ---------- Recent Games ----------
async function loadRecentGames() {
  if (!state.user) return;
  const res = await apiCall(`/api/recent_games/${state.user.user_id}`);
  const container = document.getElementById('recentGamesList');
  if (!container) return;
  if (!res || !res.length) {
    container.innerHTML = '<div style="text-align:center;color:var(--sub);padding:10px">No games yet</div>';
    return;
  }
  container.innerHTML = res.slice(0, 5).map(g => `
    <div style="border-bottom:1px solid rgba(255,255,255,0.1);padding:8px">
      Game #${g.id} | Stake: ${g.stake} ETB | Prize: ${g.prize_pool} ETB |
      ${g.cancelled ? '❌ Cancelled' : g.status === 'finished' ? '✅ Finished' : g.status}
    </div>
  `).join('');
}

// ---------- Initialization ----------
window.addEventListener('DOMContentLoaded', async () => {
  buildStakeGrid();
  buildDepositAmountGrid();
  await loadPlatformNumbers();
  await loadStakes();
  buildStakeGrid();
  await loadUser();
  renderUI();
  if (!document.querySelector('.screen.active')) {
    goPage('pg-home');
  }
});
