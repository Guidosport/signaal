(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const audio = $('audio');
  const playBtn = $('playBtn');
  const seek = $('seek');
  const speedBtn = $('speed');
  const SPEEDS = [1, 1.25, 1.5, 0.85];
  const POS_KEY = 'signaal.pos.v1';
  const SPEED_KEY = 'signaal.speed.v1';

  let episodes = [];
  let current = null;
  let seeking = false;

  // ---------- opslag (veilig) ----------
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} }
  };

  // ---------- helpers ----------
  const fmt = s => {
    if (!isFinite(s) || s < 0) s = 0;
    const m = Math.floor(s / 60), r = Math.floor(s % 60);
    return `${m}:${String(r).padStart(2, '0')}`;
  };
  const longDate = iso => new Date(iso + 'T08:00:00').toLocaleDateString('nl-NL', { weekday: 'long', day: 'numeric', month: 'long' });
  const shortDate = iso => new Date(iso + 'T08:00:00').toLocaleDateString('nl-NL', { weekday: 'short', day: 'numeric', month: 'short' });
  const isToday = iso => iso === new Date().toLocaleDateString('sv-SE');

  // ---------- laden ----------
  async function load() {
    try {
      const res = await fetch(`episodes/episodes.json?t=${Date.now()}`, { cache: 'no-store' });
      const data = await res.json();
      episodes = (data.episodes || []).slice().sort((a, b) => b.date.localeCompare(a.date));
    } catch {
      episodes = [];
    }
    if (!episodes.length) return renderEmpty();
    select(episodes[0], false);
    renderArchive();
  }

  function renderEmpty() {
    $('epDate').textContent = 'Nog geen aflevering';
    $('epTitle').textContent = 'De eerste uitzending verschijnt om 8:00';
  }

  function select(ep, autoplay) {
    current = ep;
    $('epDate').textContent = (isToday(ep.date) ? 'Vandaag · ' : '') + longDate(ep.date);
    $('epTitle').textContent = ep.title;
    audio.src = ep.audio;
    audio.playbackRate = store.get(SPEED_KEY, 1);
    const saved = store.get(POS_KEY, {})[ep.date];
    if (saved && ep.duration && saved < ep.duration - 5) {
      audio.addEventListener('loadedmetadata', () => { audio.currentTime = saved; }, { once: true });
    }
    $('tDur').textContent = fmt(ep.duration);
    [playBtn, seek, speedBtn, $('back'), $('fwd')].forEach(el => el.disabled = false);
    renderHeadlines();
    renderArchive();
    setMediaSession();
    if (autoplay) audio.play().catch(() => {});
  }

  function renderHeadlines() {
    const list = $('headlines');
    list.innerHTML = '';
    const hs = current.headlines || [];
    $('headlinesCard').hidden = !hs.length;
    hs.forEach(h => {
      const li = document.createElement('li');
      li.textContent = h.text;
      li.addEventListener('click', () => {
        const d = audio.duration || current.duration;
        if (d) { audio.currentTime = h.at * d; if (audio.paused) audio.play().catch(() => {}); }
      });
      list.appendChild(li);
    });
  }

  function renderArchive() {
    const ul = $('archive');
    ul.innerHTML = '';
    const rest = episodes.slice(0, 30);
    $('archiveCard').hidden = rest.length < 2;
    rest.forEach(ep => {
      const li = document.createElement('li');
      if (ep === current) li.className = 'current';
      li.innerHTML = `<button><span class="mini"><svg viewBox="0 0 24 24"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z"/></svg></span>
        <span class="meta"><span class="t"></span><span class="d"></span></span></button>`;
      li.querySelector('.t').textContent = ep.title;
      li.querySelector('.d').textContent = `${shortDate(ep.date)} · ${fmt(ep.duration)}`;
      li.querySelector('button').addEventListener('click', () => {
        select(ep, true);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
      ul.appendChild(li);
    });
  }

  // ---------- bediening ----------
  playBtn.addEventListener('click', () => audio.paused ? audio.play().catch(() => {}) : audio.pause());
  $('back').addEventListener('click', () => { audio.currentTime = Math.max(0, audio.currentTime - 15); });
  $('fwd').addEventListener('click', () => { audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 15); });
  speedBtn.addEventListener('click', () => {
    const i = (SPEEDS.indexOf(audio.playbackRate) + 1) % SPEEDS.length;
    audio.playbackRate = SPEEDS[i];
    store.set(SPEED_KEY, SPEEDS[i]);
    updateSpeed();
  });
  const updateSpeed = () => { speedBtn.textContent = `${String(audio.playbackRate).replace('.', ',')}×`; };
  audio.addEventListener('ratechange', updateSpeed);

  seek.addEventListener('input', () => {
    seeking = true;
    const d = audio.duration || current?.duration || 0;
    $('tCur').textContent = fmt(seek.value / 1000 * d);
    seek.style.setProperty('--p', `${seek.value / 10}%`);
  });
  seek.addEventListener('change', () => {
    const d = audio.duration || current?.duration || 0;
    audio.currentTime = seek.value / 1000 * d;
    seeking = false;
  });

  audio.addEventListener('play', () => document.body.classList.add('playing'));
  audio.addEventListener('pause', () => { document.body.classList.remove('playing'); savePos(); });
  audio.addEventListener('ended', () => {
    document.body.classList.remove('playing');
    const pos = store.get(POS_KEY, {}); delete pos[current.date]; store.set(POS_KEY, pos);
  });
  audio.addEventListener('loadedmetadata', () => { $('tDur').textContent = fmt(audio.duration); });
  audio.addEventListener('timeupdate', () => {
    const d = audio.duration || current?.duration || 0;
    if (!seeking && d) {
      const f = audio.currentTime / d;
      seek.value = Math.round(f * 1000);
      seek.style.setProperty('--p', `${f * 100}%`);
      $('tCur').textContent = fmt(audio.currentTime);
    }
    markHeadline();
    if (Math.floor(audio.currentTime) % 5 === 0) savePos();
  });

  function savePos() {
    if (!current) return;
    const pos = store.get(POS_KEY, {});
    pos[current.date] = audio.currentTime;
    store.set(POS_KEY, pos);
  }

  function markHeadline() {
    const hs = current?.headlines || [];
    const d = audio.duration || current?.duration;
    if (!hs.length || !d) return;
    const f = audio.currentTime / d;
    let idx = -1;
    hs.forEach((h, i) => { if (f >= h.at) idx = i; });
    [...$('headlines').children].forEach((li, i) => li.classList.toggle('now', i === idx && audio.currentTime > 0));
  }

  // ---------- vergrendelscherm ----------
  function setMediaSession() {
    if (!('mediaSession' in navigator)) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: current.title,
      artist: 'Signaal · AI-nieuws',
      album: longDate(current.date),
      artwork: [{ src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' }]
    });
    const set = (a, fn) => { try { navigator.mediaSession.setActionHandler(a, fn); } catch {} };
    set('play', () => audio.play());
    set('pause', () => audio.pause());
    set('seekbackward', () => { audio.currentTime = Math.max(0, audio.currentTime - 15); });
    set('seekforward', () => { audio.currentTime += 15; });
    set('seekto', e => { audio.currentTime = e.seekTime; });
  }

  // ---------- golf-animatie rond de bol ----------
  const cv = $('wave');
  const ctx = cv.getContext('2d');
  const BARS = 72;
  const level = new Float32Array(BARS);
  let energy = 0;

  function draw(t) {
    const playing = !audio.paused;
    energy += ((playing ? 1 : 0.08) - energy) * 0.05;
    const W = cv.width, c = W / 2;
    const r0 = W * 0.31;
    ctx.clearRect(0, 0, W, W);
    for (let i = 0; i < BARS; i++) {
      const a = (i / BARS) * Math.PI * 2 - Math.PI / 2;
      // gelaagde sinussen geven een spraakachtig, organisch ritme
      const n = 0.5 + 0.5 * Math.sin(t / 210 + i * 0.9) * Math.sin(t / 470 - i * 0.33)
        + 0.35 * Math.sin(t / 130 + i * 2.1) * Math.sin(t / 900);
      const target = Math.max(0.05, n) * energy;
      level[i] += (target - level[i]) * 0.25;
      const len = 6 + level[i] * W * 0.13;
      const x1 = c + Math.cos(a) * r0, y1 = c + Math.sin(a) * r0;
      const x2 = c + Math.cos(a) * (r0 + len), y2 = c + Math.sin(a) * (r0 + len);
      const mix = (Math.sin(a + t / 2000) + 1) / 2; // paars ↔ oranje rond de cirkel
      const r = Math.round(124 + (255 - 124) * mix), g = Math.round(58 + (122 - 58) * mix), b = Math.round(237 + (26 - 237) * mix);
      ctx.strokeStyle = `rgba(${r},${g},${b},${0.35 + level[i] * 0.65})`;
      ctx.lineWidth = 6;
      ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }
    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);

  // ---------- start ----------
  updateSpeed();
  load();
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && audio.paused && episodes[0] && !isToday(episodes[0].date)) load();
  });
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
})();
