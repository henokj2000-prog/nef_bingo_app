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
  speechEnabled: true
};

let pollInterval = null;
let countdownInterval = null;

// ---------- Speech functions (Amharic) ----------
function digitToAmharic(num) {
  if (num === 10) return 'አስር';
  if (num >= 11 && num <= 19) {
    const units = ['', 'አንድ', 'ሁለት', 'ሦስት', 'አራት', 'አምስት', 'ስድስት', 'ሰባት', 'ስምንት', 'ዘጠኝ'];
    const unit = units[num - 10];
    return `አስራ ${unit}`;
  }
  if (num >= 20 && num <= 99) {
    const tens = Math.floor(num / 10);
    const ones = num % 10;
    let tensWord = '';
    switch (tens) {
      case 2: tensWord = 'ሀያ'; break;
      case 3: tensWord = 'ሠላሳ'; break;
      case 4: tensWord = 'አርባ'; break;
      case 5: tensWord = 'ሀምሳ'; break;
      case 6: tensWord = 'ስልሳ'; break;
      case 7: tensWord = 'ሰባ'; break;
      case 8: tensWord = 'ሰማንያ'; break;
      case 9: tensWord = 'ዘጠና'; break;
    }
    const onesWords = ['', 'አንድ', 'ሁለት', 'ሦስት', 'አራት', 'አምስት', 'ስድስት', 'ሰባት', 'ስምንት', 'ዘጠኝ'];
    if (ones === 0) return tensWord;
    else return `${tensWord} ${onesWords[ones]}`;
  }
  if (num < 10) {
    const words = ['', 'አንድ', 'ሁለት', 'ሦስት', 'አራት', 'አምስት', 'ስድስት', 'ሰባት', 'ስምንት', 'ዘጠኝ'];
    return words[num];
  }
  return '';
}

function ballToAmharic(ball) {
  const letter = ball[0];
  const number = parseInt(ball.slice(1));
  let letterAmh = '';
  if (letter === 'B') letterAmh = 'ቢ';
  else if (letter === 'I') letterAmh = 'አይ';
  else if (letter === 'N') letterAmh = 'ኤን';
  else if (letter === 'G') letterAmh = 'ጂ';
  else if (letter === 'O') letterAmh = 'ኦ';
  const numAmh = digitToAmharic(number);
  return `${letterAmh} ${numAmh}`;
}

function speakAmharic(text) {
  if (!state.speechEnabled) return;
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'am-ET';
  utterance.rate = 0.9;
  utterance.pitch = 1;
  window.speechSynthesis.speak(utterance);
}

function toggleSpeech() {
  state.speechEnabled = !state.speechEnabled;
  const btn = document.getElementById('speechToggleBtn');
  if (btn) btn.innerText = state.speechEnabled ? '🔊' : '🔇';
  if (!state.speechEnabled) window.speechSynthesis.cancel();
}

// ---------- Translations (Full LANG object) ----------
const LANG = {
  en: {
    // Registration & settings
    'welcomeTitle': 'እንኳን በደህና መጡ! / Welcome!',
    'registerSubtitle': 'ለመጫወት እባክዎ ምዝገባዎን ያጠናቅቁ / Please complete your registration to play',
    'phoneLabel': '📞 Phone Number',
    'referralCodeLabel': '🔗 Referral Code (optional)',
    'languageSelect': '🌐 Select Language',
    'startPlaying': '✅ Start Playing',
    'saveSettings': '💾 Save Changes',
    'back': 'Back',
    // Home screen
    'balance': 'Your Balance',
    'deposit': 'Deposit',
    'withdraw': 'Withdraw',
    'playNow': 'PLAY NOW',
    'games': 'Games',
    'wins': 'Wins',
    'won': 'Won ETB',
    'recentGames': 'Recent Games',
    'noGames': 'No games yet',
    'yourReferralLink': '🔗 Your Referral Link',
    'copyLink': '📋 Copy Link',
    'announcement': '📢 Announcement',
    // Stake selection
    'selectStake': 'Select Stake',
    // Card selection
    'prizePool': 'Prize Pool',
    'players': 'Players',
    'stake': 'Stake',
    'gameStartsIn': 'Game starts in',
    'sec': 'sec',
    'yourCards': 'Your cards',
    'cardLegend': '🟡 Yours &nbsp;🔴 Taken &nbsp;⬜ Available',
    'home': 'Home',
    'leaveGame': 'Leave Game',
    // Game playing
    'called': 'Called',
    'recent': 'Recent',
    // Winner screen
    'bingo': 'BINGO!',
    'bingoSub': 'BINGO! Winner!',
    'nextGame': 'Next game',
    'seconds': 'seconds',
    'balanceUpdated': '✅ Balance updated',
    // Deposit
    'selectAmount': 'Select Amount',
    'customAmount': 'Or custom amount',
    'selectPlatform': 'Select Platform',
    'telebirr': 'Telebirr',
    'cbe': 'CBE Birr',
    // Deposit confirm
    'paymentInstructions': 'Payment Instructions',
    'sendExactly': 'Send exactly',
    'number': 'Number',
    'reference': 'Transaction Reference',
    'uploadProof': 'Upload Proof',
    'transactionRefPlaceholder': 'Transaction reference number...',
    'submitDeposit': 'Submit',
    // Withdraw
    'withdrawTitle': 'Withdraw',
    'availableBalance': 'Available Balance',
    'amount': 'Amount',
    'accountNumber': 'Account Number',
    'requestWithdrawal': 'Request Withdrawal',
    // How to play
    'howToPlayTitle': 'How to Play',
    'step1': '<b>Deposit via Telebirr or CBE.</b><br>Confirmed by admin within 30 min.',
    'step2': '<b>Choose 10, 20, 50 or 100 ETB.</b><br>Higher stake = bigger prize!',
    'step3': '<b>Select up to 4 cards from 1-500.</b><br>🟡=yours, 🔴=taken. Game starts after 30 sec.',
    'step4': '<b>Numbers called every 4 seconds.</b><br>Your card updates live with ⭐.',
    'step5': '<b>Complete a row, column or diagonal to win!</b><br>Prize split if multiple winners.',
    'step6': '<b>Request withdrawal to Telebirr or CBE.</b><br>Processed within 24 hours.',
    // Help
    'helpTitle': 'Help',
    'sendInquiry': 'Send Inquiry',
    'messageAdmin': 'Message the admin directly',
    'howToPlayLink': 'How to Play',
    'gameRules': 'Game rules',
    'faqTitle': 'FAQ',
    'faqContent': '<b>How long does deposit take?</b><br>Usually 5-30 minutes after proof submitted.<br><br><b>Withdrawal time?</b><br>Within 24 hours on business days.<br><br><b>What if game cancels?</b><br>Full refund automatically credited.',
    // Inquiry
    'inquiryTitle': 'Send Inquiry',
    'subject': 'Subject',
    'message': 'Message',
    'send': 'Send',
    // Navbar
    'navHome': 'Home',
    'navPlay': 'Play',
    'navDeposit': 'Deposit',
    'navHowTo': 'How To',
    'navHelp': 'Help'
  },
  am: {
    // Registration & settings
    'welcomeTitle': 'እንኳን በደህና መጡ!',
    'registerSubtitle': 'ለመጫወት እባክዎ ምዝገባዎን ያጠናቅቁ',
    'phoneLabel': '📞 ስልክ ቁጥር',
    'referralCodeLabel': '🔗 ማጣቀሻ ኮድ (አማራጭ)',
    'languageSelect': '🌐 ቋንቋ ይምረጡ',
    'startPlaying': '✅ መጫወት ጀምር',
    'saveSettings': '💾 ለውጦችን አስቀምጥ',
    'back': 'ተመለስ',
    // Home screen
    'balance': 'የእርስዎ ቀሪ ሒሳብ',
    'deposit': 'ተቀማጭ',
    'withdraw': 'ማውጣት',
    'playNow': 'አሁን ተጫወት',
    'games': 'ጨዋታዎች',
    'wins': 'ድሎች',
    'won': 'አሸንፈዋል ETB',
    'recentGames': 'የቅርብ ጊዜ ጨዋታዎች',
    'noGames': 'እስካሁን ጨዋታ የለም',
    'yourReferralLink': '🔗 የእርስዎ ማጣቀሻ ሊንክ',
    'copyLink': '📋 ሊንኩን ቅዳ',
    'announcement': '📢 ማስታወቂያ',
    // Stake selection
    'selectStake': 'ውርርድ ይምረጡ',
    // Card selection
    'prizePool': 'ሽልማት ገንዘብ',
    'players': 'ተጫዋቾች',
    'stake': 'ውርርድ',
    'gameStartsIn': 'ጨዋታ የሚጀምረው በ',
    'sec': 'ሰከንድ',
    'yourCards': 'ካርዶችዎ',
    'cardLegend': '🟡 የእርስዎ &nbsp;🔴 ተወስዷል &nbsp;⬜ ይገኛል',
    'home': 'መነሻ',
    'leaveGame': 'ጨዋታ ለቀቅ',
    // Game playing
    'called': 'የተጠራ',
    'recent': 'የቅርብ ጊዜ',
    // Winner screen
    'bingo': 'ቢንጎ!',
    'bingoSub': 'ቢንጎ! አሸናፊ!',
    'nextGame': 'ቀጣይ ጨዋታ',
    'seconds': 'ሰከንዶች',
    'balanceUpdated': '✅ ቀሪ ሒሳብ ተዘምኗል',
    // Deposit
    'selectAmount': 'መጠን ይምረጡ',
    'customAmount': 'ወይም ብጁ መጠን',
    'selectPlatform': 'መድረክ ይምረጡ',
    'telebirr': 'ቴሌብር',
    'cbe': 'ሲቢኢ ብር',
    // Deposit confirm
    'paymentInstructions': 'የክፍያ መመሪያ',
    'sendExactly': 'በትክክል ይላኩ',
    'number': 'ቁጥር',
    'reference': 'የግብይት ማጣቀሻ',
    'uploadProof': 'ማስረጃ ስቀል',
    'transactionRefPlaceholder': 'የግብይት ማጣቀሻ ቁጥር...',
    'submitDeposit': 'አስገባ',
    // Withdraw
    'withdrawTitle': 'ማውጣት',
    'availableBalance': 'የሚገኝ ቀሪ ሒሳብ',
    'amount': 'መጠን',
    'accountNumber': 'የሂሳብ ቁጥር',
    'requestWithdrawal': 'ማውጣት ጠይቅ',
    // How to play
    'howToPlayTitle': 'እንዴት መጫወት ይቻላል',
    'step1': '<b>በቴሌብር ወይም ሲቢኢ ብር ተቀማጭ ያድርጉ።</b><br>በአስተዳዳሪ በ30 ደቂቃ ውስጥ ይረጋገጣል።',
    'step2': '<b>10፣ 20፣ 50 ወይም 100 ብር ይምረጡ።</b><br>ከፍተኛ ውርርድ = ትልቅ ሽልማት!',
    'step3': '<b�ከ1-500 ውስጥ እስከ 4 ካርዶች ይምረጡ።</b><br>🟡 የእርስዎ፣ 🔴 ተወስዷል። ጨዋታ ከ30 ሰከንድ በኋላ ይጀምራል።',
    'step4': '<b>ቁጥሮች በየ4 ሰከንድ ይጠራሉ።</b><br>ካርድዎ በቀጥታ በ⭐ ይዘምናል።',
    'step5': '<b>ሙሉ ረድፍ፣ አምድ ወይም ዲያግናል ማጠናቀቅ አለብዎት!</b><br>በርካታ አሸናፊዎች ካሉ ሽልማቱ ይከፈላል።',
    'step6': '<b>ማውጣት ለቴሌብር ወይም ሲቢኢ ብር ይጠይቁ።</b><br>በ24 ሰዓት ውስጥ ይከናወናል።',
    // Help
    'helpTitle': 'እርዳታ',
    'sendInquiry': 'መልእክት ላክ',
    'messageAdmin': 'በቀጥታ ለአስተዳዳሪ ይላኩ',
    'howToPlayLink': 'እንዴት መጫወት ይቻላል',
    'gameRules': 'የጨዋታ ህጎች',
    'faqTitle': 'በየጥ',
    'faqContent': '<b>ተቀማጭ ገንዘብ ምን ያህል ጊዜ ይወስዳል?</b><br>ማስረጃ ከቀረበ በኋላ ከ5-30 ደቂቃዎች ውስጥ።<br><br><b>ማውጣት ምን ያህል ጊዜ ይወስዳል?</b><br>በስራ ቀናት በ24 ሰዓት ውስጥ።<br><br><b>ጨዋታው ከተሰረዘ ምን ይሆናል?</b><br>ሙሉ ተመላሽ ገንዘብ በራስ-ሰር ይደረጋል።',
    // Inquiry
    'inquiryTitle': 'መልእክት ላክ',
    'subject': 'ርዕስ',
    'message': 'መልእክት',
    'send': 'ላክ',
    // Navbar
    'navHome': 'መነሻ',
    'navPlay': 'ጫወት',
    'navDeposit': 'ተቀማጭ',
    'navHowTo': 'እንዴት',
    'navHelp': 'እርዳታ'
  },
  om: {
    // Oromo translations (placeholder – replace with actual Oromo text)
    'welcomeTitle': 'Baggaaggama!',
    'registerSubtitle': 'Taphaaf galmaa\'i',
    'phoneLabel': '📞 Lakkoofsa Bilbilaa',
    'referralCodeLabel': '🔗 Koodii Waamicha (filannoo)',
    'languageSelect': '🌐 Afaan Filadhu',
    'startPlaying': '✅ Taphuu Eegali',
    'saveSettings': '💾 Jijjiirraa Kaa\'i',
    'back': 'Duuba',
    'balance': 'Hamma Qabdaa',
    'deposit': 'Kuusa',
    'withdraw': 'Baafadhu',
    'playNow': 'AMMA TAPHU',
    'games': 'Taphatoota',
    'wins': 'Mo’annoolee',
    'won': 'ETB Mo’atte',
    'recentGames': 'Tapha Dhiyaa',
    'noGames': 'Tapha hin jiru',
    'yourReferralLink': '🔗 Liinki Keessan',
    'copyLink': '📋 Liinkii Kaapii',
    'announcement': '📢 Labsii',
    'selectStake': 'Baay’ina Wager Filadhu',
    'prizePool': 'Qabeessa Badhaasa',
    'players': 'Taphattoota',
    'stake': 'Wager',
    'gameStartsIn': 'Taphiin eegala',
    'sec': 'sekendi',
    'yourCards': 'Kaardii Keessan',
    'cardLegend': '🟡 Kan kee &nbsp;🔴 Fudhatame &nbsp;⬜ Jira',
    'home': 'Mana',
    'leaveGame': 'Tapha Dhiisi',
    'called': 'Waamame',
    'recent': 'Dhiyaa',
    'bingo': 'BINGO!',
    'bingoSub': 'BINGO! Mo’ataa!',
    'nextGame': 'Tapha Ittaanu',
    'seconds': 'sekendi',
    'balanceUpdated': '✅ Hammi fooyya’e',
    'selectAmount': 'Baay’ina Filadhu',
    'customAmount': 'Baay’ina Ofiisaani',
    'selectPlatform': 'Platform Filadhu',
    'telebirr': 'Telebirr',
    'cbe': 'CBE Birr',
    'paymentInstructions': 'Qajeelfama Kaffaltii',
    'sendExactly': 'Sagalee Ergi',
    'number': 'Lakkoofsa',
    'reference': 'Hanga Ittiin Mul’atu',
    'uploadProof': 'Ragaa Uplaadi',
    'transactionRefPlaceholder': 'Lakkoofsa hanga ittiin mul’atu...',
    'submitDeposit': 'Ergi',
    'withdrawTitle': 'Baafadhu',
    'availableBalance': 'Hamma Jiru',
    'amount': 'Baay’ina',
    'accountNumber': 'Lakkoofsa Herregaa',
    'requestWithdrawal': 'Baafachu gaafadhu',
    'howToPlayTitle': 'Akkam Tapha',
    'step1': '<b>Telebirr ykn CBE Birr kuusa.</b><br>Admin keessatti 30 dakiiqa keessatti mirkaneeffama.',
    'step2': '<b>10, 20, 50 ykn 100 ETB filadhu.</b><br>Wager ol ta’uu = badhaasa guddaa!',
    'step3': '<b>Kaardii 1-500 keessaa hanga 4 filadhu.</b><br>🟡 kan kee, 🔴 fudhatame. Taphiin 30 sekendi booda eegala.',
    'step4': '<b>Lakkoofsonni sekendi 4 mara waamamu.</b><br>Kaardiin kee ⭐’n fooyya’a.',
    'step5': '<b>Topha, tulluu ykn diagonal guutuu mo’i!</b><br>Yoo mo’attoonni hedduu ta’an badhaasni qooddama.',
    'step6': '<b>Baafachuuf Telebirr ykn CBE Birr gaafadhu.</b><br>Seenaa 24 keessatti hojjeta.',
    'helpTitle': 'Gargaarsa',
    'sendInquiry': 'Gaaffii Ergi',
    'messageAdmin': 'Adminitti ergi',
    'howToPlayLink': 'Akkam Tapha',
    'gameRules': 'Seera Taphaa',
    'faqTitle': 'Gaaffiiwwan',
    'faqContent': '<b>Kuusiin yeroo meeqa fudhata?</b><br>Ragaan ergaman booda 5-30 dakiiqa keessatti.<br><br><b>Baafachuun yeroo meeqa fudhata?</b><br>Guyyoota hojii keessatti 24 sa’aatii keessatti.<br><br><b>Taphiin yoo haquu, maal ta’a?</b><br>Hamma guutuun ofiisaan deebifama.',
    'inquiryTitle': 'Gaaffii Ergi',
    'subject': 'Mataduree',
    'message': 'Ergaa',
    'send': 'Ergi',
    'navHome': 'Mana',
    'navPlay': 'Tapha',
    'navDeposit': 'Kuusa',
    'navHowTo': 'Akkam',
    'navHelp': 'Gargaarsa'
  },
  ti: {
    // Tigrigna translations (placeholder – replace with actual Tigrigna text)
    'welcomeTitle': 'እንቋዕ ብደሓን መጻእኩም!',
    'registerSubtitle': 'ንምጻወት በጃኹም ምዝገባኹም ኣጽምዑ',
    'phoneLabel': '📞 ቁጽሪ ተሌፎን',
    'referralCodeLabel': '🔗 ኮድ ምዝገባ (ኣማራጻዊ)',
    'languageSelect': '🌐 ቋንቋ ምረጹ',
    'startPlaying': '✅ ምጽዋት ጀምሩ',
    'saveSettings': '💾 ለውጥታት ዓቅም',
    'back': 'ተመለስ',
    'balance': 'ቀሪ ሒሳብኩም',
    'deposit': 'ተቀማጽ',
    'withdraw': 'ምውጻእ',
    'playNow': 'ሕጂ ተጻወቱ',
    'games': 'ጸወታታት',
    'wins': 'ዓወታት',
    'won': 'ETB ዓሚቶም',
    'recentGames': 'ናይ ቀረባ ጸወታታት',
    'noGames': 'ክሳብ ሕጂ ጸወታ የለን',
    'yourReferralLink': '🔗 ናትኩም ሊንክ',
    'copyLink': '📋 ሊንክ ቅዱሑ',
    'announcement': '📢 ኣዋጀታ',
    'selectStake': 'ውርርድ ምረጹ',
    'prizePool': 'ብድሒ ዓዉኒ',
    'players': 'ተጻወትቲ',
    'stake': 'ውርርድ',
    'gameStartsIn': 'ጸወታ ይጅምር ብ',
    'sec': 'ካልኢት',
    'yourCards': 'ካርዳትኩም',
    'cardLegend': '🟡 ናትኩም &nbsp;🔴 ተወሲዱ &nbsp;⬜ ኣሎ',
    'home': 'ገዛ',
    'leaveGame': 'ጸወታ ስኣሩ',
    'called': 'ተጸዊዑ',
    'recent': 'ቀረባ',
    'bingo': 'ቢንጎ!',
    'bingoSub': 'ቢንጎ! ዓዋዲ!',
    'nextGame': 'ዝቕጽል ጸወታ',
    'seconds': 'ካልኢታት',
    'balanceUpdated': '✅ ቀሪ ሒሳብ ተዘሚኑ',
    'selectAmount': 'ብድሒ ምረጹ',
    'customAmount': 'ወይ ብድሒ ክትወስኑ',
    'selectPlatform': 'መድረኽ ምረጹ',
    'telebirr': 'ተሌብር',
    'cbe': 'ሲቢኢ ብር',
    'paymentInstructions': 'መምርሒታት ክፍሊት',
    'sendExactly': 'ብትኽክል ሰደዱ',
    'number': 'ቁጽሪ',
    'reference': 'መጠቀሚ ግብዓት',
    'uploadProof': 'ረድኤት ኣምጽኡ',
    'transactionRefPlaceholder': 'ቁጽሪ መጠቀሚ ግብዓት...',
    'submitDeposit': 'ኣምህሉ',
    'withdrawTitle': 'ምውጻእ',
    'availableBalance': 'ቀሪ ሒሳብ ዘሎ',
    'amount': 'ብድሒ',
    'accountNumber': 'ቁጽሪ ሒሳብ',
    'requestWithdrawal': 'ምውጻእ ሕተቱ',
    'howToPlayTitle': 'ከመይ ምጽዋት',
    'step1': '<b>በተሌብር ወይ ሲቢኢ ብር ተቀማጽ ግበሩ።</b><br>ብኣስተዳዳሪ ኣብ 30 ደቒቕ ውሽጢ ይረጋገጽ።',
    'step2': '<b>10፣ 20፣ 50 ወይ 100 ETB ምረጹ።</b><br>ውርርድ ልዑል = ዓቢ ዓዉኒ!',
    'step3': '<b>ካብ 1-500 ክሳብ 4 ካርዳት ምረጹ።</b><br>🟡 ናትኩም፣ 🔴 ተወሲዱ። ጸወታ ድሕሪ 30 ካልኢት ይጅምር።',
    'step4': '<b>ቁጽርታት ብዘለኣ 4 ካልኢት ይጽዋዑ።</b><br>ካርድኩም ብ⭐ ብቀጥታ ይዘምን።',
    'step5': '<b>�ሙሉ መስርወት፣ ዓምዲ ወይ ዲያጎናል ምፍጻም ኣለኩም!</b><br>ብዙሓት ዓወዲ እንተለዉ ዓዉኒ ይተኻፈሉ።',
    'step6': '<b>ምውጻእ ንተሌብር ወይ ሲቢኢ ብር ሕተቱ።</b><br>ኣብ 24 ሰዓት ውሽጢ ይፍጸም።',
    'helpTitle': 'ሓገዝ',
    'sendInquiry': 'መልእኽቲ ሰደዱ',
    'messageAdmin': 'ብቀጥታ ንኣስተዳዳሪ ምልክታ',
    'howToPlayLink': 'ከመይ ምጽዋት',
    'gameRules': 'ሕግታት ጸወታ',
    'faqTitle': 'ሕቶታት',
    'faqContent': '<b>ተቀማጽ ክንደይ ግዜ ይወስድ?</b><br>ረድኤት ምስ ቀረበ ድሕሪ 5-30 ደቒቕ።<br><br><b>ምውጻእ ክንደይ ግዜ ይወስድ?</b><br>ኣብ መዓልትታት ስራሕ ኣብ 24 ሰዓት ውሽጢ።<br><br><b>ጸወታ እንተተሰሪዙ እንታይ ይኸውን?</b><br>ምሉእ ተመላሽ ገንዘብ ብኣውቶማቲክ ይግበር።',
    'inquiryTitle': 'መልእኽቲ ሰደዱ',
    'subject': 'ርእሲ',
    'message': 'መልእኽቲ',
    'send': 'ሰደዱ',
    'navHome': 'ገዛ',
    'navPlay': 'ጸወታ',
    'navDeposit': 'ተቀማጽ',
    'navHowTo': 'ከመይ',
    'navHelp': 'ሓገዝ'
  }
};

function T(key, vars = {}) {
  let text = (LANG[state.lang] && LANG[state.lang][key]) || (LANG.en && LANG.en[key]) || key;
  for (let [k, v] of Object.entries(vars)) text = text.replace(`{${k}}`, v);
  return text;
}

function updateUILanguage() {
  // Update all elements with data-i18n (text content)
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (key) el.innerText = T(key);
  });
  // Update placeholders
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.getAttribute('data-i18n-placeholder');
    if (key) el.placeholder = T(key);
  });
  // Update innerHTML for elements with data-i18n-html
  document.querySelectorAll('[data-i18n-html]').forEach(el => {
    const key = el.getAttribute('data-i18n-html');
    if (key) el.innerHTML = T(key);
  });
  // Static IDs that are not covered by data-i18n (if any) – but our HTML now uses data-i18n everywhere, so this is optional
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
  if (document.getElementById('selectHomeBtn')) document.getElementById('selectHomeBtn').innerText = T('home');
  if (document.getElementById('gameHomeBtn')) document.getElementById('gameHomeBtn').innerText = T('home');
  if (document.getElementById('winnerHomeBtn')) document.getElementById('winnerHomeBtn').innerText = T('home');
  if (document.getElementById('depBackText')) document.getElementById('depBackText').innerText = T('back');
  if (document.getElementById('confBackText')) document.getElementById('confBackText').innerText = T('back');
  if (document.getElementById('wdBackText')) document.getElementById('wdBackText').innerText = T('back');
  if (document.getElementById('inqBackText')) document.getElementById('inqBackText').innerText = T('back');
  if (document.getElementById('settingsSaveBtn')) document.getElementById('settingsSaveBtn').innerText = T('saveSettings');
  if (document.getElementById('submitDepositBtn')) document.getElementById('submitDepositBtn').innerText = T('submitDeposit');
  if (document.getElementById('requestWithdrawBtn')) document.getElementById('requestWithdrawBtn').innerText = T('requestWithdrawal');
  if (document.getElementById('sendInquiryBtn')) document.getElementById('sendInquiryBtn').innerText = T('send');
  if (document.getElementById('subjectLabel')) document.getElementById('subjectLabel').innerText = T('subject');
  if (document.getElementById('messageLabel')) document.getElementById('messageLabel').innerText = T('message');
  if (document.getElementById('amountLabel')) document.getElementById('amountLabel').innerText = T('amount');
  if (document.getElementById('accountNumberLabel')) document.getElementById('accountNumberLabel').innerText = T('accountNumber');
  if (document.getElementById('wdPlatformTitle')) document.getElementById('wdPlatformTitle').innerText = T('selectPlatform');
  if (document.getElementById('referenceLabel')) document.getElementById('referenceLabel').innerText = T('reference');
  if (document.getElementById('leaveGameBtn')) document.getElementById('leaveGameBtn').innerText = T('leaveGame');
}

// ---------- API helper ----------
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
  const order = ['en', 'am', 'om', 'ti'];
  let idx = order.indexOf(state.lang);
  state.lang = order[(idx + 1) % order.length];
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
  if (pageId === 'pg-register') {
    autoFillReferralCode();
  }
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

// ---------- Settings ----------
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
    alert(T('saveSettings'));
    goPage('pg-home');
  } else {
    alert('Failed to save settings');
  }
}

// ---------- Game functions ----------
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
  if (state.balance < stake) { alert(T('insufficient')); return; }
  if (pollInterval) clearInterval(pollInterval);
  if (countdownInterval) clearInterval(countdownInterval);
  state.stake = stake;
  state.myCards = [];
  state.myCardData = [];
  state.gameId = null;
  const res = await apiCall('/api/join_game', 'POST', { user_id: state.user.user_id, stake });
  if (!res || res.error) { alert(res?.error || 'Failed to join game'); return; }
  state.gameId = res.game_id;
  document.getElementById('sel-prize').innerText = Math.floor((res.prize_pool || 0) * 0.8) + ' ETB';
  document.getElementById('sel-players').innerText = res.players;
  document.getElementById('sel-stake').innerText = stake + ' ETB';
  buildCardGrid(res.taken_cards || []);
  if (res.status === 'running') goPage('pg-game');
  else { startCountdown(res.countdown || 30); goPage('pg-select'); }
  startGamePolling();
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
  if (state.myCards.length >= 4) { alert(T('maxCards')); return; }
  const btn = document.getElementById(`card-btn-${cardNumber}`);
  if (!btn || btn.classList.contains('taken') || btn.classList.contains('mine')) return;
  const res = await apiCall('/api/pick_card', 'POST', {
    user_id: state.user.user_id,
    game_id: state.gameId,
    card_number: cardNumber,
    stake: state.stake
  });
  if (!res || res.error) { alert(res?.error || 'Failed to pick card'); return; }
  state.myCards.push(cardNumber);
  state.balance = res.balance;
  renderUI();
  await refreshGameInfo();
  await loadMyCards();
  buildCardGrid(state.takenCards || []);
}

async function leaveGame() {
  if (!state.gameId || !state.user) return;
  if (confirm(T('leaveGame') + '? You will be refunded the full stake.')) {
    const res = await apiCall('/api/withdraw_from_game', 'POST', {
      user_id: state.user.user_id,
      game_id: state.gameId
    });
    if (res && res.success) {
      alert(res.message);
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
    if (remaining <= 0) { clearInterval(countdownInterval); countdownInterval = null; }
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
    document.getElementById('bLetter').innerText = last[0];
    document.getElementById('bNum').innerText = last.slice(1);
    const amharicText = ballToAmharic(last);
    speakAmharic(amharicText);
  }
  document.getElementById('game-called').innerText = drawn.length + '/75';
  const displayPrize = gameState.winners_share || Math.floor((gameState.prize_pool || 0) * 0.8);
  document.getElementById('game-prize').innerText = displayPrize + ' ETB';
  document.getElementById('game-players').innerText = gameState.players;
  const recentChips = document.getElementById('recentChips');
  if (recentChips) recentChips.innerHTML = drawn.slice(-6).reverse().map(b => `<div class="chip">${b}</div>`).join('');
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
  const drawnNumbers = drawnBalls.map(b => parseInt(b.slice(1))).filter(n => !isNaN(n));
  const drawnSet = new Set(drawnNumbers);
  wrap.innerHTML = '';
  for (const card of state.myCardData) {
    wrap.innerHTML += buildCardHTML(card.card_data, drawnSet, card.card_index);
  }
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
  const prizeEach = gameState.prize_each || 0;
  const winners = gameState.winners || [];
  const winnerDiv = document.getElementById('winnerCards');
  if (winnerDiv) {
    if (!winners.length) winnerDiv.innerHTML = '<div style="color:var(--sub);text-align:center;padding:10px">No winner this round</div>';
    else winnerDiv.innerHTML = winners.map(w => `<div class="w-card"><div class="w-name">👤 ${w.name}</div><div style="font-size:11px;color:var(--sub)">Card #${w.card_number}</div><div class="w-prize">+${w.prize || prizeEach} ETB</div></div>`).join('');
  }
  speakAmharic('ቢንጎ!');
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
    tx_ref: proof
  });
  if (!res) alert('Network error');
  else if (res.error) alert('❌ ' + res.error);
  else {
    if (res.approved) { state.balance = res.balance; renderUI(); alert(T('depositSuccess', { amount })); }
    else alert(T('depositPending'));
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
    platform: platform,
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

// ---------- Initialization ----------
window.addEventListener('DOMContentLoaded', async () => {
  buildStakeGrid();
  buildDepositAmountGrid();
  await loadPlatformNumbers();
  await loadUser();
  renderUI();
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
