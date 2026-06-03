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
  takenCards: []
};

let pollInterval = null;
let countdownInterval = null;

// Translations (simplified, can be expanded)
const LANG = {
  en: {
    balance: 'Your Balance',
    deposit: 'Deposit',
    withdraw: 'Withdraw',
    playNow: '🎮 PLAY NOW',
    insufficient: 'Insufficient balance!',
    cardTaken: 'Card already taken',
    maxCards: 'Maximum 4 cards per game',
    gameCancelled: 'Game cancelled due to insufficient players. Your balance has been refunded. Please try again.',
    registerWelcome: 'Welcome! Please complete your registration to play',
    phoneLabel: 'Phone Number',
    languageLabel: 'Language',
    startPlaying: 'Start Playing',
    saveSettings: 'Save Changes'
  },
  am: {
    balance: 'ሂሳብዎ',
    deposit: 'ተቀምጦ',
    withdraw: 'አውጣ',
    playNow: '🎮 አሁን ጫወት',
    insufficient: 'በቂ ሂሳብ የለም!',
    cardTaken: 'ካርዱ ተወስዷል',
    maxCards: 'በአንድ ጨዋታ ከ4 ካርድ በላይ አይቻልም',
    gameCancelled: 'በቂ ተጫዋቾች የሉም። ጨዋታው ተሰርዟል። ገንዘብዎ ተመልሷል። እባክዎ እንደገና ይሞክሩ።',
    registerWelcome: 'እንኳን ደህና መጡ! ለመጫወት እባክዎ ይመዝገቡ',
    phoneLabel: 'ስልክ ቁጥር',
    languageLabel: 'ቋንቋ',
    startPlaying: 'መጫወት ጀምር',
    saveSettings: 'ለውጦችን አስቀምጥ'
  }
  // Add om, ti similarly
};
function T(key, vars={}) {
  let text = (LANG[state.lang] && LANG[state.lang][key]) || (LANG.en && LANG.en[key]) || key;
  for (let [k,v] of Object.entries(vars)) text = text.replace(`{${k}}`, v);
  return text;
}

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

    // Check registration
    if (!state.user.phone) {
      goPage('pg-register');
      return;
    }
    if (state.user.language && LANG[state.user.language]) {
      state.lang = state.user.language;
    }
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

function updateUILanguage() {
  // Update registration texts
  const regWelcome = document.querySelector('#pg-register .balance-label');
  if (regWelcome) regWelcome.innerText = T('registerWelcome');
  const phoneLabel = document.querySelector('#pg-register .card-title:first-child');
  if (phoneLabel) phoneLabel.innerText = T('phoneLabel');
  const langLabel = document.querySelector('#pg-register .card-title:last-child');
  if (langLabel) langLabel.innerText = T('languageLabel');
  const startBtn = document.querySelector('#pg-register .submit-btn');
  if (startBtn) startBtn.innerText = T('startPlaying');
  // Settings texts
  const settingsPhoneLabel = document.querySelector('#pg-settings .card-title:first-child');
  if (settingsPhoneLabel) settingsPhoneLabel.innerText = T('phoneLabel');
  const settingsLangLabel = document.querySelector('#pg-settings .card-title:last-child');
  if (settingsLangLabel) settingsLangLabel.innerText = T('languageLabel');
  const saveBtn = document.querySelector('#pg-settings .submit-btn');
  if (saveBtn) saveBtn.innerText = T('saveSettings');
  // Home screen texts
  const balanceLabel = document.querySelector('#pg-home .balance-label');
  if (balanceLabel) balanceLabel.innerText = T('balance');
  const depositBtn = document.querySelector('#pg-home .btn-deposit');
  if (depositBtn) depositBtn.innerHTML = `💰 ${T('deposit')}<br><span style="font-size:10px">ገቢ ማድረግ</span>`;
  const withdrawBtn = document.querySelector('#pg-home .btn-withdraw');
  if (withdrawBtn) withdrawBtn.innerHTML = `💸 ${T('withdraw')}<br><span style="font-size:10px">ወጪ ማድረግ</span>`;
  const playBtn = document.querySelector('#pg-home .play-btn');
  if (playBtn) playBtn.innerText = T('playNow');
}

function toggleLang() {
  state.lang = state.lang === 'en' ? 'am' : 'en';
  updateUILanguage();
  apiCall('/api/update_profile', 'POST', { user_id: state.user.user_id, language: state.lang });
}

// Navigation
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

// Registration functions
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
async function completeRegistration() {
  const phone = document.getElementById('regPhone').value.trim();
  if (!phone || phone.length < 9) {
    alert('Please enter a valid phone number (e.g., 0912345678)');
    return;
  }
  const res = await apiCall('/api/update_profile', 'POST', {
    user_id: state.user.user_id,
    phone: phone,
    language: selectedRegLang
  });
  if (res && res.success) {
    state.user.phone = phone;
    state.user.language = selectedRegLang;
    state.lang = selectedRegLang;
    updateUILanguage();
    goPage('pg-home');
  } else {
    alert('Registration failed. Please try again.');
  }
}

// Settings functions
let selectedSettingsLang = 'en';
function selectSettingsLang(lang) {
  selectedSettingsLang = lang;
  document.querySelectorAll('.settings-lang-btn').forEach(btn => {
    btn.style.borderColor = 'rgba(255,215,0,0.3)';
    btn.style.background = 'var(--card)';
  });
  const selected = document.querySelector(`.settings-lang-btn[data-lang="${lang}"]`);
  if (selected) {
    selected.style.borderColor = 'var(--gold)';
    selected.style.background = 'rgba(255,215,0,0.2)';
  }
}
async function saveSettings() {
  const phone = document.getElementById('settingsPhone').value.trim();
  if (phone && phone.length < 9) {
    alert('Please enter a valid phone number (10 digits)');
    return;
  }
  const res = await apiCall('/api/update_profile', 'POST', {
    user_id: state.user.user_id,
    phone: phone || undefined,
    language: selectedSettingsLang
  });
  if (res && res.success) {
    if (phone) state.user.phone = phone;
    if (selectedSettingsLang) {
      state.user.language = selectedSettingsLang;
      state.lang = selectedSettingsLang;
      updateUILanguage();
    }
    alert('Settings saved!');
    goPage('pg-home');
  } else {
    alert('Failed to save settings');
  }
}

// Game functions (keep your existing game logic here)
// ... (buildStakeGrid, joinGame, pickCard, refreshGameInfo, loadMyCards, startCountdown, startGamePolling, updateGameUI, renderMyCards, buildCardHTML, showWinner, deposit, withdraw, inquiry, etc.)
// I assume you already have these functions in your current app.js. If not, copy them from previous working version.

// Minimal placeholders to avoid errors (replace with your actual game functions)
function buildStakeGrid() {}
function joinGame(stake) {}
function buildCardGrid(takenCards) {}
async function pickCard(cardNumber) {}
async function refreshGameInfo() {}
async function loadMyCards() {}
function startCountdown(seconds) {}
function startGamePolling() {}
function updateGameUI(gameState) {}
async function renderMyCards(drawnBalls) {}
function buildCardHTML(cardData, drawnSet, cardIndex) { return ''; }
function showWinner(gameState) {}
function buildDepositAmountGrid() {}
function selectPlatform(platform) {}
async function submitDeposit() {}
function setWdPlatform(platform, el) {}
async function submitWithdraw() {}
async function submitInquiry() {}
async function loadLatestNotification() {}
function showAdminPanel() {}

// Initialization
window.addEventListener('DOMContentLoaded', async () => {
  buildStakeGrid();
  buildDepositAmountGrid();
  await loadUser();
  renderUI();
  // Prefill settings if user already registered
  if (state.user && state.user.phone) {
    const settingsPhone = document.getElementById('settingsPhone');
    if (settingsPhone) settingsPhone.value = state.user.phone;
    if (state.user.language) {
      selectedSettingsLang = state.user.language;
      document.querySelectorAll('.settings-lang-btn').forEach(btn => {
        if (btn.dataset.lang === state.user.language) {
          btn.style.borderColor = 'var(--gold)';
          btn.style.background = 'rgba(255,215,0,0.2)';
        }
      });
    }
  }
  goPage('pg-home');
});
