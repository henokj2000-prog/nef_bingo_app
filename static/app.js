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

// Translations (final)
const LANG = {
  en: {
    // Registration
    registerWelcome: "Welcome!",
    registerSub: "Please complete your registration to play",
    phoneLabel: "📞 Phone Number",
    languageLabel: "🌐 Language",
    startPlaying: "Start Playing",
    saveSettings: "Save Changes",
    // Home
    balance: "Your Balance",
    deposit: "Deposit",
    withdraw: "Withdraw",
    playNow: "🎮 PLAY NOW",
    recentGames: "Recent Games",
    noGames: "No games yet",
    // Stake
    selectStake: "Select Stake",
    back: "Back",
    // Card selection
    prizePool: "Prize Pool",
    players: "Players",
    stakeLabel: "Stake",
    gameStartsIn: "Game starts in",
    sec: "sec",
    yourCards: "Your cards",
    yours: "🟡 Yours",
    taken: "🔴 Taken",
    available: "⬜ Available",
    home: "Home",
    // Game
    called: "Called",
    recent: "Recent",
    // Winner
    bingo: "BINGO!",
    winnerAnnounce: "BINGO! Winner!",
    nextGame: "Next game",
    seconds: "seconds",
    balanceUpdated: "✅ Balance updated",
    // Deposit
    selectAmount: "Select Amount",
    orCustom: "Or custom amount",
    selectPlatform: "Select Platform",
    paymentInstructions: "Payment Instructions",
    sendExactly: "Send exactly",
    number: "Number",
    reference: "Reference",
    uploadProof: "Upload Proof",
    submit: "Submit",
    // Withdraw
    withdrawTitle: "Withdraw",
    availableBalance: "Available Balance",
    accountNumber: "Account Number",
    requestWithdrawal: "Request Withdrawal",
    // How to play
    howToPlay: "How to Play",
    step1: "Deposit via Telebirr or CBE. Confirmed by admin within 30 min.",
    step2: "Choose 10, 20, 50 or 100 ETB. Higher stake = bigger prize!",
    step3: "Select up to 4 cards from 1-200. 🟡=yours, 🔴=taken. Game starts after 30 sec.",
    step4: "Numbers called every 4 seconds. Your card updates live with ⭐.",
    step5: "Complete a row, column or diagonal to win! Prize split if multiple winners.",
    step6: "Request withdrawal to Telebirr or CBE. Processed within 24 hours.",
    // Help
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
    // Inquiry
    inquiryTitle: "Send Inquiry",
    subject: "Subject",
    message: "Message",
    send: "Send",
    // Errors & messages
    insufficient: "Insufficient balance!",
    cardTaken: "Card already taken",
    maxCards: "Maximum 4 cards per game",
    gameCancelled: "Game cancelled due to insufficient players. Your balance has been refunded. Please try again.",
    depositSuccess: "✅ {amount} ETB credited!",
    depositPending: "⏳ Deposit submitted for admin review.",
    withdrawSuccess: "✅ Withdrawal requested. Processed within 24h.",
    inquirySuccess: "✅ Inquiry sent. Admin will respond soon."
  },
  am: {
    registerWelcome: "እንኳን ደህና መጡ!",
    registerSub: "ለመጫወት እባክዎ ምዝገባዎን ያጠናቅቁ",
    phoneLabel: "📞 ስልክ ቁጥርዎን ያስገቡ",
    languageLabel: "ቋንቋ ይምረጡ",
    startPlaying: "መጫወት ጀምር",
    saveSettings: "ለውጦችን አስቀምጥ",
    balance: "የእርስዎ ሂሳብ",
    deposit: "ገንዘብ ያስገቡ",
    withdraw: "ገንዘብ ያውጡ",
    playNow: "🎮 አሁን ይጫወቱ",
    recentGames: "የቅርብ ጊዜ ጨዋታዎች",
    noGames: "ገና ምንም ጨዋታ የለም",
    selectStake: "መወራረጃ ይምረጡ",
    back: "ተመለስ",
    prizePool: "ሽልማት",
    players: "ተጫዋቾች",
    stakeLabel: "መወራረጃ",
    gameStartsIn: "ጨዋታው የሚጀምረው በ",
    sec: "ሰከንዶች",
    yourCards: "ካርዶችዎ",
    yours: "🟡 የእርስዎ",
    taken: "🔴 የተወሰደ",
    available: "⬜ የሚገኝ",
    home: "መነሻ",
    called: "የተጠራ",
    recent: "የቅርብ",
    bingo: "ቢንጎ!",
    winnerAnnounce: "የቢንጎ አሸናፊ ተገኝቷል!",
    nextGame: "ቀጣይ ጨዋታ",
    seconds: "ሰከንዶች",
    balanceUpdated: "ሂሳብ ተዘምኗል",
    selectAmount: "መጠን ይምረጡ",
    orCustom: "ወይም ብጁ መጠን",
    selectPlatform: "መድረክ ይምረጡ",
    paymentInstructions: "የክፍያ መመሪያ",
    sendExactly: "በትክክል ይላኩ",
    number: "ቁጥር",
    reference: "ማጣቀሻ",
    uploadProof: "ማስረጃ ይስቀሉ",
    submit: "አስገባ",
    withdrawTitle: "ማውጣት",
    availableBalance: "ያለዎት ቀሪ ሂሳብ",
    accountNumber: "የመለያ ቁጥር",
    requestWithdrawal: "ማውጣት ይጠይቁ",
    howToPlay: "እንዴት እንደሚጫወቱ",
    step1: "በቴሌብር ወይም በንግድ ባንክ (CBE) ተቀማጭ ያድርጉ። በአስተዳዳሪ በ30 ደቂቃ ውስጥ ይረጋገጣል።",
    step2: "10, 20, 50 ወይም 100 ETB ይምረጡ። ከፍ ያለ መወራረጃ = ትልቅ ሽልማት!",
    step3: "ከ1-200 እስከ 4 ካርዶችን ይምረጡ። 🟡=የእርስዎ፣ 🔴=የተወሰደ። ጨዋታው ከ30 ሰከንድ በኋላ ይጀምራል።",
    step4: "ቁጥሮች በየ4 ሰከንድ ይጠራሉ። ካርድዎ በ⭐ ይዘመናል።",
    step5: "ረድፍ፣ አምድ ወይም ሰያፍ ያጠናቅቁ! ብዙ አሸናፊዎች ካሉ ሽልማቱ ይከፈላል።",
    step6: "በቴሌብር ወይም በንግድ ባንክ (CBE) ገንዘብ ማውጣት ይጠይቁ። በ24 ሰዓት ውስጥ ይከናወናል።",
    help: "እገዛ",
    sendInquiry: "ጥያቄ ላኩ",
    messageAdmin: "ለአስተዳዳሪ በቀጥታ ይጻፉ",
    faq: "ተደጋጋሚ ጥያቄዎች",
    faq1: "ተቀማጭ ገንዘብ ለማስገባት ምን ያህል ጊዜ ይወስዳል?",
    faq1a: "ብዙውን ጊዜ ማስረጃ ከቀረበ ከ5-30 ደቂቃዎች ውስጥ።",
    faq2: "ገንዘብ ማውጣት ምን ያህል ጊዜ ይወስዳል?",
    faq2a: "በሥራ ቀናት በ24 ሰዓት ውስጥ።",
    faq3: "ጨዋታው ቢሰረዝ ምን ይደረጋል?",
    faq3a: "ሙሉ ክፍያ በራስ-ሰር ይመለሳል።",
    inquiryTitle: "ጥያቄ ላኩ",
    subject: "ርዕስ",
    message: "መልእክት",
    send: "ላኩ",
    insufficient: "በቂ ሂሳብ የለም!",
    cardTaken: "ካርዱ ቀድሞውኑ ተወስዷል",
    maxCards: "በአንድ ጨዋታ ከ4 ካርዶች መጨመር አይቻልም",
    gameCancelled: "በቂ ተጫዋቾች ባለመኖሩ ጨዋታው ተሰርዟል። ገንዘብዎ ተመላሽ ተደርጓል። እባክዎ እንደገና ይሞክሩ።",
    depositSuccess: "✅ {amount} ETB ገብቷል!",
    depositPending: "⏳ ተቀማጭ ለአስተዳዳሪ ግምገማ ቀርቧል።",
    withdrawSuccess: "✅ ገንዘብ ለማውጣት ጠይቀዋል። በ24 ሰዓት ውስጥ ይከናወናል።",
    inquirySuccess: "✅ ጥያቄ ተልኳል። አስተዳዳሪው በቅርቡ ምላሽ ይሰጣል።"
  },
  om: {
    registerWelcome: "Baga nagaan dhufte!",
    registerSub: "Mee galmaan ba'i taphaaf",
    phoneLabel: "📞 Lakkoofsa Bilbilaa",
    languageLabel: "Afaan filadhu",
    startPlaying: "Tapha eega",
    saveSettings: "Jijjiiramni kun eegamu",
    balance: "Madaala Keessan",
    deposit: "Maallaqa Galchuu",
    withdraw: "Maallaqa Baasuu",
    playNow: "🎮 AMMA TAPHADHU",
    recentGames: "Taphoota dhihoo",
    noGames: "Hanga ammaaf taphi tokkollee hin jiru",
    selectStake: "Gatii filadhu",
    back: "Deebi'i",
    prizePool: "Badhaasaa",
    players: "Taphattoota",
    stakeLabel: "Gatii",
    gameStartsIn: "Taphi kan jalqabu",
    sec: "sekondii",
    yourCards: "Kaardii kee",
    yours: "🟡 Kan kee",
    taken: "🔴 Kan fudhatame",
    available: "⬜ Kan jiru",
    home: "Mana",
    called: "Kan waamame",
    recent: "Dhihoo",
    bingo: "BINGO!",
    winnerAnnounce: "Mo'ataa BINGO beeksisii!",
    nextGame: "Taphi itti aanu",
    seconds: "sekondii",
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
    inquirySuccess: "✅ Gaaffiin ergameera. Adminiinis dafee deebisa."
  },
  ti: {
    registerWelcome: "እንኳዕ ብደሓን መጻእኩም!",
    registerSub: "ንምጽዋት በጃኹም ተመዝገቡ",
    phoneLabel: "📞 ቁጽሪ ተሌፎን",
    languageLabel: "ቋንቋ ምረጹ",
    startPlaying: "ምጽዋት ጀምሩ",
    saveSettings: "ለውጥታት ዕቅቡ",
    balance: "ሂሳብካ",
    deposit: "ማስተናገድ",
    withdraw: "ምውጻእ",
    playNow: "🎮 ሕጂ ተጻወት",
    recentGames: "ናይ ቀረባ ግዜ ጸወታታት",
    noGames: "ክሳብ ሕጂ ዝኾነ ጸወታ የለን",
    selectStake: "መወራረዲ ምረጽ",
    back: "ተመለስ",
    prizePool: "ናይ ሽልማት",
    players: "ተጻወቲ",
    stakeLabel: "መወራረዲ",
    gameStartsIn: "ጸወታ ዝጅምረሉ",
    sec: "ሰከንድ",
    yourCards: "ካርድካ",
    yours: "🟡 ናትካ",
    taken: "🔴 ዝተወሰደ",
    available: "⬜ ዘሎ",
    home: "መበገሲ",
    called: "ዝተጸውዐ",
    recent: "ናይ ቀረባ ግዜ",
    bingo: "ቢንጎ!",
    winnerAnnounce: "ናይ ቢንጎ ተዓዋቲ ኣፍልጥ!",
    nextGame: "ቀጻሊ ጸወታ",
    seconds: "ሰከንዶች",
    balanceUpdated: "ሂሳብካ ተሓዲሱ እዩ",
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
    requestWithdrawal: "ምውጻእ ሕተት",
    howToPlay: "ከመይ ጌርካ ትጻወት",
    step1: "ብቴሌብር ወይ ንግዲ ባንኪ (CBE) ተቀማጭ ግበር። ብኣድሚን ኣብ ውሽጢ 30 ደቓይቕ ይረጋገጽ።",
    step2: "10, 20, 50 ወይ 100 ETB ምረጽ። ዝለዓለ መወራረዲ = ዓቢ ሽልማት!",
    step3: "ካብ 1-200 ክሳብ 4 ካርድ ምረጽ። 🟡=ናትካ፣ 🔴=ዝተወሰደ። ጸወታ ድሕሪ 30 ሰከንድ ይጅምር።",
    step4: "ቑጽርታት ኣብ ነፍሲ ወከፍ 4 ሰከንድ ይጽውዑ። ካርድካ ብ ⭐ ይሕደስ።",
    step5: "ረድፊ፣ ዓንዲ ወይ ዲያጎናል ምላእ! ብዙሓት ተዓወትቲ እንተለዉ ሽልማት ይኽፈል።",
    step6: "ብቴሌብር ወይ ንግዲ ባንኪ (CBE) ምውጻእ ገንዘብ ሕተት። ኣብ ውሽጢ 24 ሰዓት ይፍጸም።",
    help: "ሓገዝ",
    sendInquiry: "ሕቶ ስደድ",
    messageAdmin: "ኣድሚን ብቐጥታ ኣዘራርብ",
    faq: "ተደጋጋሚ ሕቶታት",
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
    withdrawSuccess: "✅ ምውጻእ ገንዘብ ሕቲትካ። ኣብ 24 ሰዓት ይፍጸም።",
    inquirySuccess: "✅ ሕቶ ተሰዲዱ። ኣድሚን ኣብ ቀረባ ግዜ መልሲ ይህብ።"
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
    if (state.user.language && LANG[state.user.language]) state.lang = state.user.language;
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
  // Registration (fixed bilingual HTML, but we still update dynamic elements)
  document.getElementById('regStartBtn') && (document.getElementById('regStartBtn').innerText = T('startPlaying'));
  // Settings
  document.getElementById('settingsPhoneLabel') && (document.getElementById('settingsPhoneLabel').innerText = T('phoneLabel'));
  document.getElementById('settingsLangLabel') && (document.getElementById('settingsLangLabel').innerText = T('languageLabel'));
  document.getElementById('settingsSaveBtn') && (document.getElementById('settingsSaveBtn').innerText = T('saveSettings'));
  // Home
  document.getElementById('balanceLabel') && (document.getElementById('balanceLabel').innerText = T('balance'));
  document.getElementById('depositBtnText') && (document.getElementById('depositBtnText').innerText = T('deposit'));
  document.getElementById('withdrawBtnText') && (document.getElementById('withdrawBtnText').innerText = T('withdraw'));
  document.getElementById('playBtn') && (document.getElementById('playBtn').innerText = T('playNow'));
  document.getElementById('recentTitle') && (document.getElementById('recentTitle').innerText = T('recentGames'));
  document.getElementById('statGamesLbl') && (document.getElementById('statGamesLbl').innerText = T('games'));
  document.getElementById('statWinsLbl') && (document.getElementById('statWinsLbl').innerText = T('wins'));
  document.getElementById('statWonLbl') && (document.getElementById('statWonLbl').innerText = T('won'));
  // Stake
  document.getElementById('stakeBackText') && (document.getElementById('stakeBackText').innerText = T('back'));
  document.getElementById('stakeTitle') && (document.getElementById('stakeTitle').innerText = T('selectStake'));
  // Card selection
  document.getElementById('selPrizeLbl') && (document.getElementById('selPrizeLbl').innerText = T('prizePool'));
  document.getElementById('selPlayersLbl') && (document.getElementById('selPlayersLbl').innerText = T('players'));
  document.getElementById('selStakeLbl') && (document.getElementById('selStakeLbl').innerText = T('stakeLabel'));
  document.getElementById('gameStartsLabel') && (document.getElementById('gameStartsLabel').innerText = T('gameStartsIn'));
  document.getElementById('secLabel') && (document.getElementById('secLabel').innerText = T('sec'));
  document.getElementById('yourCardsLabel') && (document.getElementById('yourCardsLabel').innerText = T('yourCards'));
  document.getElementById('cardLegend') && (document.getElementById('cardLegend').innerHTML = `${T('yours')} &nbsp;${T('taken')} &nbsp;${T('available')}`);
  document.getElementById('selectHomeBtn') && (document.getElementById('selectHomeBtn').innerText = T('home'));
  // Game
  document.getElementById('gamePrizeLbl') && (document.getElementById('gamePrizeLbl').innerText = T('prizePool'));
  document.getElementById('gamePlayersLbl') && (document.getElementById('gamePlayersLbl').innerText = T('players'));
  document.getElementById('gameCalledLbl') && (document.getElementById('gameCalledLbl').innerText = T('called'));
  document.getElementById('recentLabel') && (document.getElementById('recentLabel').innerText = T('recent'));
  document.getElementById('gameHomeBtn') && (document.getElementById('gameHomeBtn').innerText = T('home'));
  // Winner
  document.getElementById('winnerTitle') && (document.getElementById('winnerTitle').innerText = T('bingo'));
  document.getElementById('winnerSub') && (document.getElementById('winnerSub').innerText = T('winnerAnnounce'));
  document.getElementById('nextGameLabel') && (document.getElementById('nextGameLabel').innerText = T('nextGame'));
  document.getElementById('secondsLabel') && (document.getElementById('secondsLabel').innerText = T('seconds'));
  document.getElementById('balanceUpdatedMsg') && (document.getElementById('balanceUpdatedMsg').innerText = T('balanceUpdated'));
  document.getElementById('winnerHomeBtn') && (document.getElementById('winnerHomeBtn').innerText = T('home'));
  // Deposit
  document.getElementById('depBackText') && (document.getElementById('depBackText').innerText = T('back'));
  document.getElementById('depAmountTitle') && (document.getElementById('depAmountTitle').innerText = T('selectAmount'));
  document.getElementById('customAmountLabel') && (document.getElementById('customAmountLabel').innerText = T('orCustom'));
  document.getElementById('depPlatformTitle') && (document.getElementById('depPlatformTitle').innerText = T('selectPlatform'));
  // Deposit confirm
  document.getElementById('confBackText') && (document.getElementById('confBackText').innerText = T('back'));
  document.getElementById('paymentInstrTitle') && (document.getElementById('paymentInstrTitle').innerText = T('paymentInstructions'));
  document.getElementById('sendExactlyLabel') && (document.getElementById('sendExactlyLabel').innerText = T('sendExactly'));
  document.getElementById('numberLabel') && (document.getElementById('numberLabel').innerText = T('number'));
  document.getElementById('referenceLabel') && (document.getElementById('referenceLabel').innerText = T('reference'));
  document.getElementById('uploadProofTitle') && (document.getElementById('uploadProofTitle').innerText = T('uploadProof'));
  document.getElementById('submitDepositBtn') && (document.getElementById('submitDepositBtn').innerText = T('submit'));
  // Withdraw
  document.getElementById('wdBackText') && (document.getElementById('wdBackText').innerText = T('back'));
  document.getElementById('withdrawTitle') && (document.getElementById('withdrawTitle').innerText = T('withdrawTitle'));
  document.getElementById('availableBalanceLabel') && (document.getElementById('availableBalanceLabel').innerText = T('availableBalance'));
  document.getElementById('wdPlatformTitle') && (document.getElementById('wdPlatformTitle').innerText = T('selectPlatform'));
  document.getElementById('amountLabel') && (document.getElementById('amountLabel').innerText = T('amount'));
  document.getElementById('accountNumberLabel') && (document.getElementById('accountNumberLabel').innerText = T('accountNumber'));
  document.getElementById('requestWithdrawBtn') && (document.getElementById('requestWithdrawBtn').innerText = T('requestWithdrawal'));
  // How to play
  document.getElementById('howtoTitle') && (document.getElementById('howtoTitle').innerText = T('howToPlay'));
  const steps = [1,2,3,4,5,6];
  steps.forEach(i => {
    const el = document.getElementById(`step${i}Text`);
    if (el) el.innerHTML = `<b>${T(`step${i}`).split('<br>')[0]}</b><br>${T(`step${i}`).split('<br>')[1] || ''}`;
  });
  // Help
  document.getElementById('helpTitle') && (document.getElementById('helpTitle').innerText = T('help'));
  document.getElementById('sendInquiryLabel') && (document.getElementById('sendInquiryLabel').innerText = T('sendInquiry'));
  document.getElementById('messageAdminLabel') && (document.getElementById('messageAdminLabel').innerText = T('messageAdmin'));
  document.getElementById('howToPlayLabel') && (document.getElementById('howToPlayLabel').innerText = T('howToPlay'));
  document.getElementById('howToPlaySub') && (document.getElementById('howToPlaySub').innerText = T('howToPlay'));
  document.getElementById('faqTitle') && (document.getElementById('faqTitle').innerText = T('faq'));
  document.getElementById('faqContent') && (document.getElementById('faqContent').innerHTML = `<b>${T('faq1')}</b><br>${T('faq1a')}<br><br><b>${T('faq2')}</b><br>${T('faq2a')}<br><br><b>${T('faq3')}</b><br>${T('faq3a')}`);
  // Inquiry
  document.getElementById('inqBackText') && (document.getElementById('inqBackText').innerText = T('back'));
  document.getElementById('inquiryTitle') && (document.getElementById('inquiryTitle').innerText = T('inquiryTitle'));
  document.getElementById('subjectLabel') && (document.getElementById('subjectLabel').innerText = T('subject'));
  document.getElementById('messageLabel') && (document.getElementById('messageLabel').innerText = T('message'));
  document.getElementById('sendInquiryBtn') && (document.getElementById('sendInquiryBtn').innerText = T('send'));
  // Navbar
  document.getElementById('navHomeLabel') && (document.getElementById('navHomeLabel').innerText = T('home'));
  document.getElementById('navPlayLabel') && (document.getElementById('navPlayLabel').innerText = T('playNow').split(' ')[0]);
  document.getElementById('navDepositLabel') && (document.getElementById('navDepositLabel').innerText = T('deposit'));
  document.getElementById('navHowLabel') && (document.getElementById('navHowLabel').innerText = T('howToPlay').split(' ')[0]);
  document.getElementById('navHelpLabel') && (document.getElementById('navHelpLabel').innerText = T('help'));
}

function toggleLang() {
  const order = ['en', 'am', 'om', 'ti'];
  let idx = order.indexOf(state.lang);
  state.lang = order[(idx + 1) % order.length];
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

// Registration & Settings (same logic, uses T)
let selectedRegLang = 'en';
function selectRegLang(lang) { selectedRegLang = lang; /* highlight styling */ }
async function completeRegistration() {
  const phone = document.getElementById('regPhone').value.trim();
  if (!phone || phone.length < 9) { alert('Please enter a valid phone number'); return; }
  const res = await apiCall('/api/update_profile', 'POST', { user_id: state.user.user_id, phone, language: selectedRegLang });
  if (res && res.success) {
    state.user.phone = phone;
    state.user.language = selectedRegLang;
    state.lang = selectedRegLang;
    updateUILanguage();
    goPage('pg-home');
  } else alert('Registration failed. Please try again.');
}

let selectedSettingsLang = 'en';
function selectSettingsLang(lang) { selectedSettingsLang = lang; }
async function saveSettings() {
  const phone = document.getElementById('settingsPhone').value.trim();
  if (phone && phone.length < 9) { alert('Please enter a valid phone number'); return; }
  const res = await apiCall('/api/update_profile', 'POST', { user_id: state.user.user_id, phone: phone || undefined, language: selectedSettingsLang });
  if (res && res.success) {
    if (phone) state.user.phone = phone;
    if (selectedSettingsLang) { state.user.language = selectedSettingsLang; state.lang = selectedSettingsLang; updateUILanguage(); }
    alert(T('saveSettings'));
    goPage('pg-home');
  } else alert('Failed to save settings');
}

// ----- Game functions (keep your existing working ones) -----
function buildStakeGrid() { ... } // unchanged
async function joinGame(stake) { ... } // unchanged
function buildCardGrid(takenCards) { ... } // unchanged
async function pickCard(cardNumber) { ... } // unchanged
async function refreshGameInfo() { ... } // unchanged
async function loadMyCards() { ... } // unchanged
function startCountdown(seconds) { ... } // unchanged
function startGamePolling() { ... } // unchanged (includes cancellation handler using T('gameCancelled'))
function updateGameUI(gameState) { ... } // unchanged
async function renderMyCards(drawnBalls) { ... } // unchanged
function buildCardHTML(cardData, drawnNumbersSet, cardIndex) { ... } // unchanged
function showWinner(gameState) { ... } // unchanged
function buildDepositAmountGrid() { ... } // unchanged
let selectedPlatform = 'telebirr';
function selectPlatform(platform) { ... } // unchanged
async function submitDeposit() { ... } // unchanged
function setWdPlatform(platform, el) { ... } // unchanged
async function submitWithdraw() { ... } // unchanged
async function submitInquiry() { ... } // unchanged
async function loadLatestNotification() { ... } // unchanged
function showAdminPanel() { window.open('/admin','_blank'); }
async function loadPlatformNumbers() { ... } // unchanged

// ----- Initialization -----
window.addEventListener('DOMContentLoaded', async () => {
  buildStakeGrid();
  buildDepositAmountGrid();
  await loadPlatformNumbers();
  await loadUser();
  renderUI();
  if (state.user && state.user.phone) {
    const settingsPhone = document.getElementById('settingsPhone');
    if (settingsPhone) settingsPhone.value = state.user.phone;
  }
  goPage('pg-home');
});
