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

// Refresh function (soft refresh - re-fetch data without reloading page)
function refreshPage() {
  if (state.user) {
    loadUser();
    loadLeaderboard();
    loadRecentGames();
    loadLatestNotification();
  }
}

let pollInterval = null;
let countdownPollInterval = null;
// Guards so only ONE request is ever in flight per poller (prevents overlapping,
// out-of-order responses on slow connections). lastCountdownShown keeps the
// countdown from ever ticking upward within a single waiting period.
let countdownBusy = false;
let gameBusy = false;
let lastCountdownShown = Infinity;

// ---------- Translations (EN and AM) ----------
const LANG = {
  en: {
    'balance': 'Your Balance', 'deposit': 'Deposit', 'withdraw': 'Withdraw',
    'games': 'Games', 'wins': 'Wins', 'won': 'Won ETB',
    'playNow': '🎮 PLAY NOW', 'selectStake': 'Select Stake',
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
    'transactionRef': 'Reference', 'your_referral_link': '🔗 Your Referral Link',
    'copy_link': '📋 Copy Link',
    'referral_bonus_text': '✨ Share this link with friends. When they register, you get <strong>{bonus} ETB</strong> instantly!',
    'referral_commission_text': '🎁 Plus, you earn <strong>{percent}% of the prize pool</strong> every time they win a game.',
    'copy_success': 'Link copied!', 'copy_fail': 'Failed to copy', 'leave_game': 'Leave Game',
    // navbar
    'nav_home': 'Home', 'nav_play': 'Play', 'nav_deposit': 'Deposit', 'nav_how': 'How To', 'nav_help': 'Help',
    'home': 'Home',
    // home screen
    'announcement': '📢 Announcement', 'topPlayers': '🏆 Top 5 Players',
    'recentGames': 'Recent Games (last 3)', 'noGames': 'No games yet',
    'noPlayers': 'No players yet', 'loading': 'Loading...',
    // select / game
    'sec': 'sec', 'cardLegend': '🟡 Yours  🔴 Taken  ⬜ Available',
    'waitingPlayers': 'Waiting for players…',
    'gameInProgress': '🎲 A game is in progress. You are watching the current round.',
    // deposit
    'selectAmount': 'Select Amount', 'customAmount': 'Or custom amount',
    'selectPlatform': 'Select Platform', 'paymentInstr': 'Payment Instructions',
    'sendExactly': 'Send exactly', 'number': 'Number', 'uploadProof': 'Upload Proof',
    'submit': 'Submit', 'balanceUpdated': '✅ Balance updated',
    // withdraw
    'availableBalance': 'Available Balance', 'requestWithdrawal': 'Request Withdrawal',
    // help / inquiry
    'send': 'Send', 'messageAdmin': 'Message the admin directly', 'gameRules': 'Game rules',
    // winner
    'winnerSub': 'BINGO! Winner!', 'noWinner': 'No winner this round',
    'noCards': 'No cards selected', 'cardUnavailable': 'Card data unavailable',
    'cardLabel': 'Card', 'player': 'Player',
    // how-to steps (HTML)
    'step1': '<b>Deposit via Telebirr or CBE.</b><br>Confirmed by admin within 30 min.',
    'step2': '<b>Choose 10, 20, 50 or 100 ETB.</b><br>Higher stake = bigger prize!',
    'step3': '<b>Select up to 4 cards from 1-500.</b><br>🟡=yours, 🔴=taken. Game starts after 30 sec.',
    'step4': '<b>Numbers called every 2 seconds.</b><br>Your card updates live with ⭐.',
    'step5': '<b>Complete a row, column or diagonal to win!</b><br>Prize split if multiple winners.',
    'step6': '<b>Request withdrawal to Telebirr or CBE.</b><br>Processed within 24 hours.',
    'faqContent': '<b>How long does deposit take?</b><br>Usually 5-30 minutes after proof submitted.<br><br><b>Withdrawal time?</b><br>Within 24 hours on business days.<br><br><b>What if game cancels?</b><br>Full refund automatically credited.',
    // placeholders
    'phEnterAmount': 'Enter amount...', 'phTxRef': 'Transaction reference number...',
    'phAccount': 'e.g. 0912345678', 'phSubject': 'e.g. Deposit not confirmed...',
    'phMessage': 'Describe your issue...',
    // alerts
    'alertValidPhone': 'Please enter a valid phone number (e.g., 0912345678)',
    'alertRegFailed': 'Registration failed. Please try again.',
    'alertJoinFailed': 'Failed to join game', 'alertPickFailed': 'Failed to pick card',
    'alertGameStarted': 'Game already started! Please wait for the next game.',
    'leaveConfirm': 'Leave game? You will be refunded for unpicked cards.',
    'leftRefunded': 'Left game. Refunded.', 'leaveFailed': 'Failed to leave: ',
    'alertPasteProof': 'Please paste transaction reference or SMS content',
    'networkError': 'Network error', 'minWithdrawal': 'Minimum withdrawal 50 ETB',
    'enterAccount': 'Enter account number', 'requestFailed': 'Request failed',
    'fillSubjectMessage': 'Please fill subject and message', 'failedSend': 'Failed to send',
    'unknownError': 'Unknown error'
  },
  am: {
    'balance': 'የእርስዎ ቀሪ ሒሳብ', 'deposit': 'ገንዘብ ማስገባት', 'withdraw': 'ገንዘብ ማውጣት',
    'games': 'ጨዋታዎች', 'wins': 'ድሎች', 'won': 'ያሸነፉት ETB',
    'playNow': '🎮 አሁን ይጫወቱ', 'selectStake': 'የሚወራረዱበትን መጠን ይምረጡ',
    'gameStartsIn': 'ጨዋታ የሚጀምረው በ', 'yourCards': 'ካርዶችዎ',
    'prizePool': 'የሽልማት ገንዘብ', 'players': 'ተጫዋቾች', 'stake': 'ውርርድ',
    'called': 'የተጠራ', 'recent': 'የቅርብ ጊዜ', 'bingo': 'ቢንጎ!',
    'nextGame': 'ቀጣይ ጨዋታ', 'seconds': 'ሰከንዶች', 'back': 'ተመለስ',
    'insufficient': 'በቂ ቀሪ ሒሳብ የለም',
    'maxCards': 'በአንድ ጨዋታ ከ4 ካርዶች መጠቀም አይቻልም', 'depositSuccess': '✅ {amount} ETB ተጨምሯል!',
    'depositPending': '⏳ ተቀማጭ ገንዘብ ለአስተዳዳሪ ምርመራ ቀርቧል።',
    'withdrawSuccess': 'የማውጣት ጥያቄ ተልኳል።', 'inquirySuccess': 'መልእክት ተልኳል።',
    'gameCancelled': 'ጨዋታው በበቂ ተጫዋቾች እጥረት ተሰርዟል። ገንዘብዎ ተመልሷል።',
    'howToPlay': 'እንዴት መጫወት እንደሚቻል', 'help': 'እርዳታ', 'faq': 'ተደጋጋሚ ጥያቄዎች',
    'sendInquiry': 'መልእክት ላክ', 'subject': 'ርዕስ', 'message': 'መልእክት',
    'amount': 'መጠን', 'accountNumber': 'የሂሳብ ቁጥር', 'platform': 'መድረክ',
    'transactionRef': 'ማጣቀሻ', 'your_referral_link': '🔗 የእርስዎ ማጣቀሻ ሊንክ',
    'copy_link': '📋 ሊንኩን ቅዳ',
    'referral_bonus_text': '✨ ይህን ሊንክ ከጓደኞችዎ ጋር ያጋሩ። ሲመዘገቡ እርስዎ <strong>{bonus} ETB</strong> ወዲያውኑ ያገኛሉ!',
    'referral_commission_text': '🎁 በተጨማሪም ጓደኞችዎ በሚያሸንፉበት ጊዜ ከሽልማቱ ገንዘብ <strong>{percent}%</strong> ያገኛሉ።',
    'copy_success': 'ሊንክ ተቀድቷል!', 'copy_fail': 'መቅዳት አልተሳካም', 'leave_game': 'ጨዋታ ለቀቅ',
    // navbar
    'nav_home': 'መነሻ', 'nav_play': 'ተጫወት', 'nav_deposit': 'ተቀማጭ', 'nav_how': 'እንዴት', 'nav_help': 'እርዳታ',
    'home': 'መነሻ',
    // home screen
    'announcement': '📢 ማስታወቂያ', 'topPlayers': '🏆 ምርጥ 5 ተጫዋቾች',
    'recentGames': 'የቅርብ ጊዜ ጨዋታዎች (የመጨረሻ 3)', 'noGames': 'እስካሁን ጨዋታ የለም',
    'noPlayers': 'እስካሁን ተጫዋች የለም', 'loading': 'በመጫን ላይ...',
    // select / game
    'sec': 'ሰከንድ', 'cardLegend': '🟡 የእርስዎ  🔴 የተያዘ  ⬜ ነፃ',
    'waitingPlayers': 'ተጫዋቾችን በመጠበቅ ላይ…',
    'gameInProgress': '🎲 ጨዋታ በመካሄድ ላይ ነው። የአሁኑን ዙር እየተመለከቱ ነው።',
    // deposit
    'selectAmount': 'መጠን ይምረጡ', 'customAmount': 'ወይም የራስዎ መጠን ያስገቡ',
    'selectPlatform': 'መድረክ ይምረጡ', 'paymentInstr': 'የክፍያ መመሪያዎች',
    'sendExactly': 'በትክክል ይላኩ', 'number': 'ቁጥር', 'uploadProof': 'ማስረጃ ይስቀሉ',
    'submit': 'አስገባ', 'balanceUpdated': '✅ ቀሪ ሒሳብ ተዘምኗል',
    // withdraw
    'availableBalance': 'ያለ ቀሪ ሒሳብ', 'requestWithdrawal': 'ማውጣት ይጠይቁ',
    // help / inquiry
    'send': 'ላክ', 'messageAdmin': 'ለአስተዳዳሪው በቀጥታ መልእክት ይላኩ', 'gameRules': 'የጨዋታ ህጎች',
    // winner
    'winnerSub': 'ቢንጎ! አሸናፊ!', 'noWinner': 'በዚህ ዙር አሸናፊ የለም',
    'noCards': 'ምንም ካርድ አልተመረጠም', 'cardUnavailable': 'የካርድ መረጃ የለም',
    'cardLabel': 'ካርድ', 'player': 'ተጫዋች',
    // how-to steps (HTML)
    'step1': '<b>በቴሌብር ወይም በCBE ያስገቡ።</b><br>በ30 ደቂቃ ውስጥ በአስተዳዳሪ ይረጋገጣል።',
    'step2': '<b>10፣ 20፣ 50 ወይም 100 ETB ይምረጡ።</b><br>ከፍ ያለ ውርርድ = ትልቅ ሽልማት!',
    'step3': '<b>ከ1-500 ውስጥ እስከ 4 ካርዶች ይምረጡ።</b><br>🟡=የእርስዎ፣ 🔴=የተያዘ። ጨዋታ ከ30 ሰከንድ በኋላ ይጀምራል።',
    'step4': '<b>ቁጥሮች በየ2 ሰከንዱ ይጠራሉ።</b><br>ካርድዎ በ⭐ በቀጥታ ይዘመናል።',
    'step5': '<b>ለማሸነፍ ረድፍ፣ አምድ ወይም ሰያፍ ያጠናቅቁ!</b><br>ብዙ አሸናፊዎች ካሉ ሽልማቱ ይከፈላል።',
    'step6': '<b>ወደ ቴሌብር ወይም CBE ማውጣት ይጠይቁ።</b><br>በ24 ሰዓት ውስጥ ይከናወናል።',
    'faqContent': '<b>ተቀማጭ ምን ያህል ጊዜ ይወስዳል?</b><br>ማስረጃ ከቀረበ በኋላ ብዙውን ጊዜ 5-30 ደቂቃ።<br><br><b>የማውጣት ጊዜ?</b><br>በስራ ቀናት በ24 ሰዓት ውስጥ።<br><br><b>ጨዋታ ቢሰረዝስ?</b><br>ሙሉ ገንዘብ በራስ-ሰር ይመለሳል።',
    // placeholders
    'phEnterAmount': 'መጠን ያስገቡ...', 'phTxRef': 'የግብይት ማጣቀሻ ቁጥር...',
    'phAccount': 'ለምሳሌ 0912345678', 'phSubject': 'ለምሳሌ ተቀማጭ አልተረጋገጠም...',
    'phMessage': 'ችግርዎን ይግለጹ...',
    // alerts
    'alertValidPhone': 'እባክዎ ትክክለኛ ስልክ ቁጥር ያስገቡ (ለምሳሌ 0912345678)',
    'alertRegFailed': 'ምዝገባ አልተሳካም። እባክዎ እንደገና ይሞክሩ።',
    'alertJoinFailed': 'ጨዋታ መቀላቀል አልተሳካም', 'alertPickFailed': 'ካርድ መምረጥ አልተሳካም',
    'alertGameStarted': 'ጨዋታ ተጀምሯል! እባክዎ ቀጣዩን ጨዋታ ይጠብቁ።',
    'leaveConfirm': 'ጨዋታ ለቀቅ? ላልተመረጡ ካርዶች ገንዘብዎ ይመለሳል።',
    'leftRefunded': 'ከጨዋታ ወጥተዋል። ገንዘብ ተመልሷል።', 'leaveFailed': 'መውጣት አልተሳካም: ',
    'alertPasteProof': 'እባክዎ የግብይት ማጣቀሻ ወይም የSMS ይዘት ይለጥፉ',
    'networkError': 'የኔትወርክ ስህተት', 'minWithdrawal': 'ዝቅተኛ ማውጣት 50 ETB',
    'enterAccount': 'የሂሳብ ቁጥር ያስገቡ', 'requestFailed': 'ጥያቄ አልተሳካም',
    'fillSubjectMessage': 'እባክዎ ርዕስ እና መልእክት ይሙሉ', 'failedSend': 'መላክ አልተሳካም',
    'unknownError': 'ያልታወቀ ስህተት'
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
  // Plain-text elements (innerText)
  const ids = {
    'balanceLabel': 'balance', 'depositBtnText': 'deposit', 'withdrawBtnText': 'withdraw',
    'statGamesLbl': 'games', 'statWinsLbl': 'wins', 'statWonLbl': 'won',
    'playBtn': 'playNow', 'stakeTitle': 'selectStake', 'gameStartsLabel': 'gameStartsIn',
    'yourCardsLabel': 'yourCards', 'selPrizeLbl': 'prizePool', 'selPlayersLbl': 'players',
    'selStakeLbl': 'stake', 'gamePrizeLbl': 'prizePool', 'gamePlayersLbl': 'players',
    'gameCalledLbl': 'called', 'recentLabel': 'recent', 'winnerTitle': 'bingo',
    'nextGameLabel': 'nextGame', 'secondsLabel': 'seconds', 'stakeBackText': 'back',
    'selectHomeBtn': 'home', 'gameHomeBtn': 'home', 'winnerHomeBtn': 'home',
    'depBackText': 'back', 'confBackText': 'back', 'wdBackText': 'back',
    'inqBackText': 'back', 'submitDepositBtn': 'submit', 'requestWithdrawBtn': 'requestWithdrawal',
    'sendInquiryBtn': 'send', 'subjectLabel': 'subject', 'messageLabel': 'message',
    'amountLabel': 'amount', 'accountNumberLabel': 'accountNumber',
    'wdPlatformTitle': 'platform', 'referenceLabel': 'transactionRef', 'leaveGameBtn': 'leave_game',
    // newly covered:
    'navHomeLabel': 'nav_home', 'navPlayLabel': 'nav_play', 'navDepositLabel': 'nav_deposit',
    'navHowLabel': 'nav_how', 'navHelpLabel': 'nav_help',
    'leaderboardTitle': 'topPlayers', 'recentTitle': 'recentGames',
    'secLabel': 'sec', 'cardLegend': 'cardLegend', 'winnerSub': 'winnerSub',
    'depAmountTitle': 'selectAmount', 'customAmountLabel': 'customAmount',
    'depPlatformTitle': 'selectPlatform', 'paymentInstrTitle': 'paymentInstr',
    'sendExactlyLabel': 'sendExactly', 'numberLabel': 'number', 'uploadProofTitle': 'uploadProof',
    'withdrawTitle': 'withdraw', 'availableBalanceLabel': 'availableBalance',
    'howtoTitle': 'howToPlay', 'helpTitle': 'help',
    'sendInquiryLabel': 'sendInquiry', 'messageAdminLabel': 'messageAdmin',
    'howToPlayLabel': 'howToPlay', 'howToPlaySub': 'gameRules', 'faqTitle': 'faq',
    'inquiryTitle': 'sendInquiry', 'balanceUpdatedMsg': 'balanceUpdated'
  };
  for (let [id, key] of Object.entries(ids)) {
    const el = document.getElementById(id);
    if (el) el.innerText = T(key);
  }
  // Elements whose content includes markup (innerHTML)
  const htmlIds = {
    'step1Text': 'step1', 'step2Text': 'step2', 'step3Text': 'step3',
    'step4Text': 'step4', 'step5Text': 'step5', 'step6Text': 'step6',
    'faqContent': 'faqContent'
  };
  for (let [id, key] of Object.entries(htmlIds)) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = T(key);
  }
  // Input placeholders
  const phIds = {
    'depCustomAmt': 'phEnterAmount', 'depProof': 'phTxRef', 'wdAmount': 'phEnterAmount',
    'wdAccount': 'phAccount', 'inqSubject': 'phSubject', 'inqMessage': 'phMessage'
  };
  for (let [id, key] of Object.entries(phIds)) {
    const el = document.getElementById(id);
    if (el) el.placeholder = T(key);
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
  try {
    const res = await apiCall('/api/settings/stakes');
    if (res && res.stakes && Array.isArray(res.stakes)) {
      state.allowedStakes = res.stakes;
      console.log('Loaded stakes:', state.allowedStakes);
    } else {
      console.warn('No stakes in response, using defaults:', state.allowedStakes);
    }
  } catch (err) {
    console.warn('Failed to load stakes, using defaults:', state.allowedStakes, err);
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
  // NEW: update balance on game and select pages
  const gameBalance = document.getElementById('game-balance');
  if (gameBalance) gameBalance.innerText = (state.balance || 0).toFixed(2) + ' ETB';
  const selBalance = document.getElementById('sel-balance');
  if (selBalance) selBalance.innerText = (state.balance || 0).toFixed(2) + ' ETB';
  const gamesEl = document.getElementById('stat-games');
  if (gamesEl) gamesEl.innerText = state.games_played || 0;
  const winsEl = document.getElementById('stat-wins');
  if (winsEl) winsEl.innerText = state.wins || 0;
  const wonEl = document.getElementById('stat-won');
  if (wonEl) wonEl.innerText = (state.total_won || 0).toFixed(0);
}

// ---------- Language toggle ----------
function toggleLang() {
  state.lang = state.lang === 'en' ? 'am' : 'en';
  updateUILanguage();
  displayReferralInfo();
  if (state.user && state.user.user_id) {
    apiCall('/api/update_profile', 'POST', { user_id: state.user.user_id, language: state.lang });
  }
}

// ---------- Refresh page (reload data, no navigation) ----------
async function refreshPage() {
  // Home page: reload user data and dynamic lists
  if (document.getElementById('pg-home').classList.contains('active')) {
    await loadUser();
    loadLeaderboard();
    loadRecentGames();
    displayReferralInfo();
    loadLatestNotification();
    renderUI();
    return;
  }
  // Card selection page: refresh game info and cards
  if (document.getElementById('pg-select').classList.contains('active')) {
    if (state.gameId) {
      await refreshGameInfo();
      await loadMyCards();
      startCountdownPolling();
    }
    return;
  }
  // Game playing page: refresh game state (balls, cards)
  if (document.getElementById('pg-game').classList.contains('active')) {
    if (state.gameId) {
      const res = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
      if (res && !res.error) {
        updateGameUI(res);
      }
    }
    return;
  }
  // Winner page: refresh winner info (but stay on winner)
  if (document.getElementById('pg-winner').classList.contains('active')) {
    if (state.gameId) {
      const res = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
      if (res && !res.error) {
        showWinner(res);
      }
    }
    return;
  }
  // Fallback: just reload user data and render UI
  await loadUser();
  renderUI();
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
    alert(T('alertValidPhone'));
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
    alert(res?.error || T('alertRegFailed'));
  }
}

// ---------- Game functions ----------
function buildStakeGrid() {
  const grid = document.getElementById('stakeGrid');
  if (!grid) {
    console.warn('stakeGrid element not found');
    return;
  }
  grid.innerHTML = '';
  
  if (!state.allowedStakes || state.allowedStakes.length === 0) {
    grid.innerHTML = '<p style="color:var(--sub);padding:10px;text-align:center;">No stakes available</p>';
    return;
  }
  
  state.allowedStakes.forEach(s => {
    const btn = document.createElement('div');
    btn.className = 'amount-btn';
    btn.innerText = s + ' ETB';
    btn.style.cursor = 'pointer';
    btn.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      joinGame(s);
    };
    grid.appendChild(btn);
  });
}

// joinGame with clearing
async function joinGame(stake) {
  if (!state.user) { alert('Not logged in'); return; }
  if (state.balance < stake) { alert(T('insufficient')); return; }
  
  try {
    // Clear previous game data and polling
    state.myCards = [];
    state.myCardData = [];
    state.takenCards = [];
    state.gameId = null;
    state.stake = stake;
    
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    if (countdownPollInterval) { clearInterval(countdownPollInterval); countdownPollInterval = null; }

    // Clear UI safely
    const selGrid = document.getElementById('selGrid');
    if (selGrid) selGrid.innerHTML = '';
    const myCardCountEl = document.getElementById('myCardCount');
    if (myCardCountEl) myCardCountEl.innerText = '0/4';

    // Call API to join/create game
    const res = await apiCall('/api/join_game', 'POST', { stake });
    if (!res || res.error) { 
      alert(res?.error || 'Failed to join game'); 
      return; 
    }

    state.gameId = res.game_id;

    // If game is already running, jump to it
    if (res.game_in_progress) {
      updateGameUI(res);
      startGamePolling();
      goPage('pg-game');
      const banner = document.getElementById('notificationBanner');
      const notifyText = document.getElementById('notifyText');
      if (banner && notifyText) {
        notifyText.innerHTML = T('gameInProgress');
        banner.style.display = 'block';
        setTimeout(() => banner.style.display = 'none', 8000);
      }
      return;
    }

    // Game is waiting – show countdown page
    const remaining = res.countdown_remaining || 30;
    const cdEl = document.getElementById('cd1');
    const progEl = document.getElementById('prog1');
    if (cdEl) cdEl.innerText = remaining;
    if (progEl) progEl.style.width = ((30 - remaining) / 30 * 100) + '%';

    const prizeEl = document.getElementById('sel-prize');
    if (prizeEl) prizeEl.innerText = '0 ETB';
    const playersEl = document.getElementById('sel-players');
    if (playersEl) playersEl.innerText = T('waitingPlayers');
    const stakeEl = document.getElementById('sel-stake');
    if (stakeEl) stakeEl.innerText = stake + ' ETB';

    // Fetch game info and cards
    await refreshGameInfo();
    await loadMyCards();
    buildCardGrid(state.takenCards || []);
    
    // Start polling for countdown
    startCountdownPolling();
    goPage('pg-select');
  } catch (err) {
    console.error('Error in joinGame:', err);
    alert('An error occurred. Please try again.');
  }
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
  if (!btn || btn.classList.contains('mine') || btn.classList.contains('taken')) return;

  // Optimistic UI
  btn.classList.add('mine');
  btn.classList.remove('taken');
  btn.innerText = `🟡${cardNumber}`;
  btn.onclick = null;
  state.myCards.push(cardNumber);
  document.getElementById('myCardCount').innerText = `${state.myCards.length}/4`;

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
    state.myCards = state.myCards.filter(c => c !== cardNumber);
    document.getElementById('myCardCount').innerText = `${state.myCards.length}/4`;
    if (res?.error === 'Game has already started or finished') {
      alert(T('alertGameStarted'));
      location.reload();
    } else {
      alert(res?.error || T('alertPickFailed'));
    }
    return;
  }

  if (res.balance !== undefined) {
    state.balance = res.balance;
    renderUI();
  }
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
}

async function leaveGame() {
  if (!state.gameId || !state.user) return;
  if (confirm(T('leaveConfirm'))) {
    const res = await apiCall('/api/withdraw_from_game', 'POST', {
      user_id: state.user.user_id,
      game_id: state.gameId
    });
    if (res && res.success) {
      alert(res.message || T('leftRefunded'));
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
      alert(T('leaveFailed') + (res?.error || T('unknownError')));
    }
  }
}

async function refreshGameInfo() {
  if (!state.gameId || !state.user) return;
  const requestedGameId = state.gameId;

  // 🧹 Clear the card grid immediately to hide old cards
  const grid = document.getElementById('selGrid');
  if (grid) grid.innerHTML = '';
  document.getElementById('myCardCount').innerText = '0/4';
  
  const res = await apiCall(`/api/game_state/${requestedGameId}?user_id=${state.user.user_id}`);
  if (state.gameId !== requestedGameId) return; // game moved on while this was in flight — discard
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
  const requestedGameId = state.gameId;
  const res = await apiCall(`/api/my_cards/${requestedGameId}?user_id=${state.user.user_id}`);
  if (state.gameId !== requestedGameId) return; // game moved on while this was in flight — discard
  if (res && res.cards) {
    state.myCardData = res.cards;
    state.myCards = res.cards.map(c => c.card_number).filter(n => n != null);
  }
}

function startCountdownPolling() {
  if (countdownPollInterval) clearInterval(countdownPollInterval);
  countdownBusy = false;
  lastCountdownShown = Infinity;
  const cdEl = document.getElementById('cd1');
  const progEl = document.getElementById('prog1');

  async function tick() {
    if (countdownBusy) return;               // a request is still in flight — skip
    if (!state.gameId || !state.user) {
      clearInterval(countdownPollInterval);
      countdownPollInterval = null;
      return;
    }
    const requestedGameId = state.gameId;
    countdownBusy = true;
    try {
      const gameState = await apiCall(`/api/game_state/${requestedGameId}?user_id=${state.user.user_id}`);
      if (state.gameId !== requestedGameId) return; // game moved on while this was in flight — discard
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
        updateGameUI(gameState);             // paint cards + first ball immediately
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
      if (gameState.status === 'waiting') {
        let remaining = typeof gameState.countdown_remaining === 'number' ? gameState.countdown_remaining : 0;
        if (remaining > lastCountdownShown) remaining = lastCountdownShown;  // never tick upward
        lastCountdownShown = remaining;
        if (cdEl) cdEl.innerText = remaining;
        if (progEl) progEl.style.width = (Math.max(0, (30 - remaining) / 30 * 100)) + '%';

        const prize = gameState.total_winners_prize || Math.floor((gameState.prize_pool || 0) * 0.8);
        const selPrize = document.getElementById('sel-prize');
        if (selPrize) selPrize.innerText = prize + ' ETB';
        const selPlayers = document.getElementById('sel-players');
        if (selPlayers) selPlayers.innerText = (gameState.players || 0) === 0 ? T('waitingPlayers') : gameState.players;

        const newTaken = gameState.taken_cards || [];
        if (JSON.stringify(state.takenCards) !== JSON.stringify(newTaken)) {
          state.takenCards = newTaken;
          buildCardGrid(state.takenCards);
        }
      }
    } finally {
      countdownBusy = false;
    }
  }

  tick();                                     // run immediately, don't wait 1s
  countdownPollInterval = setInterval(tick, 1000);
}

function startGamePolling() {
  if (pollInterval) clearInterval(pollInterval);
  gameBusy = false;

  async function tick() {
    if (gameBusy) return;                    // a request is still in flight — skip
    if (!state.gameId || !state.user) return;
    const requestedGameId = state.gameId;
    gameBusy = true;
    try {
      const res = await apiCall(`/api/game_state/${requestedGameId}?user_id=${state.user.user_id}`);
      if (state.gameId !== requestedGameId) return; // game moved on while this was in flight — discard
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
    } finally {
      gameBusy = false;
    }
  }

  tick();                                     // run immediately, don't wait 500ms
  pollInterval = setInterval(tick, 1000);
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
  if (playersEl) playersEl.innerText = gameState.players || 0;

  const chipsEl = document.getElementById('recentChips');
  if (chipsEl) chipsEl.innerHTML = drawn.slice(-6).reverse().map(b => `<div class="chip">${b}</div>`).join('');

  renderMyCards(drawn);
}

async function renderMyCards(drawnBalls) {
  const wrap = document.getElementById('bingoCardsWrap');
  if (!wrap) return;
  // Cards don't change during a running game, so only fetch them if we don't
  // already have them. This avoids a network round-trip on every poll tick,
  // which is what made cards appear only after several balls were called.
  if (!state.myCardData || !state.myCardData.length) {
    await loadMyCards();
  }
  if (!state.myCardData || !state.myCardData.length) {
    wrap.innerHTML = `<div style="text-align:center;color:var(--sub);padding:20px">${T('noCards')}</div>`;
    return;
  }
  const drawnNumbers = (drawnBalls || []).map(b => {
    const num = parseInt(b.replace(/[^0-9]/g, ''));
    return isNaN(num) ? null : num;
  }).filter(n => n !== null);
  const drawnSet = new Set(drawnNumbers);

  const cardsHtml = state.myCardData.map(card => buildCardHTML(card.card, drawnSet, card.card_number)).join('');
  const cardCount = state.myCardData.length;
  let gridClass = 'cards-1';
  if (cardCount === 2) gridClass = 'cards-2';
  else if (cardCount === 3) gridClass = 'cards-3';
  else if (cardCount === 4) gridClass = 'cards-4';
  wrap.innerHTML = `<div class="bingo-grid ${gridClass}">${cardsHtml}</div>`;
}

function buildCardHTML(cardData, drawnNumbersSet, cardNumber) {
  if (!cardData) return `<div class="bingo-card-box"><p style="color:var(--sub);padding:10px">${T('cardUnavailable')}</p></div>`;
  let html = `<div class="bingo-card-box">
    <div class="bcard-header"><div class="bcard-title">🎴 ${T('cardLabel')} #${cardNumber || '?'}</div></div>
    <div class="bcol-headers">`;
  ['B','I','N','G','O'].forEach(l => html += `<div class="bcol-h">${l}</div>`);
  html += '</div>';
  for (let r = 0; r < 5; r++) {
    html += '<div class="brow">';
    for (let c = 0; c < 5; c++) {
      const cell = cardData[r] ? cardData[r][c] : null;
      if (cell === 'FREE' || cell === null) {
        html += '<div class="bcell free">FREE</div>';
      } else if (drawnNumbersSet.has(Number(cell))) {
        html += `<div class="bcell hit">${cell}</div>`;
      } else {
        html += `<div class="bcell">${cell}</div>`;
      }
    }
    html += '</div>';
  }
  html += '</div>';
  return html;
}

// ***** FIXED showWinner: clear card grid before next game to prevent flicker *****
function showWinner(gameState) {
  // Show the final ball that was called
  const drawn = gameState.drawn_balls || [];
  const finalBall = drawn[drawn.length - 1];
  const finalBallDiv = document.getElementById('finalBall');
  if (finalBallDiv && finalBall) {
    finalBallDiv.innerHTML = `
      <div style="text-align: center; margin-bottom: 20px;">
        <div style="font-size: 14px; color: var(--sub); margin-bottom: 10px;">🎯 ${T('lastCalled')}</div>
        <div style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 15px 30px; border-radius: 10px; font-size: 28px; font-weight: bold; color: white;">
          ${finalBall}
        </div>
      </div>
    `;
  }

  const winnerDiv = document.getElementById('winnerCards');
  if (winnerDiv) {
    const details = gameState.winner_details || [];
    if (details.length) {
      const prizePool = gameState.total_winners_prize || Math.floor((gameState.prize_pool || 0) * 0.8);
      const prizePerWinner = prizePool / details.length;
      winnerDiv.innerHTML = `
        <div style="text-align: center; margin-bottom: 15px; font-size: 24px; font-weight: bold; color: #4CAF50;">
          🎉 ${T('bingo')} 🎉
        </div>
        ${details.map(w => `
          <div style="background:rgba(255,215,0,0.2);margin:6px;padding:8px;border-radius:8px;">
            🏆 ${w.username || T('player')} - ${T('cardLabel')} #${w.card_number} +${prizePerWinner.toFixed(2)} ETB
          </div>
        `).join('')}
      `;
    } else {
      winnerDiv.innerHTML = `<div style="color:var(--sub);text-align:center;padding:10px">${T('noWinner')}</div>`;
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
      
      // 🧹 CLEAR OLD CARD GRID IMMEDIATELY (prevents flicker)
      state.myCards = [];
      state.myCardData = [];
      state.takenCards = [];
      const grid = document.getElementById('selGrid');
      if (grid) grid.innerHTML = '';
      const myCardCountEl = document.getElementById('myCardCount');
      if (myCardCountEl) myCardCountEl.innerText = '0/4';
      const finalBallEl = document.getElementById('finalBall');
      if (finalBallEl) finalBallEl.innerHTML = '';
      
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
  if (!proof) { alert(T('alertPasteProof')); return; }
  const res = await apiCall('/api/deposit', 'POST', {
    user_id: state.user.user_id,
    amount,
    platform: selectedPlatform,
    proof
  });
  if (!res) alert(T('networkError'));
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
  if (isNaN(amount) || amount < 50) { alert(T('minWithdrawal')); return; }
  if (!account) { alert(T('enterAccount')); return; }
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
    alert('❌ ' + (res?.error || T('requestFailed')));
  }
}

async function submitInquiry() {
  const subject = document.getElementById('inqSubject').value.trim();
  const message = document.getElementById('inqMessage').value.trim();
  if (!subject || !message) { alert(T('fillSubjectMessage')); return; }
  const res = await apiCall('/api/inquiry', 'POST', { user_id: state.user.user_id, subject, message });
  if (res && res.success) {
    alert(T('inquirySuccess'));
    document.getElementById('inqSubject').value = '';
    document.getElementById('inqMessage').value = '';
    goPage('pg-help');
  } else {
    alert('❌ ' + T('failedSend'));
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
      container.innerHTML = `<div style="text-align:center;color:var(--sub);padding:10px">${T('noPlayers')}</div>`;
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
    container.innerHTML = `<div style="text-align:center;color:var(--sub);padding:10px">${T('noGames')}</div>`;
    return;
  }

  // Get owner cut from settings (cached)
  let ownerCut = 20; // default
  try {
    const cutResp = await apiCall('/api/settings/owner_cut_percent');
    if (cutResp && cutResp.value) ownerCut = parseInt(cutResp.value) || 20;
  } catch(e) {}

  // Only show last 3 games (the API returns latest first)
  const games = res.slice(0, 3);

  container.innerHTML = games.map(g => {
    let info = `Game #${g.id}`;
    if (g.cancelled) {
      info += ' ❌ Cancelled';
    } else if (g.status === 'finished') {
      const winners = g.winner_card_numbers || [];
      if (winners.length) {
        const prizePool = g.prize_pool || 0;
        const winnersPrize = prizePool * (100 - ownerCut) / 100;
        const perWinner = winnersPrize / winners.length;
        const winnerCards = winners.join(', #');
        info += ` | 🏆 Winner: Card #${winnerCards} | +${perWinner.toFixed(2)} ETB`;
      } else {
        info += ' | No winner';
      }
    } else {
      info += ` | ${g.status}`;
    }
    return `<div style="border-bottom:1px solid rgba(255,255,255,0.1);padding:8px">${info}</div>`;
  }).join('');
}

// ---------- Visibility change listener (resync when returning to page) ----------
document.addEventListener('visibilitychange', async () => {
  if (!document.hidden && state.gameId && state.user) {
    console.log('Page became visible – refreshing game state...');
    const requestedGameId = state.gameId;
    const res = await apiCall(`/api/game_state/${requestedGameId}?user_id=${state.user.user_id}`);
    if (state.gameId !== requestedGameId) return; // game moved on while this was in flight — discard
    if (res && !res.error) {
      if (res.status === 'running' && !document.getElementById('pg-game').classList.contains('active')) {
        goPage('pg-game');
        updateGameUI(res);
      } else if (res.status === 'waiting' && !document.getElementById('pg-select').classList.contains('active')) {
        goPage('pg-select');
        await refreshGameInfo();
        startCountdownPolling();
      } else if (res.status === 'finished' && !document.getElementById('pg-winner').classList.contains('active')) {
        showWinner(res);
      }
    }
  }
});

// ---------- Initialization ----------
window.addEventListener('DOMContentLoaded', async () => {
  // --- 0. Add refresh button to all pages ---
  const pageIds = ['pg-home', 'pg-register', 'pg-select', 'pg-game', 'pg-winner', 'pg-deposit', 'pg-withdraw', 'pg-leaderboard', 'pg-settings'];
  pageIds.forEach(pageId => {
    const page = document.getElementById(pageId);
    if (page) {
      // Add refresh button if it doesn't exist
      if (!page.querySelector('.refresh-btn')) {
        const refreshBtn = document.createElement('button');
        refreshBtn.className = 'refresh-btn';
        refreshBtn.innerHTML = '🔄';
        refreshBtn.title = 'Refresh';
        refreshBtn.style.cssText = 'position: absolute; top: 8px; right: 8px; width: 40px; height: 40px; border-radius: 50%; background: #007bff; color: white; border: none; font-size: 18px; cursor: pointer; z-index: 999;';
        refreshBtn.onclick = refreshPage;
        page.style.position = 'relative'; // ensure position context
        page.appendChild(refreshBtn);
      }
    }
  });

  // --- 1. Show home screen immediately ---
  // Ensure the home screen is active (it should already have class "active" from HTML)
  // If not, activate it now.
  const homeScreen = document.getElementById('pg-home');
  if (homeScreen) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    homeScreen.classList.add('active');
  }

  // --- 2. Build UI elements that don't depend on user data ---
  buildStakeGrid();
  buildDepositAmountGrid();
  await loadPlatformNumbers();
  await loadStakes();
  buildStakeGrid();

  // --- 3. Load user data in the background and update UI ---
  await loadUser();
  renderUI();
  displayReferralInfo();
  loadLeaderboard();
  loadRecentGames();
  loadLatestNotification();

  // If user is not logged in (e.g., needs registration), the loadUser function will navigate to pg-register.
  // No need to call goPage again.
});
