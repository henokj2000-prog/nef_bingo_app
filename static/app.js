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
  myCardData: []
};

let pollInterval = null;
let countdownInterval = null;

// ── API helper ───────────────────────────────────────
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

    // Check registration
    if (!state.user.phone) {
      goPage('pg-register');
      return;
    }

    // Set language from saved preference
    if (state.user.language && state.user.language !== state.lang) {
      state.lang = state.user.language;
      updateUILanguage();
    }

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

// ── Language handling (simplified) ────────────────────
function updateUILanguage() {
  // Apply translations using the LANG object (to be filled with your translations)
  // For now, just update the phone/language prompts.
  const regTitle = document.querySelector('#pg-register .balance-label');
  if (regTitle) regTitle.innerText = (state.lang === 'am') ? 'እንኳን ደህና መጡ!' : 'Welcome!';
  // Add more translations as needed.
}

function toggleLang() {
  state.lang = state.lang === 'en' ? 'am' : 'en';
  updateUILanguage();
  // Optionally save to backend if needed
}

// ── Registration functions ────────────────────────────
let selectedRegLang = 'en';
function selectRegLang(lang) {
  selectedRegLang = lang;
  document.querySelectorAll('#pg-register .amount-btn').forEach(btn => btn.classList.remove('selected'));
  document.querySelector(`#pg-register .amount-btn[data-lang="${lang}"]`).classList.add('selected');
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

// ── Settings functions ────────────────────────────────
let selectedSettingsLang = 'en';
function selectSettingsLang(lang) {
  selectedSettingsLang = lang;
  document.querySelectorAll('#pg-settings .amount-btn').forEach(btn => btn.classList.remove('selected'));
  document.querySelector(`#pg-settings .amount-btn[data-lang="${lang}"]`).classList.add('selected');
}
async function saveSettings() {
  const phone = document.getElementById('settingsPhone').value.trim();
  if (phone && phone.length < 9) {
    alert('Please enter a valid phone number (10 digits)');
    return;
  }
  const res = await apiCall('/api/update_profile', 'POST', {
    user_id: state.user.user_id,
    phone: phone,
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

// ── Game functions (keep your existing ones: buildStakeGrid, joinGame, pickCard, etc.) ──
// For brevity, I assume you already have all game logic (polling, card grid, winner, etc.)
// If not, I will provide the full game logic in a separate message.

// ── Placeholders for game functions (to avoid errors) ──
function buildStakeGrid() { /* your existing */ }
function joinGame(stake) { /* your existing */ }
function buildCardGrid(takenCards) { /* your existing */ }
function pickCard(cardNumber) { /* your existing */ }
function refreshGameInfo() { /* your existing */ }
async function loadMyCards() { /* your existing */ }
function startCountdown(seconds) { /* your existing */ }
function startGamePolling() { /* your existing */ }
function updateGameUI(gameState) { /* your existing */ }
async function renderMyCards(drawnBalls) { /* your existing */ }
function showWinner(gameState) { /* your existing */ }
function buildDepositAmountGrid() { /* your existing */ }
function selectPlatform(platform) { /* your existing */ }
async function submitDeposit() { /* your existing */ }
function setWdPlatform(platform, el) { /* your existing */ }
async function submitWithdraw() { /* your existing */ }
async function submitInquiry() { /* your existing */ }
async function loadLatestNotification() { /* your existing */ }
function showAdminPanel() { /* your existing */ }

// ── Initialization ───────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  buildStakeGrid();
  buildDepositAmountGrid();
  await loadUser();
  renderUI();
  // Pre-fill settings screen if user already registered
  if (state.user && state.user.phone) {
    const settingsPhone = document.getElementById('settingsPhone');
    if (settingsPhone) settingsPhone.value = state.user.phone;
    if (state.user.language) {
      selectedSettingsLang = state.user.language;
      document.querySelectorAll('#pg-settings .amount-btn').forEach(btn => {
        if (btn.dataset.lang === state.user.language) btn.classList.add('selected');
      });
    }
  }
  goPage('pg-home');
});
