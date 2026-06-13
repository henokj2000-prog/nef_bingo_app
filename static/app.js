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
    'copy_link': '📋 Copy Link', 'referral_bonus_text': '✨ Share this link with friends. When they register, you get <strong>{bonus} ETB</strong> instantly!',
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
    'copy_link': '📋 ሊንኩን ቅዳ', 'referral_bonus_text': '✨ ይህን ሊንክ ከጓደኞችዎ ጋር ያጋሩ። ሲመዘገቡ እርስዎ <strong>{bonus} ETB</strong> ወዲያውኑ ያገኛሉ!',
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
  if (document.getElementById('balanceLabel')) document.getElementById('balanceLabel').innerText = T('balance');
  if (document.getElementById('depositBtnText')) document.getElementById('depositBtnText').innerText = T('deposit');
  if (document.getElementById('withdrawBtnText')) document.getElementById('withdrawBtnText').innerText = T('withdraw');
  if (document.getElementById('statGamesLbl')) document.getElementById('statGamesLbl').innerText = T('games');
  if (document.getElementById('statWinsLbl')) document.getElementById('statWinsLbl').innerText = T('wins');
  if (document.getElementById('statWonLbl')) document.getElementById('statWonLbl').innerText = T('won');
  if (document.getElementById('playBtn')) document.getElementById('playBtn').innerText = T('playNow');
  if (document.getElementById('stakeTitle')) document.getElementById('stakeTitle').innerText = T('selectStake');
  if (document.getElementById('gameStartsLabel')) document.getElementById('gameStartsLabel').innerText = T('gameStartsIn');
  if (document.getElementById('yourCardsLabel')) document.getElementById('yourCardsLabel').innerText = T('yourCards');
  if (document.getElementById('selPrizeLbl')) document.getElementById('selPrizeLbl').innerText = T('prizePool');
  if (document.getElementById('selPlayersLbl')) document.getElementById('selPlayersLbl').innerText = T('players');
  if (document.getElementById('selStakeLbl')) document.getElementById('selStakeLbl').innerText = T('stake');
  if (document.getElementById('gamePrizeLbl')) document.getElementById('gamePrizeLbl').innerText = T('prizePool');
  if (document.getElementById('gamePlayersLbl')) document.getElementById('gamePlayersLbl').innerText = T('players');
  if (document.getElementById('gameCalledLbl')) document.getElementById('gameCalledLbl').innerText = T('called');
  if (document.getElementById('recentLabel')) document.getElementById('recentLabel').innerText = T('recent');
  if (document.getElementById('winnerTitle')) document.getElementById('winnerTitle').innerText = T('bingo');
  if (document.getElementById('nextGameLabel')) document.getElementById('nextGameLabel').innerText = T('nextGame');
  if (document.getElementById('secondsLabel')) document.getElementById('secondsLabel').innerText = T('seconds');
  if (document.getElementById('stakeBackText')) document.getElementById('stakeBackText').innerText = T('back');
  if (document.getElementById('selectHomeBtn')) document.getElementById('selectHomeBtn').innerText = T('back');
  if (document.getElementById('gameHomeBtn')) document.getElementById('gameHomeBtn').innerText = T('back');
  if (document.getElementById('winnerHomeBtn')) document.getElementById('winnerHomeBtn').innerText = T('back');
  if (document.getElementById('depBackText')) document.getElementById('depBackText').innerText = T('back');
  if (document.getElementById('confBackText')) document.getElementById('confBackText').innerText = T('back');
  if (document.getElementById('wdBackText')) document.getElementById('wdBackText').innerText = T('back');
  if (document.getElementById('inqBackText')) document.getElementById('inqBackText').innerText = T('back');
  if (document.getElementById('submitDepositBtn')) document.getElementById('submitDepositBtn').innerText = T('deposit');
  if (document.getElementById('requestWithdrawBtn')) document.getElementById('requestWithdrawBtn').innerText = T('withdraw');
  if (document.getElementById('sendInquiryBtn')) document.getElementById('sendInquiryBtn').innerText = T('sendInquiry');
  if (document.getElementById('subjectLabel')) document.getElementById('subjectLabel').innerText = T('subject');
  if (document.getElementById('messageLabel')) document.getElementById('messageLabel').innerText = T('message');
  if (document.getElementById('amountLabel')) document.getElementById('amountLabel').innerText = T('amount');
  if (document.getElementById('accountNumberLabel')) document.getElementById('accountNumberLabel').innerText = T('accountNumber');
  if (document.getElementById('wdPlatformTitle')) document.getElementById('wdPlatformTitle').innerText = T('platform');
  if (document.getElementById('referenceLabel')) document.getElementById('referenceLabel').innerText = T('transactionRef');
  if (document.getElementById('leaveGameBtn')) document.getElementById('leaveGameBtn').innerText = T('leave_game');
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
  if (state.lang === 'en') state.lang = 'am';
  else state.lang = 'en';
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
    if (pollInterval) clearInterval(pollInterval);
    if (countdownPollInterval) clearInterval(countdownPollInterval);
    pollInterval = null;
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
    phone: phone,
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
    alert('Registration failed. Please try again.');
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

// ============================================================
// FIX 1: Handle join_game response correctly
// ============================================================
async function handleJoinGame(stake) {
    try {
        const res = await apiCall('/api/join_game', 'POST', { stake });
       
        if (res.error) {
            alert(T(res.error) || res.error);
            return;
        }

        if (res.game_in_progress) {
            // Spectator mode - game already running
            state.gameId = res.game_id;
            state.myCards = []; // No cards for spectators
            goPage('pg-game');
            startGamePolling();
            return;
        }

        // ✅ FIX: Save game state
        state.gameId = res.game_id;
        state.myCards = res.card ? [res.card] : []; // ✅ Save the bingo card
        state.currentStake = stake;

        // ✅ FIX: Set initial countdown display with CORRECT progress bar
        if (typeof res.countdown === 'number') {
            const remaining = res.countdown;
            document.getElementById('cd1').innerText = remaining;
            const progress = ((30 - remaining) / 30) * 100;
            document.getElementById('prog1').style.width = progress + '%';
        }

        // Update player count
        if (document.getElementById('players1')) {
            document.getElementById('players1').innerText = res.players || 0;
        }

        // Go to waiting room
        goPage('pg-wait1');

        // ✅ FIX: Start countdown polling AFTER setting initial values
        startCountdownPolling();

    } catch (err) {
        console.error('Join game error:', err);
        alert('Failed to join game');
    }
}


// ============================================================
// FIX 2: Corrected countdown polling with proper syncing
// ============================================================

function startCountdownPolling() {
    if (countdownPollInterval) clearInterval(countdownPollInterval);
   
    const cdEl = document.getElementById('cd1');
    const progEl = document.getElementById('prog1');
    const playersEl = document.getElementById('players1');

    countdownPollInterval = setInterval(async () => {
        if (!state.gameId) {
            clearInterval(countdownPollInterval);
            return;
        }

        const gameState = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
       
        if (!gameState || gameState.error) {
            clearInterval(countdownPollInterval);
            state.gameId = null;
            state.myCards = [];
            goPage('pg-home');
            loadUser();
            return;
        }

        // Game started!
        if (gameState.status === 'running') {
            clearInterval(countdownPollInterval);
            goPage('pg-game');
            startGamePolling();
            return;
        }

        // Game cancelled
        if (gameState.status === 'cancelled') {
            clearInterval(countdownPollInterval);
            alert(gameState.cancelled_message || T('gameCancelled'));
            state.gameId = null;
            state.myCards = [];
            goPage('pg-home');
            loadUser();
            return;
        }

        // Game finished (no winner)
        if (gameState.status === 'finished') {
            clearInterval(countdownPollInterval);
            alert(gameState.message || 'Game finished');
            state.gameId = null;
            state.myCards = [];
            goPage('pg-home');
            loadUser();
            return;
        }

        // Still waiting - update countdown
        if (gameState.status === 'waiting' && typeof gameState.countdown === 'number') {
            const remaining = gameState.countdown;
           
            // ✅ Update countdown text
            if (cdEl) cdEl.innerText = remaining;
           
            // ✅ Update progress bar correctly
            if (progEl) {
                const progress = ((30 - remaining) / 30) * 100;
                progEl.style.width = progress + '%';
            }
           
            // ✅ Update player count
            if (playersEl) playersEl.innerText = gameState.players || 0;
        }

    }, 2000); // Poll every 2 seconds (gives server time to add bots)
}


// ============================================================
// FIX 3: Game loop - display the card in waiting room
// ============================================================
function displayWaitingRoom() {
    const container = document.getElementById('card-container');
    if (!container || !state.myCards || state.myCards.length === 0) {
        return;
    }

    const card = state.myCards[0];
    container.innerHTML = ''; // Clear

    // Create 5x5 grid
    const table = document.createElement('table');
    table.className = 'bingo-card';
   
    const headerRow = document.createElement('tr');
    ['B', 'I', 'N', 'G', 'O'].forEach(col => {
        const th = document.createElement('th');
        th.innerText = col;
        headerRow.appendChild(th);
    });
    table.appendChild(headerRow);

    // Card rows
    for (let row = 0; row < 5; row++) {
        const tr = document.createElement('tr');
        for (let col = 0; col < 5; col++) {
            const cell = card[row][col];
            const td = document.createElement('td');
            td.className = 'bingo-cell';
            td.innerText = cell === 'FREE' ? 'FREE' : cell;
            if (cell === 'FREE') td.classList.add('free');
            tr.appendChild(td);
        }
        table.appendChild(tr);
    }

    container.appendChild(table);
}

// Call this when displaying pg-wait1
// Add to your goPage() or page display logic

async function pickCard(cardNumber) {
  if (state.myCards.length >= 4) { alert(T('maxCards')); return; }
  const btn = document.getElementById(`card-btn-${cardNumber}`);
  if (!btn || btn.classList.contains('taken') || btn.classList.contains('mine')) return;

  const gameStateRes = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
  if (gameStateRes && gameStateRes.status !== 'waiting') {
    alert('Game already started! Please wait for the next game.');
    if (gameStateRes.status === 'running') {
      goPage('pg-game');
      startGamePolling();
    }
    return;
  }

  const res = await apiCall('/api/pick_card', 'POST', {
    user_id: state.user.user_id,
    game_id: state.gameId,
    card_number: cardNumber,
    stake: state.stake
  });
  if (!res || res.error) {
    if (res?.error === 'Game has already started or finished') {
      alert('Game already started! Reloading...');
      location.reload();
    } else {
      alert(res?.error || 'Failed to pick card');
    }
    return;
  }
  state.myCards.push(cardNumber);
  state.balance = res.balance;
  renderUI();
  await refreshGameInfo();
  await loadMyCards();
  buildCardGrid(state.takenCards || []);
}

async function leaveGame() {
  if (!state.gameId || !state.user) return;
  if (confirm(T('leave_game') + '? You will be refunded the full stake.')) {
    const res = await apiCall('/api/withdraw_from_game', 'POST', {
      user_id: state.user.user_id,
      game_id: state.gameId
    });
    if (res && res.success) {
      alert(res.message);
      if (res.balance !== undefined) {
        state.balance = res.balance;
        renderUI();
      }
      state.gameId = null;
      state.myCards = [];
      state.myCardData = [];
      goPage('pg-home');
      loadUser();
    } else {
      alert('Failed to leave: ' + (res?.error || 'Unknown error'));
    }
  }
}

async function refreshGameInfo() {
  if (!state.gameId) return;
  const res = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
  if (res && !res.error) {
    state.takenCards = res.taken_cards || [];
    document.getElementById('sel-prize').innerText = Math.floor((res.prize_pool || 0) * 0.8) + ' ETB';
    const playersEl = document.getElementById('sel-players');
    if (playersEl) {
      playersEl.innerText = res.players === 0 ? 'Waiting for players…' : res.players;
    }
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

// ---------- Countdown polling ----------
function startCountdownPolling() {
  if (countdownPollInterval) clearInterval(countdownPollInterval);
  const cdEl = document.getElementById('cd1');
  const progEl = document.getElementById('prog1');
  countdownPollInterval = setInterval(async () => {
    if (!state.gameId) {
      clearInterval(countdownPollInterval);
      return;
    }
    const gameState = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
    if (!gameState || gameState.error) {
      clearInterval(countdownPollInterval);
      state.gameId = null;
      state.myCards = [];
      goPage('pg-home');
      loadUser();
      return;
    }
    if (gameState.status === 'running') {
      clearInterval(countdownPollInterval);
      goPage('pg-game');
      startGamePolling();
      return;
    }
    if (gameState.status === 'cancelled' || gameState.status === 'finished') {
      clearInterval(countdownPollInterval);
      alert(gameState.cancelled_message || T('gameCancelled'));
      state.gameId = null;
      state.myCards = [];
      goPage('pg-home');
      loadUser();
      return;
    }
    if (gameState.status === 'waiting' && typeof gameState.countdown === 'number') {
      const remaining = gameState.countdown;
      if (cdEl) cdEl.innerText = remaining;
      if (progEl) progEl.style.width = ((30 - remaining) / 30 * 100) + '%';
      if (remaining <= 0) {
        clearInterval(countdownPollInterval);
        setTimeout(() => startCountdownPolling(), 1000);
      }
    }
  }, 1000);
}

// ---------- Game polling ----------
function startGamePolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    if (!state.gameId) return;
    const res = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
    if (!res || res.error) return;

    if (res.status === 'waiting') {
      const displayPrize = res.total_winners_prize || Math.floor((res.prize_pool || 0) * 0.8);
      document.getElementById('sel-prize').innerText = displayPrize + ' ETB';
      document.getElementById('sel-players').innerText = res.players;
      if (JSON.stringify(state.takenCards) !== JSON.stringify(res.taken_cards)) {
        state.takenCards = res.taken_cards;
        buildCardGrid(state.takenCards);
      }
      if (document.getElementById('pg-select')?.classList.contains('active')) {
        if (!countdownPollInterval) startCountdownPolling();
      }
    } else if (res.status === 'running') {
      updateGameUI(res);
      if (document.getElementById('pg-select')?.classList.contains('active')) goPage('pg-game');
    } else if (res.status === 'cancelled') {
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
  if (playersEl) playersEl.innerText = gameState.players;

  const chipsEl = document.getElementById('recentChips');
  if (chipsEl) chipsEl.innerHTML = drawn.slice(-6).reverse().map(b => `<div class="chip">${b}</div>`).join('');

  renderMyCards(drawn);
}

async function renderMyCards(drawnBalls) {
  const wrap = document.getElementById('bingoCardsWrap');
  if (!wrap) return;
  await loadMyCards();
  if (!state.myCardData.length) {
    wrap.innerHTML = '<div style="text-align:center;color:var(--sub);padding:20px">No cards selected</div>';
    return;
  }
  const drawnNumbers = drawnBalls.map(b => parseInt(b.slice(1))).filter(n => !isNaN(n));
  const drawnSet = new Set(drawnNumbers);
  const cardsHtml = state.myCardData.map(card => buildCardHTML(card.card_data, drawnSet, card.card_index)).join('');
  const cardCount = state.myCardData.length;
  let gridClass = 'cards-1';
  if (cardCount === 2) gridClass = 'cards-2';
  else if (cardCount === 3) gridClass = 'cards-3';
  else if (cardCount === 4) gridClass = 'cards-4';
  wrap.innerHTML = `<div class="bingo-grid ${gridClass}">${cardsHtml}</div>`;
}

function buildCardHTML(cardData, drawnNumbersSet, cardIndex) {
  let html = `<div class="bingo-card-box"><div class="bcard-header"><div class="bcard-title">🎴 Card #${cardIndex}</div></div><div class="bcol-headers">`;
  ['B','I','N','G','O'].forEach(l => html += `<div class="bcol-h">${l}</div>`);
  html += '</div>';
  for (let r = 0; r < 5; r++) {
    html += '<div class="brow">';
    for (let c = 0; c < 5; c++) {
      let cell = cardData[r][c];
      if (cell === 'FREE') html += '<div class="bcell free">FREE</div>';
      else if (drawnNumbersSet.has(cell)) html += '<div class="bcell hit">⭐</div>';
      else html += `<div class="bcell">${cell}</div>`;
    }
    html += '</div>';
  }
  html += '</div>';
  return html;
}

function showWinner(gameState) {
  const winnerDiv = document.getElementById('winnerCards');
  if (winnerDiv) {
    if (gameState.winner_details && gameState.winner_details.length) {
      const prizePerWinner = gameState.total_winners_prize / gameState.winner_details.length;
      winnerDiv.innerHTML = gameState.winner_details.map(w => `
        <div style="background:rgba(255,215,0,0.2); margin:6px; padding:8px; border-radius:8px;">
          🏆 ${w.username} - Card #${w.card_number} +${prizePerWinner.toFixed(2)} ETB
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
      if (gameState.next_game_id) {
        state.gameId = gameState.next_game_id;
        state.myCards = [];
        state.myCardData = [];
        state.takenCards = [];
        const gameInfo = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
        if (gameInfo && !gameInfo.error) {
          state.stake = gameInfo.stake;
          document.getElementById('sel-prize').innerText = Math.floor((gameInfo.prize_pool || 0) * 0.8) + ' ETB';
          document.getElementById('sel-players').innerText = gameInfo.players;
          document.getElementById('sel-stake').innerText = gameInfo.stake + ' ETB';
          buildCardGrid(gameInfo.taken_cards || []);
        }
        startCountdownPolling();
        goPage('pg-select');
      } else {
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
  const platformNum = platform === 'telebirr' ? (window.telebirrNumber || '0929 001 000') : (window.cbeNumber || '1000061737212');
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
    amount: amount,
    platform: selectedPlatform,
    proof: proof
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
    amount: amount,
    method: platform,
    account_no: account
  });
  if (res && res.success) {
    state.balance -= amount;
    renderUI();
    alert(T('withdrawSuccess'));
    goPage('pg-home');
  } else alert('❌ ' + (res?.error || 'Request failed'));
}

async function submitInquiry() {
  const subject = document.getElementById('inqSubject').value.trim();
  const message = document.getElementById('inqMessage').value.trim();
  if (!subject || !message) { alert('Please fill subject and message'); return; }
  const res = await apiCall('/api/inquiry', 'POST', {
    user_id: state.user.user_id,
    subject: subject,
    message: message
  });
  if (res && res.success) {
    alert(T('inquirySuccess'));
    document.getElementById('inqSubject').value = '';
    document.getElementById('inqMessage').value = '';
    goPage('pg-help');
  } else alert('❌ Failed to send');
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
    const tele = await apiCall('/api/settings/telebirr_number');
    const cbe = await apiCall('/api/settings/cbe_number');
    if (tele && tele.telebirr_number) window.telebirrNumber = tele.telebirr_number;
    if (cbe && cbe.cbe_number) window.cbeNumber = cbe.cbe_number;
    const telePlace = document.getElementById('telebirrNumberPlaceholder');
    const cbePlace = document.getElementById('cbeNumberPlaceholder');
    if (telePlace) telePlace.innerText = window.telebirrNumber || '0929 001 000';
    if (cbePlace) cbePlace.innerText = window.cbeNumber || '1000061737212';
  } catch(e) {}
}

// ---------- Referral Link Functions ----------
async function displayReferralInfo() {
  if (!state.user || !state.user.user_id) return;
  const data = await apiCall(`/api/referral_stats/${state.user.user_id}`);
  if (data && data.referral_code) {
    const baseUrl = window.location.origin;
    const fullLink = `${baseUrl}?ref=${data.referral_code}`;
    const linkElem = document.getElementById('referralLinkAnchor');
    if (linkElem) {
      linkElem.href = fullLink;
      linkElem.innerText = fullLink;
    }
    const card = document.getElementById('referralCard');
    if (card) card.style.display = 'block';
    const bonusAmount = 10;
    const commissionPercent = 5;
    const bonusText = T('referral_bonus_text', { bonus: bonusAmount });
    const commissionText = T('referral_commission_text', { percent: commissionPercent });
    const msgElem = document.getElementById('referralMessage');
    if (msgElem) msgElem.innerHTML = `${bonusText}<br>${commissionText}`;
  }
}

function copyReferralLink() {
  const link = document.getElementById('referralLinkAnchor')?.href;
  if (!link) return;
  navigator.clipboard.writeText(link).then(() => {
    alert(T('copy_success'));
  }).catch(() => {
    alert(T('copy_fail'));
  });
}

// ---------- Leaderboard (top 5) ----------
async function loadLeaderboard() {
  const res = await apiCall('/api/leaderboard');
  if (res && Array.isArray(res)) {
    const container = document.getElementById('leaderboardList');
    if (container) {
      const top5 = res.slice(0, 5);
      if (top5.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:var(--sub);padding:10px">No players yet</div>';
      } else {
        container.innerHTML = top5.map((p, idx) => `
          <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05)">
            <span>${idx+1}. ${p.full_name || p.username}</span>
            <span style="color:var(--gold)">${(p.total_won || p.balance || 0).toFixed(0)} ETB</span>
          </div>
        `).join('');
      }
    }
  }
}

// ---------- Recent Games (last 5) ----------
async function loadRecentGames() {
  if (!state.user) return;
  const res = await apiCall(`/api/recent_games/${state.user.user_id}`);
  const container = document.getElementById('recentGamesList');
  if (!container) return;
  if (!res || !res.length) {
    container.innerHTML = '<div style="text-align:center;color:var(--sub);padding:10px">No games yet</div>';
    return;
  }
  const last5 = res.slice(0, 5);
  container.innerHTML = last5.map(g => `
    <div style="border-bottom:1px solid rgba(255,255,255,0.1);padding:8px">
      Game #${g.id} | Stake: ${g.stake} ETB | Prize: ${g.prize_pool} ETB | ${g.won ? '🏆 Won' : g.status}
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
  goPage('pg-home');
});

