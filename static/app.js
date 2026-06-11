// -----------------------------------------------
// NEF BINGO frontend - v2.0
// -----------------------------------------------

// ---------- GLOBALS ----------
let tg = window.Telegram?.WebApp;
let user = null;
let currentGame = null;          // { game_id, stake, prize_pool, status, myCards, takenCards }
let countdownInterval = null;
let gameStateInterval = null;
let speechEnabled = true;
let currentLang = 'en';
let translations = {};

// ---------- TRANSLATIONS (English + Amharic) ----------
const locale = {
  en: {
    balance: "Your Balance",
    deposit: "Deposit",
    withdraw: "Withdraw",
    your_referral_link: "🔗 Your Referral Link",
    copy_link: "📋 Copy Link",
    referral_info: "Share this link with friends. When they join and play, you'll earn commission!",
    games: "Games",
    wins: "Wins",
    won_etb: "Won ETB",
    top_players: "🏆 Top 5 Players",
    recent_games: "Recent Games (last 3)",
    play_now: "🎮 PLAY NOW",
    back: "Back",
    select_stake: "Select Stake",
    prize_pool: "Prize Pool",
    players: "Players",
    stake: "Stake",
    game_starts_in: "Game starts in",
    sec: "sec",
    your_cards: "Your cards",
    leave_game: "Leave Game",
    home: "Home",
    called: "Called",
    recent: "Recent",
    how_to_play: "How to Play",
    help: "Help",
    send_inquiry: "Send Inquiry",
    message_admin: "Message the admin directly",
    faq: "FAQ",
    deposit_amount: "Select Amount",
    custom_amount: "Or custom amount",
    select_platform: "Select Platform",
    payment_instructions: "Payment Instructions",
    send_exactly: "Send exactly",
    number: "Number",
    reference: "Reference",
    upload_proof: "Upload Proof",
    transaction_ref: "Transaction reference number...",
    submit: "Submit",
    available_balance: "Available Balance",
    amount: "Amount",
    account_number: "Account Number",
    request_withdrawal: "Request Withdrawal",
    subject: "Subject",
    message: "Message",
    send: "Send",
    confirm: "Confirm",
    home_nav: "Home",
    play_nav: "Play",
    deposit_nav: "Deposit",
    howto_nav: "How To",
    help_nav: "Help",
    registration_welcome: "እንኳን በደህና መጡ! / Welcome!",
    registration_sub: "Please complete your registration to play",
    phone_number: "Enter your Phone Number",
    referral_code_optional: "Referral Code (optional)",
    select_language: "Please select language",
    start_playing: "Start Playing",
    game_started: "Game started!",
    waiting_for_game: "Waiting for game to start...",
    bingo_winner: "BINGO!",
    next_game_in: "Next game in",
    seconds: "seconds",
    balance_updated: "Balance updated",
    card_taken: "Card already taken",
    max_cards: "Maximum 4 cards per player",
    insufficient_balance: "Insufficient balance",
    deposit_success: "Deposit recorded. Awaiting admin approval.",
    withdrawal_requested: "Withdrawal request submitted.",
    inquiry_sent: "Inquiry sent. Admin will respond soon.",
    copy_success: "Referral link copied!",
  },
  am: {
    balance: "የእርስዎ ቀሪ ሒሳብ",
    deposit: "ገንዘብ አስገቡ",
    withdraw: "ገንዘብ አውጡ",
    your_referral_link: "🔗 የእርስዎ ሪፈራል ሊንክ",
    copy_link: "📋 ቅዳ",
    referral_info: "ይህን ሊንክ ለጓደኞችዎ ያጋሩ። ሲመዘገቡ እና ሲጫወቱ ኮሚሽን ያገኛሉ!",
    games: "ጨዋታዎች",
    wins: "ድሎች",
    won_etb: "ያሸነፉት ETB",
    top_players: "🏆 ከፍተኛ 5 ተጫዋቾች",
    recent_games: "የቅርብ ጊዜ ጨዋታዎች (የመጨረሻ 3)",
    play_now: "🎮 አሁን ተጫወት",
    back: "ተመለስ",
    select_stake: "ውርርድ ምረጥ",
    prize_pool: "ሽልማት ገንዘብ",
    players: "ተጫዋቾች",
    stake: "ውርርድ",
    game_starts_in: "ጨዋታ ይጀምራል በ",
    sec: "ሰከንድ",
    your_cards: "ካርዶችዎ",
    leave_game: "ጨዋታውን ልቀቁ",
    home: "መነሻ",
    called: "የተጠሩ",
    recent: "የቅርብ",
    how_to_play: "እንዴት መጫወት እንደሚቻል",
    help: "እገዛ",
    send_inquiry: "ጥያቄ ላኩ",
    message_admin: "አስተዳዳሪን በቀጥታ ያነጋግሩ",
    faq: "ተደጋጋሚ ጥያቄዎች",
    deposit_amount: "መጠን ምረጡ",
    custom_amount: "ወይም የራስዎ መጠን",
    select_platform:ገጽ ምረጡ",
    payment_instructions: "የክፍያ መመሪያ",
    send_exactly: "በትክክል ይላኩ",
    number: "ቁጥር",
    reference: "ማጣቀሻ",
    upload_proof: "ማረጋገጫ አስገቡ",
    transaction_ref: "የግብይት ማጣቀሻ ቁጥር...",
    submit: "አስገባ",
    available_balance: "የሚገኝ ቀሪ ሒሳብ",
    amount: "መጠን",
    account_number: "አካውንት ቁጥር",
    request_withdrawal: "ገንዘብ አውጣ",
    subject: "ርዕስ",
    message: "መልእክት",
    send: "ላክ",
    confirm: "አረጋግጥ",
    home_nav: "መነሻ",
    play_nav: "ጨዋታ",
    deposit_nav: "አስገባ",
    howto_nav: "እንዴት",
    help_nav: "እገዛ",
    registration_welcome: "እንኳን በደህና መጡ!",
    registration_sub: "እባክዎ ምዝገባዎን ያጠናቅቁ",
    phone_number: "ስልክ ቁጥርዎን ያስገቡ",
    referral_code_optional: "ሪፈራል ኮድ (አማራጭ)",
    select_language: "ቋንቋ ይምረጡ",
    start_playing: "መጫወት ጀምር",
    game_started: "ጨዋታ ተጀምሯል!",
    waiting_for_game: "ጨዋታ ሲጀመር ይጠብቁ...",
    bingo_winner: "ቢንጎ!",
    next_game_in: "ቀጣይ ጨዋታ በ",
    seconds: "ሰከንዶች",
    balance_updated: "ቀሪ ሒሳብ ተሻሽሏል",
    card_taken: "ካርዱ አስቀድሞ ተወስዷል",
    max_cards: "በአንድ ተጫዋች ከፍተኛው 4 ካርዶች ናቸው",
    insufficient_balance: "በቂ ገንዘብ የለዎትም",
    deposit_success: "ገንዘብ መግቢያ ተመዝግቧል። አስተዳዳሪ ያረጋግጣል።",
    withdrawal_requested: "የገንዘብ ማውጫ ጥያቄ ቀርቧል።",
    inquiry_sent: "ጥያቄዎ ተልኳል። አስተዳዳሪ በቅርቡ ይመልሳል።",
    copy_success: "ሪፈራል ሊንክ ተቀድቷል!",
  }
};

// ---------- HELPER: load translations ----------
function loadTranslations(lang) {
  translations = locale[lang] || locale.en;
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (translations[key]) el.innerText = translations[key];
  });
  // Update dynamic texts
  document.getElementById('balanceLabel').innerText = translations.balance;
  document.getElementById('depositBtnText').innerText = translations.deposit;
  document.getElementById('withdrawBtnText').innerText = translations.withdraw;
  document.getElementById('stakeBackText').innerText = translations.back;
  document.getElementById('depBackText').innerText = translations.back;
  document.getElementById('wdBackText').innerText = translations.back;
  document.getElementById('confBackText').innerText = translations.back;
  document.getElementById('inqBackText').innerText = translations.back;
  document.getElementById('gameHomeBtn').innerText = translations.home;
  document.getElementById('winnerHomeBtn').innerText = translations.home;
  document.getElementById('selectHomeBtn').innerText = translations.home;
  document.getElementById('leaveGameBtn').innerText = translations.leave_game;
  document.getElementById('gameStartsLabel').innerHTML = translations.game_starts_in;
  document.getElementById('secLabel').innerText = translations.sec;
  document.getElementById('yourCardsLabel').innerHTML = translations.your_cards;
  document.getElementById('gamePrizeLbl').innerText = translations.prize_pool;
  document.getElementById('gamePlayersLbl').innerText = translations.players;
  document.getElementById('gameCalledLbl').innerText = translations.called;
  document.getElementById('recentLabel').innerHTML = translations.recent;
  document.getElementById('selPrizeLbl').innerText = translations.prize_pool;
  document.getElementById('selPlayersLbl').innerText = translations.players;
  document.getElementById('selStakeLbl').innerText = translations.stake;
  document.getElementById('stakeTitle').innerText = translations.select_stake;
  document.getElementById('depAmountTitle').innerText = translations.deposit_amount;
  document.getElementById('customAmountLabel').innerText = translations.custom_amount;
  document.getElementById('depPlatformTitle').innerText = translations.select_platform;
  document.getElementById('paymentInstrTitle').innerText = translations.payment_instructions;
  document.getElementById('sendExactlyLabel').innerText = translations.send_exactly;
  document.getElementById('numberLabel').innerText = translations.number;
  document.getElementById('referenceLabel').innerText = translations.reference;
  document.getElementById('uploadProofTitle').innerText = translations.upload_proof;
  document.getElementById('submitDepositBtn').innerText = translations.submit;
  document.getElementById('withdrawTitle').innerText = translations.withdraw;
  document.getElementById('availableBalanceLabel').innerText = translations.available_balance;
  document.getElementById('wdPlatformTitle').innerText = translations.select_platform;
  document.getElementById('amountLabel').innerText = translations.amount;
  document.getElementById('accountNumberLabel').innerText = translations.account_number;
  document.getElementById('requestWithdrawBtn').innerText = translations.request_withdrawal;
  document.getElementById('inquiryTitle').innerText = translations.send_inquiry;
  document.getElementById('subjectLabel').innerText = translations.subject;
  document.getElementById('messageLabel').innerText = translations.message;
  document.getElementById('sendInquiryBtn').innerText = translations.send;
  document.getElementById('howtoTitle').innerText = translations.how_to_play;
  document.getElementById('helpTitle').innerText = translations.help;
  document.getElementById('sendInquiryLabel').innerText = translations.send_inquiry;
  document.getElementById('messageAdminLabel').innerText = translations.message_admin;
  document.getElementById('faqTitle').innerText = translations.faq;
  document.getElementById('step1Text').innerHTML = "<b>Deposit via Telebirr or CBE.</b><br>Confirmed by admin within 30 min.";
  document.getElementById('step2Text').innerHTML = "<b>Choose 10, 20, 50 or 100 ETB.</b><br>Higher stake = bigger prize!";
  document.getElementById('step3Text').innerHTML = "<b>Select up to 4 cards from 1-500.</b><br>🟡=yours, 🔴=taken. Game starts after 30 sec.";
  document.getElementById('step4Text').innerHTML = "<b>Numbers called every 2 seconds.</b><br>Your card updates live with ⭐.";
  document.getElementById('step5Text').innerHTML = "<b>Complete a row, column or diagonal to win!</b><br>Prize split if multiple winners.";
  document.getElementById('step6Text').innerHTML = "<b>Request withdrawal to Telebirr or CBE.</b><br>Processed within 24 hours.";
  document.getElementById('faqContent').innerHTML = "<b>How long does deposit take?</b><br>Usually 5-30 minutes after proof submitted.<br><br><b>Withdrawal time?</b><br>Within 24 hours on business days.<br><br><b>What if game cancels?</b><br>Full refund automatically credited.";
  document.getElementById('winnerTitle').innerText = translations.bingo_winner;
  document.getElementById('winnerSub').innerText = translations.bingo_winner;
  document.getElementById('nextGameLabel').innerText = translations.next_game_in;
  document.getElementById('secondsLabel').innerText = translations.seconds;
  document.getElementById('balanceUpdatedMsg').innerText = translations.balance_updated;
  // Navbar
  document.getElementById('navHomeLabel').innerText = translations.home_nav;
  document.getElementById('navPlayLabel').innerText = translations.play_nav;
  document.getElementById('navDepositLabel').innerText = translations.deposit_nav;
  document.getElementById('navHowLabel').innerText = translations.howto_nav;
  document.getElementById('navHelpLabel').innerText = translations.help_nav;
  // Stats labels
  document.getElementById('statGamesLbl').innerText = translations.games;
  document.getElementById('statWinsLbl').innerText = translations.wins;
  document.getElementById('statWonLbl').innerText = translations.won_etb;
  document.getElementById('leaderboardTitle').innerText = translations.top_players;
  document.getElementById('recentTitle').innerText = translations.recent_games;
  // Registration
  document.querySelector('#pg-register .logo-text').innerText = "NEF BINGO";
  document.querySelector('#pg-register .logo-sub').innerText = "ነፍ ቢንጎ";
  document.querySelector('#pg-register div[style*="font-size:20px"]').innerText = translations.registration_welcome;
  document.querySelector('#pg-register div[style*="font-size:13px"]').innerText = translations.registration_sub;
  document.querySelector('#pg-register div[style*="text-align:left"]:first-child div[style*="font-size:14px"]').innerText = translations.phone_number;
  document.querySelector('#pg-register div[style*="text-align:left"]:nth-child(2) div[style*="font-size:14px"]').innerText = translations.referral_code_optional;
  document.querySelector('#pg-register div[style*="text-align:left"]:nth-child(3) div[style*="font-size:14px"]').innerText = translations.select_language;
  document.querySelector('#pg-register button').innerText = translations.start_playing;
}

// ---------- SPEECH ----------
function speak(text, lang = currentLang) {
  if (!speechEnabled) return;
  if (window.Telegram?.WebApp?.HapticFeedback) {
    // Telegram can't speak directly; use browser speech
  }
  if ('speechSynthesis' in window) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang === 'am' ? 'am-ET' : 'en-US';
    speechSynthesis.cancel();
    speechSynthesis.speak(utterance);
  }
}

function toggleSpeech() {
  speechEnabled = !speechEnabled;
  const btn = document.getElementById('speechToggleBtn');
  btn.style.opacity = speechEnabled ? '1' : '0.5';
  speak(speechEnabled ? "Voice enabled" : "Voice disabled");
}

// ---------- API HELPERS ----------
async function apiCall(url, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ---------- REGISTRATION ----------
async function completeRegistration() {
  const phone = document.getElementById('regPhone').value.trim();
  const referralCode = document.getElementById('regReferralCode').value.trim();
  let lang = 'en';
  const selected = document.querySelector('.reg-lang-btn[style*="border:2px solid rgb(255, 215, 0)"]');
  if (selected) lang = selected.getAttribute('data-lang');
  if (!phone || phone.length < 9) {
    alert("Please enter a valid phone number");
    return;
  }
  // Save to backend via update_profile
  await apiCall('/api/update_profile', 'POST', {
    user_id: user.id,
    phone: phone,
    language: lang,
    referral_code: referralCode
  });
  currentLang = lang;
  localStorage.setItem('nef_lang', lang);
  localStorage.setItem('nef_phone', phone);
  // Now fetch player data and show home
  await loadUserData();
  document.getElementById('pg-register').classList.remove('active');
  document.getElementById('pg-home').classList.add('active');
  startHomeRefresh();
}

function selectRegLang(lang) {
  document.querySelectorAll('.reg-lang-btn').forEach(btn => {
    btn.style.border = '2px solid rgba(255,215,0,0.3)';
  });
  const btn = document.querySelector(`.reg-lang-btn[data-lang="${lang}"]`);
  btn.style.border = '2px solid var(--gold)';
  currentLang = lang;
}

// ---------- USER DATA & HOME ----------
async function loadUserData() {
  if (!tg && !user) {
    // For web testing, create dummy user
    user = { id: Math.floor(Math.random() * 1000000), username: 'test_user', first_name: 'Test' };
  }
  const data = await apiCall(`/api/player/${user.id}?username=${encodeURIComponent(user.username || '')}&full_name=${encodeURIComponent(user.first_name || 'User')}`);
  window.player = data;
  document.getElementById('balanceDisplay').innerText = data.balance.toFixed(2) + ' ETB';
  document.getElementById('stat-games').innerText = data.games_played || 0;
  document.getElementById('stat-wins').innerText = data.wins || 0;
  document.getElementById('stat-won').innerText = (data.total_won || 0).toFixed(2);
  if (data.referral_code) {
    const link = `${window.location.origin}?ref=${data.referral_code}`;
    document.getElementById('referralLinkAnchor').href = link;
    document.getElementById('referralLinkAnchor').innerText = link;
    document.getElementById('referralCard').style.display = 'block';
    document.getElementById('referralMessage').innerText = translations.referral_info;
  } else {
    document.getElementById('referralCard').style.display = 'none';
  }
  // Refresh leaderboard & recent games
  refreshLeaderboard();
  refreshRecentGames();
}

async function refreshLeaderboard() {
  const data = await apiCall('/api/leaderboard');
  const container = document.getElementById('leaderboardList');
  if (data.length === 0) {
    container.innerHTML = '<div style="text-align:center;color:var(--sub);padding:10px">No data yet</div>';
    return;
  }
  let html = '';
  data.slice(0,5).forEach((p, idx) => {
    html += `<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05);">
      <div>${idx+1}. ${p.username || 'User'}</div>
      <div style="color:var(--gold)">${p.balance.toFixed(0)} ETB</div>
    </div>`;
  });
  container.innerHTML = html;
}

async function refreshRecentGames() {
  if (!user) return;
  const data = await apiCall(`/api/recent_games/${user.id}`);
  const container = document.getElementById('recentGamesList');
  if (!data.length) {
    container.innerHTML = '<div style="text-align:center;color:var(--sub);padding:10px">No games yet</div>';
    return;
  }
  let html = '';
  data.slice(0,3).forEach(g => {
    const status = g.won ? '🏆 Win' : (g.status === 'finished' ? 'Finished' : g.status);
    html += `<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05);">
      <div>${g.stake} ETB</div>
      <div>${status}</div>
      <div>${new Date(g.finished_at * 1000).toLocaleDateString()}</div>
    </div>`;
  });
  container.innerHTML = html;
}

let homeInterval = null;
function startHomeRefresh() {
  if (homeInterval) clearInterval(homeInterval);
  homeInterval = setInterval(() => {
    if (document.getElementById('pg-home').classList.contains('active')) {
      loadUserData();
    }
  }, 30000);
}

// ---------- STAKE SELECTION ----------
async function loadStakeGrid() {
  const stakes = [10, 20, 50, 100];
  const container = document.getElementById('stakeGrid');
  container.innerHTML = '';
  stakes.forEach(s => {
    const btn = document.createElement('div');
    btn.className = 'amount-btn';
    btn.innerText = s + ' ETB';
    btn.onclick = () => selectStake(s);
    container.appendChild(btn);
  });
}

let selectedStake = null;
async function selectStake(stake) {
  selectedStake = stake;
  const result = await apiCall('/api/join_game', 'POST', { user_id: user.id, stake });
  if (result.error) {
    alert(result.error);
    return;
  }
  if (result.game_in_progress) {
    alert(result.message || "A game is already running. Please wait for next game.");
    return;
  }
  currentGame = {
    game_id: result.game_id,
    stake: result.stake,
    prize_pool: result.prize_pool,
    status: result.status,
    myCards: [],
    takenCards: result.taken_cards || []
  };
  // Go to card selection
  document.getElementById('sel-prize').innerText = result.prize_pool;
  document.getElementById('sel-players').innerText = result.players;
  document.getElementById('sel-stake').innerText = result.stake;
  renderCardGrid();
  startCountdown(result.countdown, result.game_id);
  goPage('pg-select');
}

function renderCardGrid() {
  const container = document.getElementById('selGrid');
  container.innerHTML = '';
  for (let i = 1; i <= 500; i++) {
    const btn = document.createElement('div');
    btn.className = 'cgrid-btn';
    btn.innerText = i;
    if (currentGame.takenCards.includes(i)) {
      btn.classList.add('taken');
      btn.innerText = '🔴';
    } else if (currentGame.myCards.includes(i)) {
      btn.classList.add('mine');
      btn.innerText = '🟡';
    } else {
      btn.onclick = () => pickCard(i);
    }
    container.appendChild(btn);
  }
  document.getElementById('myCardCount').innerText = `${currentGame.myCards.length}/4`;
}

async function pickCard(cardNum) {
  if (currentGame.myCards.length >= 4) {
    alert(translations.max_cards);
    return;
  }
  try {
    const result = await apiCall('/api/pick_card', 'POST', {
      user_id: user.id,
      game_id: currentGame.game_id,
      card_number: cardNum,
      stake: currentGame.stake
    });
    if (result.error) {
      alert(result.error);
      return;
    }
    currentGame.myCards.push(cardNum);
    currentGame.takenCards.push(cardNum);
    renderCardGrid();
    // Update balance
    document.getElementById('balanceDisplay').innerText = result.balance.toFixed(2) + ' ETB';
  } catch(e) { alert(e.message); }
}

async function leaveGame() {
  if (!confirm("Leave game? You will be refunded.")) return;
  const res = await apiCall('/api/withdraw_from_game', 'POST', {
    user_id: user.id,
    game_id: currentGame.game_id
  });
  if (res.success) {
    alert("Left game. Refunded.");
    goPage('pg-home');
    loadUserData();
  } else alert(res.error);
}

let countdownTimer = null;
function startCountdown(seconds, gameId) {
  if (countdownTimer) clearInterval(countdownTimer);
  let remaining = seconds;
  const cdElem = document.getElementById('cd1');
  const fill = document.getElementById('prog1');
  function update() {
    cdElem.innerText = remaining;
    fill.style.width = ((30 - remaining) / 30 * 100) + '%';
    if (remaining <= 0) {
      clearInterval(countdownTimer);
      // Game should have started; poll game state
      pollGameState(gameId);
    }
    remaining--;
  }
  update();
  countdownTimer = setInterval(update, 1000);
}

async function pollGameState(gameId) {
  if (gameStateInterval) clearInterval(gameStateInterval);
  gameStateInterval = setInterval(async () => {
    const state = await apiCall(`/api/game_state/${gameId}`);
    if (state.status === 'running') {
      clearInterval(gameStateInterval);
      startGame(state);
    } else if (state.status === 'finished') {
      clearInterval(gameStateInterval);
      // Show winner screen if needed
      if (state.winner_card_numbers && state.winner_card_numbers.length) {
        showWinner(state);
      } else {
        alert("Game finished with no winner.");
        goPage('pg-home');
      }
    }
  }, 2000);
}

// ---------- GAME PLAY ----------
let currentGameState = null;
function startGame(state) {
  currentGameState = state;
  document.getElementById('game-prize').innerText = state.prize_pool;
  document.getElementById('game-players').innerText = state.players;
  document.getElementById('game-called').innerText = state.drawn_balls.length + '/75';
  renderRecentChips(state.drawn_balls.slice(-10));
  renderMyCards(state);
  goPage('pg-game');
  // Start polling game state every 2 seconds
  if (gameStateInterval) clearInterval(gameStateInterval);
  gameStateInterval = setInterval(async () => {
    const newState = await apiCall(`/api/game_state/${currentGame.game_id}`);
    if (newState.status === 'finished') {
      clearInterval(gameStateInterval);
      if (newState.winner_card_numbers && newState.winner_card_numbers.length) {
        showWinner(newState);
      } else {
        alert("Game finished, but you didn't win.");
        goPage('pg-home');
        loadUserData();
      }
    } else {
      // Update UI
      document.getElementById('game-prize').innerText = newState.prize_pool;
      document.getElementById('game-players').innerText = newState.players;
      document.getElementById('game-called').innerText = newState.drawn_balls.length + '/75';
      if (newState.drawn_balls.length > (currentGameState?.drawn_balls?.length || 0)) {
        const lastBall = newState.drawn_balls[newState.drawn_balls.length-1];
        updateBallDisplay(lastBall);
        speak(lastBall.toString());
      }
      renderRecentChips(newState.drawn_balls.slice(-10));
      renderMyCards(newState);
      currentGameState = newState;
    }
  }, 2000);
}

function renderRecentChips(balls) {
  const container = document.getElementById('recentChips');
  container.innerHTML = balls.map(b => `<div class="chip">${b}</div>`).join('');
}

function updateBallDisplay(ball) {
  let letter = '';
  if (ball <= 15) letter = 'B';
  else if (ball <= 30) letter = 'I';
  else if (ball <= 45) letter = 'N';
  else if (ball <= 60) letter = 'G';
  else letter = 'O';
  document.getElementById('bLetter').innerText = letter;
  document.getElementById('bNum').innerText = ball;
}

async function renderMyCards(state) {
  // Fetch my card data
  const cardsData = await apiCall(`/api/my_cards/${currentGame.game_id}?user_id=${user.id}`);
  const wrap = document.getElementById('bingoCardsWrap');
  if (!cardsData.cards.length) {
    wrap.innerHTML = '<div class="card" style="text-align:center">No cards found</div>';
    return;
  }
  const count = cardsData.cards.length;
  wrap.className = `bingo-cards-wrap bingo-grid cards-${count}`;
  wrap.innerHTML = '';
  for (let idx=0; idx<cardsData.cards.length; idx++) {
    const card = cardsData.cards[idx];
    const cardData = JSON.parse(card.card_data);
    const marked = JSON.parse(card.marked_numbers || '[]');
    const box = document.createElement('div');
    box.className = 'bingo-card-box';
    box.innerHTML = `<div class="bcard-header"><div class="bcard-title">🎯 CARD ${card.card_number}</div></div>
      <div class="bcol-headers"><div class="bcol-h">B</div><div class="bcol-h">I</div><div class="bcol-h">N</div><div class="bcol-h">G</div><div class="bcol-h">O</div></div>`;
    for (let r=0; r<5; r++) {
      const rowDiv = document.createElement('div');
      rowDiv.className = 'brow';
      for (let c=0; c<5; c++) {
        const cellVal = cardData[r][c];
        const isHit = marked.includes(cellVal);
        const isFree = (r===2 && c===2);
        const cellDiv = document.createElement('div');
        cellDiv.className = 'bcell';
        if (isHit) cellDiv.classList.add('hit');
        if (isFree && !isHit) cellDiv.classList.add('free');
        cellDiv.innerText = (isFree && !isHit) ? '⭐' : cellVal;
        rowDiv.appendChild(cellDiv);
      }
      box.appendChild(rowDiv);
    }
    wrap.appendChild(box);
  }
}

function showWinner(state) {
  // Show winner screen with next game countdown
  goPage('pg-winner');
  const winnerCardsDiv = document.getElementById('winnerCards');
  if (state.winner_details && state.winner_details.length) {
    let html = '';
    state.winner_details.forEach(w => {
      html += `<div style="background:rgba(255,215,0,0.2); margin:6px; padding:8px; border-radius:8px;">🏆 ${w.username} - Card ${w.card_number}</div>`;
    });
    winnerCardsDiv.innerHTML = html;
  } else {
    winnerCardsDiv.innerHTML = '<div>You won! Check your balance.</div>';
  }
  let countdown = 5;
  const nextSpan = document.getElementById('nextNum');
  const timer = setInterval(() => {
    nextSpan.innerText = countdown;
    countdown--;
    if (countdown < 0) {
      clearInterval(timer);
      goPage('pg-home');
      loadUserData();
    }
  }, 1000);
}

// ---------- DEPOSIT / WITHDRAW / INQUIRY ----------
function loadDepositAmounts() {
  const amounts = [50,100,200,500];
  const container = document.getElementById('depAmtGrid');
  container.innerHTML = '';
  amounts.forEach(a => {
    const btn = document.createElement('div');
    btn.className = 'amount-btn';
    btn.innerText = a + ' ETB';
    btn.onclick = () => { document.getElementById('depCustomAmt').value = a; };
    container.appendChild(btn);
  });
}

let selectedPlatform = 'telebirr';
function selectPlatform(platform) {
  selectedPlatform = platform;
  const telNum = document.getElementById('telebirrNumberPlaceholder').innerText;
  const cbeNum = document.getElementById('cbeNumberPlaceholder').innerText;
  document.getElementById('depPlatformNum').innerText = platform === 'telebirr' ? telNum : cbeNum;
  goPage('pg-dep-confirm');
  const amount = parseFloat(document.getElementById('depCustomAmt').value);
  document.getElementById('depAmountShow').innerText = amount + ' ETB';
  const ref = 'BINGO-' + user.id + '-' + Date.now();
  document.getElementById('depRef').innerText = ref;
  window.depositData = { amount, platform, ref };
}

async function submitDeposit() {
  const proof = document.getElementById('depProof').value.trim();
  if (!proof) { alert("Please enter transaction reference"); return; }
  const res = await apiCall('/api/deposit', 'POST', {
    user_id: user.id,
    amount: window.depositData.amount,
    platform: window.depositData.platform,
    proof: proof
  });
  if (res.success) {
    alert(translations.deposit_success);
    goPage('pg-home');
    loadUserData();
  } else alert(res.error);
}

let wdPlatform = 'telebirr';
function setWdPlatform(platform, elem) {
  wdPlatform = platform;
  document.querySelectorAll('.platform-btn').forEach(btn => btn.style.border = '');
  elem.style.border = '2px solid var(--gold)';
  document.getElementById('wd-platform').value = platform;
}
async function submitWithdraw() {
  const amount = parseFloat(document.getElementById('wdAmount').value);
  const account = document.getElementById('wdAccount').value.trim();
  if (!amount || amount < 50) { alert("Minimum withdrawal 50 ETB"); return; }
  if (!account) { alert("Account number required"); return; }
  const res = await apiCall('/api/withdraw', 'POST', {
    user_id: user.id,
    amount: amount,
    method: wdPlatform,
    account: account
  });
  if (res.success) {
    alert(translations.withdrawal_requested);
    goPage('pg-home');
    loadUserData();
  } else alert(res.error);
}

async function submitInquiry() {
  const subject = document.getElementById('inqSubject').value;
  const msg = document.getElementById('inqMessage').value;
  if (!subject || !msg) { alert("Please fill all fields"); return; }
  const res = await apiCall('/api/inquiry', 'POST', { user_id: user.id, subject, message: msg });
  if (res.success) {
    alert(translations.inquiry_sent);
    goPage('pg-help');
  } else alert(res.error);
}

function copyReferralLink() {
  const link = document.getElementById('referralLinkAnchor').href;
  navigator.clipboard.writeText(link);
  alert(translations.copy_success);
}

// ---------- NAVIGATION ----------
function goPage(pageId) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(pageId).classList.add('active');
  if (pageId === 'pg-stake') loadStakeGrid();
  if (pageId === 'pg-deposit') loadDepositAmounts();
  if (pageId === 'pg-home') loadUserData();
  if (pageId === 'pg-select' && currentGame) {
    renderCardGrid();
    startCountdown(30, currentGame.game_id);
  }
}

function navTo(pageId, navItem) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  navItem.classList.add('active');
  goPage(pageId);
}

function toggleLang() {
  currentLang = currentLang === 'en' ? 'am' : 'en';
  loadTranslations(currentLang);
  localStorage.setItem('nef_lang', currentLang);
  if (user) {
    apiCall('/api/update_profile', 'POST', { user_id: user.id, language: currentLang });
  }
}

// Only needed if you have an admin panel (not shown)
function showAdminPanel() {
  // optional
}

// ---------- INITIALIZATION ----------
window.onload = async () => {
  // Initialize Telegram or web user
  if (tg) {
    tg.expand();
    user = tg.initDataUnsafe?.user;
    if (!user) user = { id: 123456, username: 'demo', first_name: 'Demo' };
  } else {
    // Fallback for web testing
    user = { id: Math.floor(Math.random() * 1000000), username: 'webuser', first_name: 'Web' };
  }
  const savedLang = localStorage.getItem('nef_lang') || 'en';
  currentLang = savedLang;
  loadTranslations(currentLang);
  // Check if already registered
  const phone = localStorage.getItem('nef_phone');
  if (phone) {
    // Assume registered
    await loadUserData();
    document.getElementById('pg-register').classList.remove('active');
    document.getElementById('pg-home').classList.add('active');
    startHomeRefresh();
  } else {
    document.getElementById('pg-register').classList.add('active');
  }
  // Set default platform numbers from settings (you can fetch via API)
  fetch('/api/settings/telebirr').then(r=>r.json()).then(data => {
    if (data.number) document.getElementById('telebirrNumberPlaceholder').innerText = data.number;
  }).catch(()=>{});
  fetch('/api/settings/cbe').then(r=>r.json()).then(data => {
    if (data.number) document.getElementById('cbeNumberPlaceholder').innerText = data.number;
  }).catch(()=>{});
};

