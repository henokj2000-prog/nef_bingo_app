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
  myCardData: [],
  takenCards: []
};

let pollInterval = null;
let countdownInterval = null;

// ── Translations (from your table) ───────────────────
const LANG = {
  en: {
    balance: "Your Balance",
    deposit: "Deposit",
    withdraw: "Withdraw",
    playNow: "🎮 PLAY NOW",
    recentGames: "Recent Games",
    noGames: "No games yet",
    back: "← Back",
    home: "🏠 Home",
    selectStake: "Select Stake",
    prizePool: "Prize Pool",
    players: "Players",
    stakeLabel: "Stake",
    gameStartsIn: "Game starts in",
    seconds: "seconds",
    yourCards: "Your cards",
    yours: "🟡 Yours",
    taken: "🔴 Taken",
    available: "⬜ Available",
    called: "Called",
    recent: "Recent",
    bingo: "BINGO!",
    winnerAnnounce: "BINGO! Winner!",
    nextGame: "Next game",
    balanceUpdated: "✅ Balance updated",
    selectAmount: "Select Amount",
    orCustom: "Or custom amount",
    selectPlatform: "Select Platform",
    paymentInstructions: "Payment Instructions",
    sendExactly: "Send exactly",
    number: "Number",
    reference: "Reference",
    uploadProof: "Upload Proof",
    submit: "Submit",
    withdrawTitle: "Withdraw",
    availableBalance: "Available Balance",
    accountNumber: "Account Number",
    requestWithdrawal: "Request Withdrawal",
    howToPlay: "How to Play",
    step1: "Deposit via Telebirr or CBE. Confirmed by admin within 30 min.",
    step2: "Choose 10, 20, 50 or 100 ETB. Higher stake = bigger prize!",
    step3: "Select up to 4 cards from 1-200. 🟡=yours, 🔴=taken. Game starts after 30 sec.",
    step4: "Numbers called every 4 seconds. Your card updates live with ⭐.",
    step5: "Complete a row, column or diagonal to win! Prize split if multiple winners.",
    step6: "Request withdrawal to Telebirr or CBE. Processed within 24 hours.",
    help: "Help",
    sendInquiry: "Send Inquiry",
    messageAdmin: "Message the admin directly",
    faq: "FAQ",
    faq1: "How long does deposit take?",
    faq1a: "Usually 5-30 minutes after proof submitted.",
    faq2: "Withdrawal time?",
    faq2a: "Within 24 hours on business days.",
    faq3: "What if game cancels?",
    faq3a: "Full refund automatically credited.",
    inquiryTitle: "Send Inquiry",
    subject: "Subject",
    message: "Message",
    send: "Send",
    insufficient: "Insufficient balance!",
    cardTaken: "Card already taken",
    maxCards: "Maximum 4 cards per game",
    gameCancelled: "Game cancelled due to insufficient players. Your balance has been refunded. Please try again.",
    depositSuccess: "✅ {amount} ETB credited!",
    depositPending: "⏳ Deposit submitted for admin review.",
    withdrawSuccess: "✅ Withdrawal requested. Processed within 24h.",
    inquirySuccess: "✅ Inquiry sent. Admin will respond soon.",
    registerWelcome: "Welcome! Please complete your registration to play",
    phoneLabel: "Phone Number",
    languageLabel: "Language",
    startPlaying: "Start Playing",
    saveSettings: "Save Changes"
  },
  am: {
    balance: "ሂሳቦ",
    deposit: "ገንዘብ ያስገቡ",
    withdraw: "ገንዘብ ያውጡ",
    playNow: "🎮 አሁን ይጫወቱ",
    recentGames: "የቅርብ ጊዜ ጨዋታዎች",
    noGames: "ገና ምንም ጨዋታ የለም",
    back: "← ተመለስ",
    home: "🏠 መነሻ",
    selectStake: "መወራረጃ ይምረጡ",
    prizePool: "የሽልማት ገንዳ",
    players: "ተጫዋቾች",
    stakeLabel: "መወራረጃ",
    gameStartsIn: "ጨዋታው የሚጀምረው በ",
    seconds: "ሰከንዶች",
    yourCards: "ካርዶችዎ",
    yours: "🟡 የእርስዎ",
    taken: "🔴 የተወሰደ",
    available: "⬜ የሚገኝ",
    called: "የተጠራ",
    recent: "የቅርብ ጊዜ",
    bingo: "ቢንጎ!",
    winnerAnnounce: "የቢንጎ አሸናፊውን ያስታውቁ!",
    nextGame: "የሚቀጥለው ጨዋታ",
    balanceUpdated: "✅ ሂሳብ ተዘምኗል",
    selectAmount: "መጠኑን ይምረጡ",
    orCustom: "ወይም ብጁ መጠን",
    selectPlatform: "መድረክ ይምረጡ",
    paymentInstructions: "የክፍያ መመሪያዎች",
    sendExactly: "በትክክል ይላኩ",
    number: "ቁጥር",
    reference: "ማጣቀሻ",
    uploadProof: "ማስረጃ ይስቀሉ",
    submit: "ያስገቡ",
    withdrawTitle: "ማውጣት",
    availableBalance: "ያለዎት ቀሪ ሂሳብ",
    accountNumber: "የመለያ ቁጥር",
    requestWithdrawal: "ገንዘብ ማውጣት ይጠይቁ",
    howToPlay: "እንዴት እንደሚጫወቱ",
    step1: "በቴሌብር ወይም በንግድ ባንክ (CBE) ተቀማጭ ያድርጉ። በአስተዳዳሪ በ30 ደቂቃ ውስጥ ይረጋገጣል።",
    step2: "10, 20, 50 ወይም 100 ETB ይምረጡ። ከፍ ያለ መወራረጃ = ትልቅ ሽልማት!",
    step3: "ከ 1-200 እስከ 4 ካርዶችን ይምረጡ። 🟡=የእርስዎ፣ 🔴=የተወሰደ። ጨዋታው ከ 30 ሰከንድ በኋላ ይጀምራል።",
    step4: "ቁጥሮች በየ 4 ሰከንድ ይጠራሉ ። ካርድዎ በ ⭐ ይዘመናል።",
    step5: "ለማሸነፍ ረድፍ፣ አምድ ወይም ሰያፍ ያጠናቅቁ! ብዙ አሸናፊዎች ካሉ ሽልማቱ ይከፈላል።",
    step6: "በቴሌብር ወይም በንግድ ባንክ (CBE) ገንዘብ ማውጣት ይጠይቁ። በ 24 ሰዓት ውስጥ ይከናወናል።",
    help: "እገዛ",
    sendInquiry: "ጥያቄ ይላኩ",
    messageAdmin: "አስተዳዳሪውን በቀጥታ ያነጋግሩ",
    faq: "ተደጋግመው የሚጠየቁ ጥያቄዎች (FAQ)",
    faq1: "ተቀማጭ ለማድረግ ምን ያህል ጊዜ ይወስዳል?",
    faq1a: "ብዙውን ጊዜ ማስረጃ ከቀረበ በኋላ ከ 5-30 ደቂቃዎች ውስጥ።",
    faq2: "ገንዘብ ማውጣት ምን ያህል ጊዜ ይወስዳል?",
    faq2a: "በሥራ ቀናት በ 24 ሰዓት ውስጥ።",
    faq3: "ጨዋታው ቢሰረዝ ምን ይደረጋል?",
    faq3a: "ሙሉ ክፍያ በራስ-ሰር ይመለሳል።",
    inquiryTitle: "ጥያቄ ይላኩ",
    subject: "ርዕሰ ጉዳይ",
    message: "መልእክት",
    send: "ይላኩ",
    insufficient: "በቂ ሂሳብ የለም!",
    cardTaken: "ካርዱ ቀድሞውኑ ተወስዷል",
    maxCards: "በአንድ ጨዋታ ቢበዛ 4 ካርዶች",
    gameCancelled: "በቂ ተጫዋቾች ባለመኖሩ ጨዋታው ተሰርዟል። ሂሳብዎ ተመላሽ ተደርጓል። እባክዎ እንደገና ይሞክሩ።",
    depositSuccess: "✅ {amount} ETB ገብቷል!",
    depositPending: "⏳ ተቀማጭ ለአስተዳዳሪ ግምገማ ቀርቧል።",
    withdrawSuccess: "✅ ገንዘብ ለማውጣት ጠይቀዋል። በ 24 ሰዓት ውስጥ ይከናወናል።",
    inquirySuccess: "✅ ጥያቄ ተልኳል። አስተዳዳሪው በቅርቡ ምላሽ ይሰጣል።",
    registerWelcome: "እንኳን ደህና መጡ! ለመጫወት እባክዎ ይመዝገቡ",
    phoneLabel: "ስልክ ቁጥር",
    languageLabel: "ቋንቋ",
    startPlaying: "መጫወት ጀምር",
    saveSettings: "ለውጦችን አስቀምጥ"
  },
  om: {
    balance: "Maallaqa Qabdan",
    deposit: "Maallaqa Galchuu",
    withdraw: "Maallaqa Baasuu",
    playNow: "🎮 AMMA TAPHADHU",
    recentGames: "Taphoota dhihoo",
    noGames: "Hanga ammaaf taphi tokkollee hin jiru",
    back: "← Deebi'i",
    home: "🏠 Mana",
    selectStake: "Gatii filadhu",
    prizePool: "Qabeenya badhaasaa",
    players: "Taphattoota",
    stakeLabel: "Gatii",
    gameStartsIn: "Taphi kan jalqabu",
    seconds: "sekondii",
    yourCards: "Kaardii kee",
    yours: "🟡 Kan kee",
    taken: "🔴 Kan fudhatame",
    available: "⬜ Kan jiru",
    called: "Kan waamame",
    recent: "Dhihoo",
    bingo: "BINGO!",
    winnerAnnounce: "Mo'ataa BINGO beeksisii!",
    nextGame: "Taphi itti aanu",
    balanceUpdated: "✅ Haqqiin kee haaromfameera",
    selectAmount: "Gatii filadhu",
    orCustom: "ykn gatii mataa keetii",
    selectPlatform: "Plaatfoormii filadhu",
    paymentInstructions: "Qajeelfama kaffaltii",
    sendExactly: "Sirriitti ergi",
    number: "Lakkofsa",
    reference: "Wabii",
    uploadProof: "Ragaa ergi",
    submit: "Ergi",
    withdrawTitle: "Baasii",
    availableBalance: "Haqqii jiru",
    accountNumber: "Lakkofsa herregaa",
    requestWithdrawal: "Baasii gaafadhu",
    howToPlay: "Akkam taphachuu qabda",
    step1: "Telebirr ykn CBE fayyadamuun galchi. Adminin daqiiqaa 30 keessatti mirkaneessa.",
    step2: "10, 20, 50 ykn 100 ETB filadhu. Gatiin guddaan = badhaasa guddaa!",
    step3: "Kaardii 4 hanga 1-200 filadhu. 🟡=kan kee, 🔴=kan fudhatame. Taphi sekondii 30 booda jalqaba.",
    step4: "Lakkofsi sekondii 4 hunda waamama. Kaardiin kee ⭐ waliin haaromfama.",
    step5: "Riqicha, utubaa ykn diagonal guuti! Yoo mo'attoonni baay'atan badhaasichi hirama.",
    step6: "Telebirr ykn CBE fayyadamuun baasii gaafadhu. Sa'aatii 24 keessatti raawwatama.",
    help: "Gargaarsa",
    sendInquiry: "Gaaffii ergi",
    messageAdmin: "Admin kallattiin haasofsiisi",
    faq: "Gaaffiiwwan yeroo baay'ee gaafataman",
    faq1: "Kaffaltii galchuun yeroo hammam fudhata?",
    faq1a: "Yeroo baay'ee ragaan ergamee daqiiqaa 5-30 booda.",
    faq2: "Yeroo baasii?",
    faq2a: "Guyyoota hojii keessatti sa'aatii 24 keessatti.",
    faq3: "Yoo taphi haqamehoo?",
    faq3a: "Kaffaltiin guutuu ofumaan deebi'a.",
    inquiryTitle: "Gaaffii ergi",
    subject: "Mata duree",
    message: "Ergaa",
    send: "Ergi",
    insufficient: "Haqqiin gahaa miti!",
    cardTaken: "Kaardiin fudhatameera",
    maxCards: "Tapha tokkotti kaardii 4 qofa",
    gameCancelled: "Taphi taphattoota gahaa dhabuun haqameera. Haqqiin kee deebi'eera. Maaloo irra deebi'ii yaali.",
    depositSuccess: "✅ {amount} ETB galameera!",
    depositPending: "⏳ Kaffaltiin qorannoo adminiif ergameera.",
    withdrawSuccess: "✅ Baasii gaafatteerta. Sa'aatii 24 keessatti raawwatama.",
    inquirySuccess: "✅ Gaaffiin ergameera. Adminiinis dafee deebisa.",
    registerWelcome: "Baga nagaan dhufte! Mee galmaan ba'i taphaaf",
    phoneLabel: "Lakkoofsa Bilbilaa",
    languageLabel: "Afaan",
    startPlaying: "Tapha eega",
    saveSettings: "Jijjiiramni kun eegamu"
  },
  ti: {
    balance: "ሂሳብካ",
    deposit: "Maallaqa Galchuu",
    withdraw: "Maallaqa Baasuu",
    playNow: "🎮 ሕጂ ተጻወት",
    recentGames: "ናይ ቀረባ ግዜ ጸወታታት",
    noGames: "ክሳብ ሕጂ ዝኾነ ጸወታ የለን",
    back: "← ተመለስ",
    home: "🏠 መበገሲ",
    selectStake: "መወራረዲ ምረጽ",
    prizePool: "ናይ ሽልማት ዋንጫ",
    players: "ተጻወቲ",
    stakeLabel: "መወራረዲ",
    gameStartsIn: "ጸወታ ዝጅምረሉ",
    seconds: "ሰከንዶች",
    yourCards: "ካርድካ",
    yours: "🟡 ናትካ",
    taken: "🔴 ዝተወሰደ",
    available: "⬜ ዘሎ",
    called: "ዝተጸውዐ",
    recent: "ናይ ቀረባ ግዜ",
    bingo: "ቢንጎ!",
    winnerAnnounce: "ናይ ቢንጎ ተዓዋቲ ኣፍልጥ!",
    nextGame: "ቀጻሊ ጸወታ",
    balanceUpdated: "✅ ሂሳብካ ተሓዲሱ እዩ",
    selectAmount: "መጠን ምረጽ",
    orCustom: "ወይ ናይ ባዕልኻ መጠን",
    selectPlatform: "መድረኽ ምረጽ",
    paymentInstructions: "ናይ ክፍሊት መምርሒታት",
    sendExactly: "ልክ ኣድልካ ስደድ",
    number: "ቑጽሪ",
    reference: "መወከሲ",
    uploadProof: "መሰረዲ ስቀል",
    submit: "ስደድ",
    withdrawTitle: "ምውጻእ",
    availableBalance: "ዘሎ ሂሳብ",
    accountNumber: "ቑጽሪ ሂሳብ",
    requestWithdrawal: "ምውጻእ ገንዘብ ሕተት",
    howToPlay: "ከመይ ጌርካ ትጻወት",
    step1: "ብቴሌብር ወይ ንግዲ ባንኪ (CBE) ተቀማጭ ግበር። ብኣድሚን ኣብ ውሽጢ 30 ደቓይቕ ይረጋገጽ።",
    step2: "10, 20, 50 ወይ 100 ETB ምረጽ። ዝለዓለ መወራረዲ = ዓቢ ሽልማት!",
    step3: "ካብ 1-200 ክሳብ 4 ካርድ ምረጽ። 🟡=ናትካ፣ 🔴=ዝተወሰደ። ጸወታ ድሕሪ 30 ሰከንድ ይጅምር።",
    step4: "ቑጽርታት ኣብ ነፍሲ ወከፍ 4 ሰከንድ ይጽውዑ። ካርድካ ብ ⭐ ይሕደስ።",
    step5: "ንኽትዕወት ረድፊ፣ ዓንዲ ወይ ዲያጎናል ምላእ! ብዙሓት ተዓወትቲ እንተለዉ ሽልማት ይኽፈል/ይካፈል።",
    step6: "ብቴሌብር ወይ ንግዲ ባንኪ (CBE) ምውጻእ ገንዘብ ሕተት። ኣብ ውሽጢ 24 ሰዓት ይፍጸም።",
    help: "ሓገዝ",
    sendInquiry: "ሕቶ ስደድ",
    messageAdmin: "ኣድሚን ብቐጥታ ኣዘራርብ",
    faq: "ተደጋጋሚ ሕቶታት (FAQ)",
    faq1: "ተቀማጭ ንምግባር ክንደይ ግዜ ይወስድ?",
    faq1a: "መብዛሕት ግዜ መሰረዲ ድሕሪ ምቕራብ ካብ 5-30 ደቓይቕ።",
    faq2: "ናይ ምውጻእ ግዜ?",
    faq2a: "ኣብ ናይ ስራሕ መዓልታት ኣብ ውሽጢ 24 ሰዓት።",
    faq3: "ጸወታ እንተተሰሪዙ እንታይ ይኸውን?",
    faq3a: "ምሉእ ክፍሊት ብኣውቶማቲክ ይምለስ።",
    inquiryTitle: "ሕቶ ስደድ",
    subject: "ኣርእስቲ",
    message: "መልእኽቲ",
    send: "ስደድ",
    insufficient: "እኹል ሂሳብ የለን!",
    cardTaken: "ካርድ ተወሲዱ እዩ",
    maxCards: "ኣብ ሓደ ጸወታ ልዕሊ 4 ካርድ ኣይፍቀድን",
    gameCancelled: "እኹል ተጻወትቲ ብዘይምህላዎም ጸወታ ተሰሪዙ እዩ። ሂሳብካ ተመሊሱልካ እዩ። በጃኻ እንደገና ፈትን።",
    depositSuccess: "✅ {amount} ETB ኣትዩ!",
    depositPending: "⏳ ተቀማጭ ንምርመራ ኣድሚን ቀሪቡ።",
    withdrawSuccess: "✅ ምውጻእ ገንዘብ ሕቲትካ። ኣብ ውሽጢ 24 ሰዓት ይፍጸም።",
    inquirySuccess: "✅ ሕቶ ተሰዲዱ። ኣድሚን ኣብ ቀረባ ግዜ መልሲ ይህብ።",
    registerWelcome: "እንኳዕ ብደሓን መጻእኩም! ንምጽዋት በጃኹም ተመዝገቡ",
    phoneLabel: "ቁጽሪ ተሌፎን",
    languageLabel: "ቋንቋ",
    startPlaying: "ምጽዋት ጀምሩ",
    saveSettings: "ለውጥታት ዕቅቡ"
  }
};

function T(key, vars = {}) {
  let text = (LANG[state.lang] && LANG[state.lang][key]) || (LANG.en && LANG.en[key]) || key;
  for (let [k, v] of Object.entries(vars)) text = text.replace(`{${k}}`, v);
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
  // Registration screen
  const regWelcome = document.querySelector('#pg-register .balance-label');
  if (regWelcome) regWelcome.innerText = T('registerWelcome');
  const phoneLabel = document.querySelector('#pg-register .card-title:first-child');
  if (phoneLabel) phoneLabel.innerText = T('phoneLabel');
  const langLabel = document.querySelector('#pg-register .card-title:last-child');
  if (langLabel) langLabel.innerText = T('languageLabel');
  const startBtn = document.querySelector('#pg-register .submit-btn');
  if (startBtn) startBtn.innerText = T('startPlaying');

  // Settings screen
  const settingsPhoneLabel = document.querySelector('#pg-settings .card-title:first-child');
  if (settingsPhoneLabel) settingsPhoneLabel.innerText = T('phoneLabel');
  const settingsLangLabel = document.querySelector('#pg-settings .card-title:last-child');
  if (settingsLangLabel) settingsLangLabel.innerText = T('languageLabel');
  const saveBtn = document.querySelector('#pg-settings .submit-btn');
  if (saveBtn) saveBtn.innerText = T('saveSettings');

  // Home screen
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
  const order = ['en', 'am', 'om', 'ti'];
  let idx = order.indexOf(state.lang);
  idx = (idx + 1) % order.length;
  state.lang = order[idx];
  updateUILanguage();
  apiCall('/api/update_profile', 'POST', { user_id: state.user.user_id, language: state.lang });
}

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

// -------------------- Game Functions --------------------
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
  startGamePolling();
}

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

function startGamePolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    if (!state.gameId) return;
    const res = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
    if (!res || res.error) return;
    if (res.status === 'waiting') {
      const displayPrize = res.winners_share || Math.floor((res.prize_pool || 0) * 0.8);
      document.getElementById('sel-prize').innerText = displayPrize + ' ETB';
      document.getElementById('sel-players').innerText = res.players;
      if (JSON.stringify(state.takenCards) !== JSON.stringify(res.taken_cards)) {
        state.takenCards = res.taken_cards;
        buildCardGrid(state.takenCards);
      }
    } else if (res.status === 'running') {
      if (countdownInterval) clearInterval(countdownInterval);
      countdownInterval = null;
      updateGameUI(res);
      if (document.getElementById('pg-select')?.classList.contains('active')) {
        goPage('pg-game');
      }
    } else if (res.status === 'cancelled') {
      clearInterval(pollInterval);
      pollInterval = null;
      alert(res.cancelled_message || T('gameCancelled'));
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

async function renderMyCards(drawnBalls) {
  await loadMyCards();
  const wrap = document.getElementById('bingoCardsWrap');
  if (!wrap) return;
  if (!state.myCardData.length) {
    wrap.innerHTML = '<div style="text-align:center;color:var(--sub);padding:20px">No cards selected</div>';
    return;
  }
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
  loadUser().then(() => renderUI());
  let seconds = 5;
  const nextNum = document.getElementById('nextNum');
  if (nextNum) nextNum.innerText = seconds;
  const timer = setInterval(() => {
    seconds--;
    if (nextNum) nextNum.innerText = Math.max(0, seconds);
    if (seconds <= 0) {
      clearInterval(timer);
      if (gameState.next_game_id) {
        state.gameId = gameState.next_game_id;
        state.myCards = [];
        state.myCardData = [];
        startGamePolling();
        goPage('pg-select');
        refreshGameInfo();
        startCountdown(30);
      } else {
        state.gameId = null;
        goPage('pg-stake');
      }
    }
  }, 1000);
}

// Deposit / Withdraw / Inquiry functions (keep your existing working ones)
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
      alert(T('depositSuccess', { amount }));
    } else {
      alert(T('depositPending'));
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
    alert(T('withdrawSuccess'));
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
        setTimeout(() => { banner.style.display = 'none'; }, 10000);
      }
    }
  } catch(e) { console.error(e); }
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
