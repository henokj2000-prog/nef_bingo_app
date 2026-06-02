// ── Telegram WebApp init ─────────────────────────────
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

// ── Single global state (defined ONCE here only) ─────
const state = {
  user: null,
  balance: 0,
  gameId: null,
  stake: 0,
  myCards: [],
  lang: 'en',
  games_played: 0,
  wins: 0,
  total_won: 0
};

// ── Translations ─────────────────────────────────────
const LANG = {
  en: {
    balance:'Your Balance', deposit:'Deposit', withdraw:'Withdraw',
    playNow:'🎮 PLAY NOW', insufficient:'Insufficient balance!',
  },
  am: {
    balance:'ሂሳብዎ', deposit:'ተቀምጦ', withdraw:'አውጣ',
    playNow:'🎮 አሁን ጫወት', insufficient:'በቂ ሂሳብ የለም!',
  }
};
function T(key){ return LANG[state.lang][key] || key; }

function toggleLang(){
  state.lang = state.lang === 'en' ? 'am' : 'en';
  renderApp();
}

// ── Navigation ───────────────────────────────────────
function goPage(id){
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const el = document.getElementById(id);
  if(el){ el.classList.add('active'); window.scrollTo(0,0); }
  if(id === 'pg-home'){ loadUser().then(() => renderApp()); }
  document.querySelectorAll('.nav-item').forEach(n => {
    n.classList.toggle('active', n.dataset.page === id);
  });
}

function navTo(id, el){
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  el.classList.add('active');
  goPage(id);
}

// ── API helper ───────────────────────────────────────
async function apiCall(path, method='GET', body=null){
  try {
    const opts = { method, headers: {'Content-Type':'application/json'} };
    if(body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    return await res.json();
  } catch(e){
    console.error('API error:', e);
    return null;
  }
}

// ── Load user from backend ───────────────────────────
async function loadUser(){
  const userId   = tg?.initDataUnsafe?.user?.id        || 99999;
  const username = tg?.initDataUnsafe?.user?.username  || 'admin';
  const fullName = tg?.initDataUnsafe?.user?.first_name|| 'Admin User';
 
  let retries = 3;
  while(retries > 0){
    const data = await apiCall(
      `/api/player/${userId}?username=${encodeURIComponent(username)}&full_name=${encodeURIComponent(fullName)}`
    );
    if(data && !data.error){
      state.user         = data;
      state.balance      = data.balance      || 0;
      state.games_played = data.games_played || 0;
      state.wins         = data.wins         || 0;
      state.total_won    = data.total_won    || 0;
      return;
    }
    retries--;
    await new Promise(r => setTimeout(r, 1000));
  }
}

// ── Render UI with current state ─────────────────────
function renderApp(){
  const bal = document.getElementById('balanceDisplay');
  if(bal) bal.textContent = (state.balance||0).toFixed(2) + ' ETB';

  const wdBal = document.getElementById('wdBalanceShow');
  if(wdBal) wdBal.textContent = (state.balance||0).toFixed(2) + ' ETB';

  const sg = document.getElementById('stat-games');
  const sw = document.getElementById('stat-wins');
  const swon = document.getElementById('stat-won');
  if(sg) sg.textContent = state.games_played || 0;
  if(sw) sw.textContent = state.wins         || 0;
  if(swon) swon.textContent = (state.total_won||0).toFixed(0);
}

// ── Build stake grid ─────────────────────────────────
function buildStakeGrid(){
  const sg = document.getElementById('stakeGrid');
  if(!sg) return;
  sg.innerHTML = '';
  [10, 20, 50, 100].forEach(s => {
    const b = document.createElement('div');
    b.className = 'amount-btn';
    b.textContent = s + ' ETB';
    b.onclick = () => joinGame(s);
    sg.appendChild(b);
  });
}

// ── Build deposit amount grid ─────────────────────────
let selDepAmt = 50;
function buildDepAmtGrid(){
  const dag = document.getElementById('depAmtGrid');
  if(!dag) return;
  dag.innerHTML = '';
  [50, 100, 200, 500].forEach(a => {
    const b = document.createElement('div');
    b.className = 'amount-btn' + (a === 50 ? ' selected' : '');
    b.textContent = a + ' ETB';
    b.onclick = () => {
      document.querySelectorAll('#depAmtGrid .amount-btn').forEach(x => x.classList.remove('selected'));
      b.classList.add('selected');
      selDepAmt = a;
    };
    dag.appendChild(b);
  });
}

// ── Deposit ──────────────────────────────────────────
const PLATFORMS = {
  telebirr: { name:'Telebirr',  number:'0929 001 000' },
  cbe:      { name:'CBE Birr',  number:'1000061737212' }
};
let selPlatform = 'telebirr';

function selectPlatform(p){
  selPlatform = p;
  const amt = parseInt(document.getElementById('depCustomAmt').value) || selDepAmt;
  document.getElementById('depAmountShow').textContent = amt + ' ETB';
  document.getElementById('depPlatformNum').textContent = PLATFORMS[p].number;
  document.getElementById('depRef').textContent = 'BINGO-' + (state.user?.user_id || 'XXX');
  goPage('pg-dep-confirm');
}

async function submitDeposit(){
  const proof = document.getElementById('depProof').value.trim();
  const amt   = parseInt(document.getElementById('depCustomAmt').value) || selDepAmt;
  if(!proof){ alert('Please enter transaction reference number'); return; }

  if(!state.user){
  await loadUser();
  if(!state.user){ alert('Please go back to Home first'); goPage('pg-home'); return; }
} 
  const res = await apiCall('/api/deposit', 'POST', {
    user_id: state.user.user_id,
    amount:  amt,
    platform: selPlatform,
    tx_ref:  proof
  });

  if(res && res.success){
    alert('✅ Submitted! Admin will confirm shortly.');
    document.getElementById('depProof').value = '';
    await loadUser();
    renderApp();
    goPage('pg-home');}
  
}

// ── Withdraw ─────────────────────────────────────────
function setWdPlatform(p, el){
  document.getElementById('wd-platform').value = p;
  document.querySelectorAll('#pg-withdraw .platform-btn').forEach(b => b.style.borderColor = '');
  el.style.borderColor = 'var(--gold)';
}

async function submitWithdraw(){
  const amt  = parseFloat(document.getElementById('wdAmount').value);
  const acc  = document.getElementById('wdAccount').value.trim();
  const plat = document.getElementById('wd-platform').value;
  if(!amt || !acc){ alert('Please fill all fields'); return; }
  if(amt > state.balance){ alert(T('insufficient')); return; }
  const res = await apiCall('/api/withdraw', 'POST', {
    user_id:    state.user.user_id,
    amount:     amt,
    platform:   plat,
    account_no: acc
  });
  if(res && res.success){
    state.balance -= amt;
    renderApp();
    alert('✅ Withdrawal requested! Processed within 24 hours.');
    goPage('pg-home');
  } else {
    alert('❌ ' + (res?.error || 'Request failed'));
  }
}

// ── Inquiry ──────────────────────────────────────────
async function submitInquiry(){
  const subj = document.getElementById('inqSubject').value.trim();
  const msg  = document.getElementById('inqMessage').value.trim();
  if(!subj || !msg){ alert('Please fill all fields'); return; }
  const res = await apiCall('/api/inquiry', 'POST', {
    user_id: state.user.user_id,
    subject: subj,
    message: msg
  });
  if(res && res.success){
    alert('✅ Message sent to admin!');
    document.getElementById('inqSubject').value = '';
    document.getElementById('inqMessage').value = '';
    goPage('pg-help');
  } else {
    alert('❌ Failed to send. Try again.');
  }
}

// ── Join game ─────────────────────────────────────────
async function joinGame(stake){
  if(state.balance < stake){ alert(T('insufficient')); return; }
  state.stake   = stake;
  state.myCards = [];
  const res = await apiCall('/api/join_game', 'POST', {
    user_id: state.user.user_id,
    stake:   stake
  });
  if(!res || res.error){ alert('Error joining game. Try again.'); return; }
  state.gameId = res.game_id;
  document.getElementById('sel-prize').textContent   = res.prize_pool + ' ETB';
  document.getElementById('sel-players').textContent = res.players;
  document.getElementById('sel-stake').textContent   = stake + ' ETB';
  buildCardGrid(res.game_id, res.taken_cards || []);
  startCountdown(res.countdown || 30);
  goPage('pg-select');
  pollGameState();
}

// ── Card grid ─────────────────────────────────────────
function buildCardGrid(gameId, taken){
  const g = document.getElementById('selGrid');
  g.innerHTML = '';
  for(let i = 1; i <= 200; i++){
    const b = document.createElement('div');
    const isMine  = state.myCards.includes(i);
    const isTaken = taken.includes(i) && !isMine;
    b.className = 'cgrid-btn' + (isMine ? ' mine' : isTaken ? ' taken' : '');
    b.textContent = isMine ? '🟡' + i : isTaken ? '🔴' + i : i;
    b.id = 'card-btn-' + i;
    if(!isMine && !isTaken) b.onclick = () => pickCard(i);
    g.appendChild(b);
  }
  document.getElementById('myCardCount').textContent = state.myCards.length + '/4';
}

async function pickCard(cardNum){
  const btn = document.getElementById('card-btn-' + cardNum);
  if(!btn || btn.classList.contains('mine') || btn.classList.contains('taken')) return;
  const res = await apiCall('/api/pick_card', 'POST', {
    user_id:     state.user.user_id,
    game_id:     state.gameId,
    card_number: cardNum,
    stake:       state.stake
  });
  if(!res || res.error){ alert(res?.error || 'Error picking card'); return; }
  state.myCards.push(cardNum);
  state.balance = res.balance;
  renderApp();
  btn.className = 'cgrid-btn mine';
  btn.textContent = '🟡' + cardNum;
  btn.onclick = null;
  document.getElementById('myCardCount').textContent = state.myCards.length + '/4';
}

// ── Countdown ─────────────────────────────────────────
let cdInterval = null;
function startCountdown(seconds){
  if(cdInterval) clearInterval(cdInterval);
  let cd = seconds;
  const cdEl   = document.getElementById('cd1');
  const progEl = document.getElementById('prog1');
  if(cdEl) cdEl.textContent = cd;
  if(progEl) progEl.style.width = '0%';
  cdInterval = setInterval(() => {
    cd--;
    if(cdEl)   cdEl.textContent = Math.max(0, cd);
    if(progEl) progEl.style.width = ((30 - cd) / 30 * 100) + '%';
    if(cd <= 0) clearInterval(cdInterval);
  }, 1000);
}

// ── Poll game state ───────────────────────────────────
let pollTimeout = null;
async function pollGameState(){
  if(!state.gameId) return;
  const res = await apiCall(`/api/game_state/${state.gameId}?user_id=${state.user.user_id}`);
  if(!res) { pollTimeout = setTimeout(pollGameState, 3000); return; }

  if(res.status === 'waiting'){
    buildCardGrid(state.gameId, res.taken_cards || []);
    document.getElementById('sel-players').textContent = res.players;
    document.getElementById('sel-prize').textContent   = res.prize_pool + ' ETB';
    pollTimeout = setTimeout(pollGameState, 2000);

  } else if(res.status === 'running'){
    await updateCardsFromServer();
    updateGameScreen(res);
    goPage('pg-game');
    pollTimeout = setTimeout(pollGameState, 2000);

  } else if(res.status === 'finished'){
    await updateCardsFromServer();
    showWinner(res);
  }
}

// ── Game screen update ────────────────────────────────
function updateGameScreen(res){
  const drawn = res.drawn_balls || [];
  const last  = drawn[drawn.length - 1];
  if(last){
    document.getElementById('bLetter').textContent = ballLetter(last);
    document.getElementById('bNum').textContent    = last;
  }
  document.getElementById('game-called').textContent  = drawn.length + '/75';
  document.getElementById('game-prize').textContent   = res.prize_pool + ' ETB';
  document.getElementById('game-players').textContent = res.players;
  const rc = document.getElementById('recentChips');
  if(rc) rc.innerHTML = drawn.slice(-6).reverse()
    .map(b => `<div class="chip">${ballLetter(b)}${b}</div>`).join('');
  renderMyCards(drawn);
}

// ── Render bingo cards ────────────────────────────────
let myCardData = [];
async function updateCardsFromServer(){
  if(!state.gameId || !state.user) return;
  const res = await apiCall(`/api/my_cards/${state.gameId}?user_id=${state.user.user_id}`);
  if(res) myCardData = res.cards || [];
}

function renderMyCards(drawn){
  const wrap = document.getElementById('bingoCardsWrap');
  if(!wrap) return;
  wrap.innerHTML = '';
  if(myCardData.length === 0){
    wrap.innerHTML = '<div style="text-align:center;color:var(--sub);padding:20px">No cards selected</div>';
    return;
  }
  myCardData.forEach(card => {
    wrap.innerHTML += buildCardHTML(card.card_data, drawn, card.card_index);
  });
}

function buildCardHTML(cardData, drawn, cardIndex){
  const drawnSet = new Set(drawn);
  let html = `<div class="bingo-card-box">
    <div class="bcard-header"><div class="bcard-title">🎴 Card #${cardIndex}</div></div>
    <div class="bcol-headers">
      <div class="bcol-h">B</div><div class="bcol-h">I</div>
      <div class="bcol-h">N</div><div class="bcol-h">G</div><div class="bcol-h">O</div>
    </div>`;
  cardData.forEach(row => {
    html += '<div class="brow">';
    row.forEach(n => {
      if(n === 0)              html += '<div class="bcell free">FREE</div>';
      else if(drawnSet.has(n)) html += `<div class="bcell hit">⭐</div>`;
      else                     html += `<div class="bcell">${n}</div>`;
    });
    html += '</div>';
  });
  html += '</div>';
  return html;
}

// ── Show winner screen ────────────────────────────────
function showWinner(res){
  if(pollTimeout) clearTimeout(pollTimeout);
  const wc = document.getElementById('winnerCards');
  wc.innerHTML = (res.winners || []).map(w => `
    <div class="w-card">
      <div class="w-name">👤 ${w.name}</div>
      <div style="font-size:11px;color:var(--sub)">Card #${w.card_index}</div>
      <div class="w-prize">+${w.prize} ETB 💰</div>
    </div>`).join('');
  if(res.winners && res.winners.length === 0){
    wc.innerHTML = '<div style="color:var(--sub);text-align:center">No winner this round</div>';
  }
  goPage('pg-winner');
  let nc = 5;
  document.getElementById('nextNum').textContent = nc;
  const ni = setInterval(() => {
    nc--;
    document.getElementById('nextNum').textContent = Math.max(0, nc);
    if(nc <= 0){
      clearInterval(ni);
      state.myCards = [];
      state.gameId  = null;
      myCardData    = [];
      loadUser().then(() => { renderApp(); goPage('pg-stake'); });
    }
  }, 1000);
}

// ── Ball letter helper ────────────────────────────────
function ballLetter(n){
  if(n <= 15) return 'B';
  if(n <= 30) return 'I';
  if(n <= 45) return 'N';
  if(n <= 60) return 'G';
  return 'O';
}

// ── Admin panel ───────────────────────────────────────
function showAdminPanel(){
  const pass = prompt('Admin Password:');
  if(pass !== 'nefbingo2026'){ alert('Wrong password!'); return; }
  window.open('/admin', '_blank');
}

// ── App startup ───────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  buildStakeGrid();
  buildDepAmtGrid();
  await loadUser(); //retry once
  renderApp();
  goPage('pg-home');
});
