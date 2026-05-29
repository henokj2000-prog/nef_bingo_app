const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

const API = '';
let state = {
  user: null, balance: 0, gameId: null, stake: 0,
  myCards: [], drawn: [], lang: 'en'
};

const t = {
  en: {
    appName: 'NEF BINGO', appSub: 'ነፍ ቢንጎ',
    balance: 'Your Balance', deposit: 'Deposit', withdraw: 'Withdraw',
    playNow: '🎮 PLAY NOW', gamesPlayed: 'Games Played', wins: 'Wins',
    totalWon: 'Total Won', recentGames: 'Recent Games',
    selectStake: 'Select Stake', joinGame: 'Join Game',
    cardSelection: 'Pick Your Card', gameStarts: 'Game starts in',
    yourCards: 'Your cards', yours: 'Yours', taken: 'Taken', available: 'Available',
    prizePool: 'Prize Pool', players: 'Players', called: 'Called',
    recent: 'Recent numbers', bingo: 'BINGO!', winner: 'Winner!',
    nextGame: 'Next game in', balanceUpdated: 'Balance updated',
    howToPlay: 'How to Play', help: 'Help', home: 'Home', play: 'Play',
    inquiry: 'Send Inquiry', faq: 'FAQ', back: '← Back',
    selectAmount: 'Select Amount', selectPlatform: 'Select Platform',
    paymentInstructions: 'Payment Instructions', uploadProof: 'Upload Proof',
    submit: 'Submit', send: 'Send', amount: 'Amount', accountNo: 'Account Number',
    requestWithdraw: 'Request Withdrawal', subject: 'Subject', message: 'Message',
    stake: 'Stake', insufficient: 'Insufficient balance!',
  },
  am: {
    appName: 'ነፍ ቢንጎ', appSub: 'NEF BINGO',
    balance: 'ሂሳብዎ', deposit: 'ተቀምጦ', withdraw: 'አውጣ',
    playNow: '🎮 አሁን ጫወት', gamesPlayed: 'የተጫወቱ ጨዋታዎች', wins: 'ድሎች',
    totalWon: 'ድምር ያሸነፉት', recentGames: 'የቅርብ ጨዋታዎች',
    selectStake: 'ድርሻ ምረጡ', joinGame: 'ጨዋታ ይቀላቀሉ',
    cardSelection: 'ካርድዎን ምረጡ', gameStarts: 'ጨዋታ ይጀምራል',
    yourCards: 'ካርዶችዎ', yours: 'የእርስዎ', taken: 'የተወሰደ', available: 'ይገኛል',
    prizePool: 'የሽልማት ድምር', players: 'ተጫዋቾች', called: 'የተጠሩ',
    recent: 'የቅርብ ቁጥሮች', bingo: 'ቢንጎ!', winner: 'አሸናፊ!',
    nextGame: 'ቀጣይ ጨዋታ', balanceUpdated: 'ሂሳብ ተዘምኗል',
    howToPlay: 'እንዴት ይጫወቱ', help: 'እርዳታ', home: 'መነሻ', play: 'ጫወት',
    inquiry: 'ጥያቄ ላክ', faq: 'ጥያቄዎች', back: '← ተመለስ',
    selectAmount: 'መጠን ምረጡ', selectPlatform: 'መድረክ ምረጡ',
    paymentInstructions: 'የክፍያ መመሪያ', uploadProof: 'ደረሰኝ ያስገቡ',
    submit: 'አስገባ', send: 'ላክ', amount: 'መጠን', accountNo: 'የሂሳብ ቁጥር',
    requestWithdraw: 'ማስወጣት ይጠይቁ', subject: 'ርዕስ', message: 'መልዕክት',
    stake: 'ድርሻ', insufficient: 'በቂ ሂሳብ የለም!',
  }
};

function T(key) { return t[state.lang][key] || key; }

function toggleLang() {
  state.lang = state.lang === 'en' ? 'am' : 'en';
  renderApp();
}

function goPage(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const el = document.getElementById(id);
  if (el) { el.classList.add('active'); window.scrollTo(0,0); }
  document.querySelectorAll('.nav-item').forEach(n => {
    n.classList.toggle('active', n.dataset.page === id);
  });
}

async function apiCall(path, method='GET', body=null) {
  try {
    const opts = { method, headers: {'Content-Type':'application/json'} };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(API + path, opts);
    return await res.json();
  } catch(e) { return null; }
}

async function loadUser() {
  const userId = tg?.initDataUnsafe?.user?.id || 12345;
  const username = tg?.initDataUnsafe?.user?.username || 'testuser';
  const fullName = tg?.initDataUnsafe?.user?.first_name || 'Test User';
  const data = await apiCall(`/api/player/${userId}?username=${username}&full_name=${encodeURIComponent(fullName)}`);
  if (data) {
    state.user = data;
    state.balance = data.balance;
  }
}

function renderApp() {
  document.querySelectorAll('[data-t]').forEach(el => {
    el.textContent = T(el.dataset.t);
  });
  document.querySelectorAll('[data-app-name]').forEach(el => {
    el.textContent = T('appName');
  });
  document.querySelectorAll('[data-app-sub]').forEach(el => {
    el.textContent = T('appSub');
  });
  if (state.balance !== undefined) {
    document.querySelectorAll('[data-balance]').forEach(el => {
      el.textContent = state.balance.toFixed(2) + ' ETB';
    });
  }
}

window.addEventListener('DOMContentLoaded', async () => {
  await loadUser();
  renderApp();
  goPage('pg-home');
});
