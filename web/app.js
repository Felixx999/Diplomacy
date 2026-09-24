// Депеша — интерфейс прототипа.
// Ни одно число из движка не показывается сырым: сервер отдаёт деления
// шкалы, здесь они превращаются в полосы и слова.

const $ = s => document.querySelector(s);
const api = {
  get: async (p) => (await fetch('/api' + p)).json(),
  post: async (p, b) => (await fetch('/api' + p, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(b || {})
  })).json(),
};

let TAB = 'dash';
let LANG = 'ru';
let S = {};                       // словарь подписей с сервера

// Подпись по ключу. Нет перевода — показываем ключ, чтобы пропуск было
// видно сразу, а не искать его глазами по экрану.
function T(key, params) {
  let v = S[key] || key;
  if (params) for (const [k, x] of Object.entries(params))
    v = v.replace(new RegExp('\\{' + k + '\\}', 'g'), x);
  return v;
}
let SEL = null;
let DATA = {};

const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function flagImg(o, w) {
  if (o && o.flag_url)
    return `<img class="flag" src="${o.flag_url}" alt="" width="${w || 22}">`;
  return (o && o.flag) || '';
}

function ico(url, size) {
  return url ? `<img class="ico" src="${url}" alt="" width="${size || 17}">` : '';
}

function meter(b, tone, sm) {
  if (!b) return '';
  let p = '';
  for (let i = 1; i <= b.steps; i++) p += `<i class="${i <= b.step ? 'on' : ''}"></i>`;
  return `<span class="meter ${tone || ''} ${sm ? 'sm' : ''}">${p}</span>`;
}
function reading(b, tone) {
  return b ? meter(b, tone) + `<span class="word">${esc(b.label)}</span>` : '';
}
function tone(b) {
  if (!b) return '';
  const f = b.step / b.steps;
  return f <= 0.3 ? 'bad' : (f <= 0.5 ? 'warn' : '');
}

function toast(msg) {
  Audio_.play('notify');
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 2200);
}

// --- навигация -----------------------------------------------------------

const ICONS = {
  dash: 'M3 12h4l3-8 4 16 3-8h4',
  cabinet: 'M4 20V9l8-5 8 5v11M9 20v-6h6v6',
  course: 'M4 6h16M4 12h10M4 18h13M18 10v4',
  world: 'M12 3a9 9 0 100 18 9 9 0 000-18zM3 12h18M12 3c3 4 3 14 0 18M12 3c-3 4-3 14 0 18',
  doss: 'M5 4h9l5 5v11H5zM14 4v5h5',
};
const TABS = ['dash', 'cabinet', 'course', 'world', 'doss'];

function nav() {
  $('nav').innerHTML = TABS.map(id =>
    `<button data-tab="${id}" class="${TAB === id ? 'on' : ''}">
      <svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round">
        <path d="${ICONS[id]}"/></svg>${T('tab.' + id)}</button>`).join('')
    + '<span class="sp"></span>';
  $('nav').querySelectorAll('button').forEach(b =>
    b.onclick = () => { Audio_.play('tab'); TAB = b.dataset.tab; render(); });
}

// --- разделы -------------------------------------------------------------

// Пульт — рабочий стол. Слева бумаги, требующие решения; в центре
// штурманский стол с графом отношений; справа кабинет в лицах.
const SEEN = new Set();          // депеши, уже лежавшие на столе

async function viewDash() {
  const [d, cab] = await Promise.all([api.get('/dashboard'), api.get('/cabinet')]);
  DATA.dash = d;
  if (d.ambience) Audio_.set(d.ambience);
  header(d);

  const cables = d.agenda.length ? d.agenda.map(cableItem).join('')
    : `<div class="quiet">${T('dash.quiet')}</div>`;
  d.agenda.forEach(i => SEEN.add(i.id));

  const hot = (d.hot || []).map(h => `<div class="it">
      <span class="nm">${esc(h.name)}</span>
      <span class="st">${esc(h.stage || h.label)}</span>
      ${meter(h, tone(h, true), true)}</div>`).join('');

  const roster = cab.ministries.map(m => m.minister
    ? `<div class="m" data-min="${m.id}" title="${esc(m.short)}: ${esc(m.minister)}">
         ${m.face || ''}<span class="tip">${esc(m.short)}</span></div>`
    : `<div class="m vac" data-min="${m.id}" title="${esc(m.short)}: ${T('cab.vacant')}">+</div>`
  ).join('');

  $('#view').innerHTML = `<div class="desk">
    <section><h2>${T('dash.agenda')}</h2>${cables}</section>

    <section class="mid">
      <h2>${T('dash.world')}</h2>
      <div class="table">${graphSvg(d.graph)}
        <div class="legend">
          <span><i style="background:var(--cool)"></i>${T('dash.legend_warm')}</span>
          <span><i style="background:var(--warm)"></i>${T('dash.legend_cold')}</span>
          <span><i style="background:var(--desk-muted);height:0;border-top:2px dashed var(--desk-muted)"></i>${T('dash.legend_pact')}</span>
          <span style="margin-left:auto">${T('dash.graph_note')}</span>
        </div>
      </div>
      ${hot ? `<div class="hot panel"><h2>${T('dash.hot')}</h2>${hot}</div>` : ''}
    </section>

    <section>
      <h2>${T('dash.cabinet')}</h2>
      <div class="roster">${roster}</div>
      <div class="panel stack" style="margin-top:12px">
        <div class="stat"><span class="lb">${T('dash.vacant_n', {n: cab.vacant})}</span></div>
        ${d.state.map(s => `<div class="stat"><span class="lb">${esc(s.label)}</span>
          ${meter(s, tone(s), true)}</div>`).join('')}
      </div>
    </section>
  </div>`;
  bindAgenda();
  bindGraph();
  $('#view').querySelectorAll('.roster [data-min]').forEach(el =>
    el.onclick = () => openShortlist(el.dataset.min, null));
}

// Верхняя полоса: кто мы, когда, главные показатели и обстановка.
function header(d) {
  $('#who').innerHTML = `${d.flag_url ? `<img class="flag" src="${d.flag_url}" alt="">` : ''}
    <div><h1>${esc(d.country)}</h1>
    <div class="when">${esc(d.date)}, ${T('ui.turn', {turn: d.turn})}</div></div>`;
  $('#gauges').innerHTML = d.state.slice(0, 4).map(s =>
    `<div class="gauge"><span class="lb">${esc(s.label)}</span>${meter(s, tone(s), true)}</div>`
  ).join('');
  const a = d.ambience || {};
  const k = a.crisis > 0.6 ? 'crisis' : (a.tension > 0.5 ? 'tense' : 'calm');
  $('#air').className = 'air ' + k;
  $('#air').innerHTML = `<i></i>${T('air.' + k)}`;
}

// Депеша: бумага с маршрутом, штампом срочности, участниками и выбором.
function cableItem(i) {
  const sc = i.scene || {};
  const u = i.urgency || 0;
  const stamp = u >= 0.7 ? `<span class="stamp">${T('stamp.urgent')}</span>`
    : u >= 0.5 ? `<span class="stamp">${T('stamp.important')}</span>`
    : `<span class="stamp soft">${T('stamp.info')}</span>`;
  const faces = (sc.figures || []).map(f =>
    `<div class="fig"><div class="ph">${
        f.photo ? `<img src="${f.photo}" alt="">` : f.face}</div>
      <div class="nm">${esc(f.name)}</div>
      <div class="rl">${esc(f.role)}</div></div>`).join('');
  const clip = sc.clip ? (sc.clip.endsWith('.svg')
      ? `<img class="clip" src="${sc.clip}" alt="">`
      : `<video class="clip" src="${sc.clip}" autoplay muted loop playsinline></video>`) : '';
  return `<article class="cable ${SEEN.has(i.id) ? '' : 'new'}" style="--tint:${sc.tint || 'var(--paper-line)'}">
    ${stamp}
    <div class="route"><span>${ico(sc.icon, 13)}${esc(sc.theme || i.area)}</span>
      <span>${esc(i.source)}</span></div>
    <h3>${esc(i.title)}</h3>
    ${clip}
    ${faces ? `<div class="scene">${faces}</div>` : ''}
    <p>${esc(i.body)}</p>
    <div class="choices">${i.choices.map((c, n) => `
      <button class="choice" data-item="${esc(i.id)}" data-ch="${n}"
        ${c.blocked ? 'disabled' : ''}>${esc(c.label)}
        <span class="hint">${esc(c.blocked || c.hint)}</span></button>`).join('')}
    </div></article>`;
}

function bindAgenda() {
  $('#view').querySelectorAll('[data-ch]').forEach(b => b.onclick = async () => {
    const item = DATA.dash.agenda.find(x => x.id === b.dataset.item);
    const ch = item.choices[+b.dataset.ch];
    if (ch.effect === 'goto_cabinet') { TAB = 'cabinet'; return render(); }
    if (ch.effect === 'package' && ch.params && ch.params.other) {
      return openPackage(ch.params.other, ch.params.type, 60);
    }
    if (ch.effect === 'negotiate' && ch.params && ch.params.other) {
      return openNegotiation(ch.params.other, ch.params.type || 'tariffs');
    }
    const r = await api.post('/act', {effect: ch.effect, params: ch.params});
    Audio_.tick(r.ok === false ? 'bad' : 'good');
    toast(r.note || r.label || 'принято');
    render();
  });
}

// Граф на тёмном штурманском столе. Своя страна — латунь, враждебные —
// охра; размер узла — вес страны. Подписи только у держав, чтобы стол не
// превращался в кашу из тридцати двух надписей.
function graphSvg(g) {
  const W = 640, H = 380;
  const pos = {};
  g.nodes.forEach(n => {
    pos[n.code] = [36 + (n.lon + 180) / 360 * (W - 72),
                   30 + (90 - n.lat) / 180 * (H - 70)];
  });
  let grid = '';
  for (let x = 36; x <= W - 36; x += (W - 72) / 8)
    grid += `<line x1="${x.toFixed(0)}" y1="18" x2="${x.toFixed(0)}" y2="${H - 22}" stroke="#1E3140" stroke-width="1"/>`;
  for (let y = 30; y <= H - 40; y += (H - 70) / 5)
    grid += `<line x1="24" y1="${y.toFixed(0)}" x2="${W - 24}" y2="${y.toFixed(0)}" stroke="#1E3140" stroke-width="1"/>`;

  const edges = g.edges.map(e => {
    const A = pos[e.a], B = pos[e.b];
    if (!A || !B) return '';
    const col = e.tone === 'warm' ? '#4C8DB0' : '#C08A3E';
    const dash = e.alliance === 'defense' ? '5 3' : (e.alliance === 'entente' ? '2 3' : '');
    return `<line x1="${A[0].toFixed(1)}" y1="${A[1].toFixed(1)}" x2="${B[0].toFixed(1)}" y2="${B[1].toFixed(1)}"
      stroke="${col}" stroke-width="${(0.6 + e.weight * 2.2).toFixed(1)}"
      stroke-dasharray="${dash}" opacity="${(0.18 + e.strength * 0.55).toFixed(2)}"/>`;
  }).join('');

  const nodes = g.nodes.map(n => {
    const [x, y] = pos[n.code];
    const r = 3.5 + n.power.step * 2.4;
    const hostile = n.relation && n.relation.step <= 2;
    const fill = n.me ? '#B8975A' : (hostile ? '#C08A3E' : '#253442');
    const ring = n.me ? '#E3C98F' : (hostile ? '#C08A3E' : '#6F8597');
    return `<g data-code="${n.code}"><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r.toFixed(1)}"
      fill="${fill}" stroke="${ring}" stroke-width="${n.me ? 2 : 1}">
      <title>${esc(n.name)}</title></circle>
      ${n.tier === 'A' || n.me ? `<text x="${x.toFixed(1)}" y="${(y + r + 11).toFixed(1)}"
        text-anchor="middle" ${n.me ? 'style="fill:#E3C98F"' : ''}>${n.code}</text>` : ''}</g>`;
  }).join('');

  return `<svg class="graph" viewBox="0 0 ${W} ${H}" role="img"
    aria-label="${esc(T('dash.graph_note'))}">${grid}${edges}${nodes}</svg>`;
}

function bindGraph() {
  $('#view').querySelectorAll('[data-code]').forEach(g => g.onclick = () => {
    SEL = g.dataset.code;
    if (SEL !== DATA.dash.player) { TAB = 'doss'; render(); }
  });
}

async function viewCabinet() {
  const d = await api.get('/cabinet');
  $('#view').innerHTML = `<h2>${T('cab.title')}, ${T('cab.vacancies', {n: d.vacant, total: d.ministries.length})}</h2>
    <div class="grid mins">${d.ministries.map(m => `
      <div class="min ${m.minister ? '' : 'vacant'}" data-min="${m.id}">
        <div class="face">${m.face || '+'}</div>
        <div>
          <h3>${ico(m.icon)}${esc(m.short)}</h3>
          <div class="note">${esc(m.note)}</div>
          <span class="who ${m.minister ? '' : 'none'}">${
            m.minister ? esc(m.minister) : T('cab.vacant')}</span>
          ${m.fit ? meter(m.fit, tone(m.fit), true) + `<span class="word">${T('cab.fit')}</span>` : ''}
        </div>
      </div>`).join('')}</div>`;
  $('#view').querySelectorAll('[data-min]').forEach(el =>
    el.onclick = () => openShortlist(el.dataset.min, null));
}

async function viewCourse() {
  const d = await api.get('/course');
  $('#view').innerHTML = `<h2>${T('tab.course')}</h2>
    <div class="card row" style="margin-bottom:12px">
      <span class="small">${T('course.capital')}</span>${reading(d.capital, tone(d.capital))}
    </div>
    ${d.branches.map(b => `<details class="branch">
      <summary>${ico(b.icon)}${esc(b.name)}<span class="small">${
        b.minister ? esc(b.minister) : T('course.no_minister')}</span></summary>
      ${b.levers.map(l => `<div class="lever">
        <div class="top"><span style="min-width:220px">${esc(l.name)}</span>
          <input type="range" min="0" max="100" step="1" value="${l.value}"
            data-pol="${l.id}"><span class="val">${l.value}</span></div>
        <div class="cares">${l.cares.map(c =>
          `<span class="${c.for ? 'up' : 'dn'}">${c.for ? '▲' : '▼'} ${esc(c.group)}</span>`
        ).join('')}</div></div>`).join('')}
    </details>`).join('')}`;
  $('#view').querySelectorAll('[data-pol]').forEach(inp => {
    inp.oninput = () => { inp.nextElementSibling.textContent = inp.value; };
    inp.onpointerup = () => Audio_.play('slider');
    inp.onchange = async () => {
      await api.post('/act', {effect: 'set_policy',
        params: {id: inp.dataset.pol, value: inp.value}});
      toast('курс изменён');
    };
  });
}

async function viewWorld() {
  const d = await api.get('/world');
  $('#view').innerHTML = `<h2>${T('world.directions')}</h2>
    <div class="grid dirs" style="margin-bottom:16px">${d.directions.map(x => `
      <div class="dir ${x.works ? '' : 'off'}">
        <h3>${ico(x.icon)} ${esc(x.name)}</h3>
        <div class="row"><input type="range" min="0" max="100" value="${x.effort}"
          data-dir="${x.id}" style="flex:1"><span class="val">${x.effort}</span></div>
        <div class="small">${esc(x.ministry)}</div>
        <div class="small">${x.works ? esc(x.note) : esc(x.blocked)}</div>
      </div>`).join('')}</div>
    ${(d.blocs && d.blocs.length) ? `<h2>${T('world.blocs')}</h2>
    <div class="grid dirs" style="margin-bottom:16px">${d.blocs.map(b =>
      `<div class="dir" style="text-align:center">
        <div style="line-height:0;margin-bottom:6px">${b.emblem}</div>
        <div style="font-size:13px">${esc(b.patron)}${b.mine ? ', ' + T('world.ours') : ''}</div>
        <div class="small">клиентов: ${b.clients}</div></div>`).join('')}</div>` : ''}
    <h2>${T('world.embassies')}</h2>${d.vacant ? `<p class="small" style="margin:-4px 0 8px">${T('dash.vacant_n', {n: d.vacant})}</p>` : ''}
    <table class="posts">${d.posts.map(p => `<tr data-post="${p.code}">
      <td style="width:180px">${flagImg(p, 22)}${esc(p.name)}
        <div class="cl">${esc(p.climate)}</div></td>
      <td>${p.face ? `<span class="mini">${p.face}</span>` : ''}${
        p.envoy ? esc(p.envoy) : `<span style="color:#D06A5E">${T('world.no_envoy')}</span>`}</td>
      <td style="width:110px">${p.fit ? meter(p.fit, tone(p.fit), true) : ''}</td>
      <td style="width:110px">${meter(p.relation, tone(p.relation), true)}</td>
    </tr>`).join('')}</table>`;
  $('#view').querySelectorAll('[data-post]').forEach(tr =>
    tr.onclick = () => openShortlist(null, tr.dataset.post));
  $('#view').querySelectorAll('[data-dir]').forEach(inp => {
    inp.oninput = () => { inp.nextElementSibling.textContent = inp.value; };
    inp.onpointerup = () => Audio_.play('slider');
    inp.onchange = async () => {
      const w = {};
      $('#view').querySelectorAll('[data-dir]').forEach(x => w[x.dataset.dir] = +x.value);
      await api.post('/act', {effect: 'set_effort', params: {weights: w}});
      render();
    };
  });
}

async function viewDoss() {
  const code = SEL || 'USA';
  const d = await api.get('/dossier?code=' + code);
  const colors = ['#3F7A5E', '#2E6E8E', '#B07D2B', '#69746F', '#7F77DD'];
  const stack = d.economy.basket.map((b, i) =>
    `<i style="width:${b.share}%;background:${colors[i % 5]}"></i>`).join('');
  const legend = d.economy.basket.map((b, i) =>
    `<span><i style="background:${colors[i % 5]}"></i>${esc(b.name)} ${b.share}%</span>`).join('');
  $('#view').innerHTML = `<div class="doss">
    <div>
      <div class="dossier-head">${flagImg(d, 42)}
        <div><div class="t">${esc(d.name)}</div>
        <div class="s">${esc(d.power.label)}, ${esc(d.regime)}</div></div></div>
      ${d.recognition ? `<p class="small" style="margin:4px 0 0">${esc(d.recognition)}</p>` : ''}
      <div class="terrain">${d.terrain || ''}</div>
      <div class="panel" style="margin-bottom:12px">
        <div class="small">${T('doss.sells')}</div>
        <div class="bar-stack">${stack}</div>
        <div class="legend">${legend}</div>
        ${d.power_parts ? `<div class="small" style="margin-top:10px">
          Из чего складывается вес: ${d.power_parts.map(x =>
            esc(x.name) + ' ' + x.share + '%').join(', ')}</div>` : ''}
        <table class="kv" style="margin-top:12px">
          <tr><td>${T('doss.gdp')}</td><td>${d.economy.gdp} млрд</td></tr>
          <tr><td>${T('doss.percap')}</td><td>${d.economy.per_capita} долл</td></tr>
          <tr><td>${T('doss.rate')}</td><td>${d.economy.currency}</td></tr>
          <tr><td>${T('doss.balance')}</td><td>${d.economy.balance} млрд</td></tr>
          <tr><td>${T('doss.buyers')}</td><td>${
            d.economy.to.map(t => esc(t[0])).join(', ') || '—'}</td></tr>
        </table>
      </div>
      ${d.disputes.length ? `<div class="panel" style="margin-bottom:12px">
        <div class="small">${T('doss.disputes')}</div>${d.disputes.map(x =>
          `<div class="row" style="margin-top:6px"><span style="flex:1">${esc(x.name)}</span>
           ${meter(x.heat, 'bad', true)}<span class="word">${esc(x.heat.label)}</span></div>`
        ).join('')}</div>` : ''}
      ${d.deals.length ? `<div class="panel"><div class="small">${T('doss.deals')}</div>
        ${d.deals.map(x => `<div class="row" style="margin-top:6px">
          <span class="small" style="flex:1">${esc(x.label)} — ${x.progress}%</span>
          <button class="btn" style="padding:3px 9px;font-size:12px"
            data-cancel="${esc(d.code)}">${T('doss.cancel')}</button></div>`).join('')}</div>` : ''}
    </div>
    <div>
      <div class="panel" style="margin-bottom:12px">
        <div class="small">${T('doss.relations')}</div>
        <table class="kv">
          <tr><td>${T('doss.alignment')}</td><td>${reading(d.bands.alignment)}</td></tr>
          <tr><td>${T('doss.threat')}</td><td>${reading(d.bands.threat, 'bad')}</td></tr>
          <tr><td>${T('doss.trust')}</td><td>${reading(d.bands.trust)}</td></tr>
          <tr><td>${T('doss.intel')}</td><td>${reading(d.bands.intel)}</td></tr>
        </table>
        <div class="small" style="margin-top:8px">Посол: ${
          d.envoy ? esc(d.envoy) : 'не назначен'}</div>
      </div>
      <div class="panel">
        <div class="small" style="margin-bottom:6px">${T('doss.issues')}</div>
        ${d.issues.length ? d.issues.map(i => `<button class="btn"
          style="width:100%;margin-bottom:6px;text-align:left"
          data-neg="${i.id}">${ico(i.icon)} ${esc(i.name)}
          <span class="hint" style="display:block;font-size:11px;color:var(--muted)">
          простор для торга: ${esc(i.zone.label)}</span></button>`).join('')
          : `<div class="small">${T('doss.nothing')}</div>`}
      </div>
    </div></div>`;
  $('#view').querySelectorAll('[data-cancel]').forEach(b =>
    b.onclick = async () => {
      const r = await api.post('/act', {effect: 'cancel_deal',
        params: {other: b.dataset.cancel}});
      toast(r.note); render();
    });
  $('#view').querySelectorAll('[data-neg]').forEach(b =>
    b.onclick = () => openNegotiation(code, b.dataset.neg));
}

// --- наложения -----------------------------------------------------------

function veil(html) {
  Audio_.play('open');
  const el = document.createElement('div');
  el.className = 'veil';
  el.innerHTML = `<div class="sheet">${html}</div>`;
  el.onclick = e => { if (e.target === el) { Audio_.play('close'); el.remove(); } };
  document.body.appendChild(el);
  return el;
}

async function openShortlist(ministry, target) {
  const q = ministry ? '?ministry=' + ministry : '?target=' + target;
  const d = await api.get('/shortlist' + q);
  const box = veil(`<h2>${ministry ? T('cab.appoint') : T('world.send')}</h2>
    <div class="cands">${d.candidates.map(c => `
      <div class="cand" data-who="${esc(c.id)}">
        <div style="float:right;margin-left:8px">${c.face || ''}</div>
        <div class="nm">${esc(c.name)}</div>
        <div class="ar">${esc(c.archetype)}</div>
        ${meter(c.fit, tone(c.fit), true)}<span class="word">${T('cab.fit')}</span>
        <div class="wh">${esc(c.why)}</div>
      </div>`).join('')}</div>
    <p class="small">Назначение стоит влияния.</p>`);
  box.querySelectorAll('[data-who]').forEach(el => el.onclick = async () => {
    const r = await api.post('/act', ministry
      ? {effect: 'appoint', params: {ministry, who: el.dataset.who}}
      : {effect: 'send_envoy', params: {other: target, who: el.dataset.who}});
    box.remove();
    toast(r.why || r.note || 'назначено');
    render();
  });
}

async function openPackage(other, type, level) {
  const d = await api.get(`/package?other=${other}&type=${type}&level=${level || 60}`);
  if (!d.ok && !d.legs) {
    return veil(`<h2>Пакет не собрался</h2>
      <p style="font:400 14px/1.7 Spectral,Georgia,serif">${esc(d.note || '')}</p>`);
  }
  const box = veil(`<h2>Пакет со встречной уступкой</h2>
    <p class="small">${d.solo_fails
      ? 'В одиночку этот вопрос решения не имеет. Пакет — единственный путь.'
      : 'Вопрос решается и отдельно, но пакет выгоднее.'}</p>
    <div class="grid" style="grid-template-columns:1fr 1fr;margin:12px 0">
      ${d.legs.map(l => `<div class="panel">
        <div class="small">${l.mine ? 'уступаем мы' : 'уступают они'}</div>
        <div style="font-size:14px;margin-top:4px">${ico(l.icon)}${esc(l.name)}</div>
        <div style="font-size:22px;font-weight:500">${l.level}</div></div>`).join('')}
    </div>
    <div class="opp">${esc(d.home)}</div>
    <table class="kv" style="margin-top:8px">${d.detail.map(g =>
      `<tr><td>${esc(g.group)}</td><td>${g.stays ? 'остаются' : 'уходят'}</td></tr>`
      ).join('')}</table>
    <div class="row" style="margin-top:14px;gap:8px">
      <button class="btn go" id="pk" ${d.ok ? '' : 'disabled'}>${T('pkg.sign')}</button>
      <button class="btn" id="cancel">${T('pkg.decline')}</button>
      ${d.ok ? '' : `<span class="small">${esc(d.why || '')}</span>`}
    </div>`);
  box.querySelector('#pk').onclick = async () => {
    const r = await api.post('/act', {effect: 'sign_package',
      params: {other, type, level: level || 60}});
    box.remove(); toast(r.note); render();
  };
  box.querySelector('#cancel').onclick = () => box.remove();
}

async function openNegotiation(other, type) {
  const d = await api.get(`/negotiation?other=${other}&type=${type}`);
  const pts = d.points;
  const mid = pts.length ? pts[Math.floor(pts.length / 2)] : d.ceiling;
  const box = veil(`
    <h2>${T('neg.title', {country: esc(d.name)})}</h2>
    <div class="row" style="gap:8px;margin-bottom:4px">
      ${d.types.map(t => `<button class="btn ${t[0] === d.type ? 'go' : ''}"
        data-t="${t[0]}">${esc(t[1])}</button>`).join('')}
    </div>
    <div class="track">
      <i class="t-home" style="width:${d.ceiling}%"></i>
      <i class="t-est" style="left:${d.est_lo}%;width:${Math.max(2, d.est_hi - d.est_lo)}%"></i>
      ${pts.length ? `<i class="t-ok" style="left:${pts[0]}%;width:${
        Math.max(2, pts[pts.length - 1] - pts[0])}%"></i>` : ''}
      <i class="t-pin" id="pin" style="left:${mid}%"></i>
    </div>
    <div class="scale"><span>дома пройдёт до ${d.ceiling}</span>
      <span>партнёр просит ${d.est_lo}–${d.est_hi}</span></div>
    <div class="row" style="margin:14px 0">
      <span class="small" style="min-width:70px">Уступка</span>
      <input type="range" min="0" max="100" value="${mid}" id="lvl" style="flex:1">
      <span class="val" id="lvlv">${mid}</span>
    </div>
    <div class="opp">${esc(d.why)}${d.opposition.length ? '<br>' +
      d.opposition.map(o => `<b>${esc(o.group)}</b> уходят на ${o.leaves_at}`).join(', ') : ''}</div>
    <p class="small" style="margin-top:10px">Разведка: ${esc(d.intel.label)}.
      Простор для торга: ${esc(d.zone.label)}.</p>
    <div class="row" style="margin-top:14px;gap:8px">
      <button class="btn go" id="sign" ${pts.length ? '' : 'disabled'}>${T('neg.sign')}</button>
      <button class="btn" id="spy">${T('neg.spy', {cost: d.intel_cost})}</button>
      <button class="btn" id="pack">${T('neg.package')}</button>
      <button class="btn" id="walk">${T('neg.walk')}</button>
      ${pts.length ? '' : `<span class="small">${esc(d.reason || '')}${
        d.misjudged ? '<br>' + esc(d.misjudged) : ''}</span>`}
    </div>`);
  const lvl = box.querySelector('#lvl');
  lvl.oninput = () => {
    box.querySelector('#lvlv').textContent = lvl.value;
    box.querySelector('#pin').style.left = lvl.value + '%';
  };
  box.querySelectorAll('[data-t]').forEach(b => b.onclick = () => {
    box.remove(); openNegotiation(other, b.dataset.t);
  });
  box.querySelector('#sign').onclick = async () => {
    await api.post('/act', {effect: 'sign',
      params: {other, type: d.type, level: +lvl.value}});
    box.remove(); Audio_.play('sign'); toast('соглашение подписано'); render();
  };
  box.querySelector('#spy').onclick = async () => {
    await api.post('/act', {effect: 'spy', params: {other, spend: d.intel_cost}});
    box.remove(); openNegotiation(other, d.type);
  };
  box.querySelector('#pack').onclick = () => {
    box.remove(); openPackage(other, d.type, +lvl.value);
  };
  box.querySelector('#walk').onclick = () => box.remove();
}

function openEnding(e) {
  veil(`<h2>${esc(e.title)}</h2>
    <p style="font:400 15px/1.7 Spectral,Georgia,serif">${esc(e.body)}</p>
    <p class="small">Ваш мир разошёлся с нашей хронологией на
      ${Math.round(e.share * 100)}%.</p>
    <table class="kv">${e.divergence.map(d =>
      `<tr><td>${esc(d[0])}</td><td>${esc(d[2])}</td></tr>`).join('')}</table>
    ${e.highlights.length ? `<p class="small" style="margin-top:12px">${T('end.changed')}:</p>`
      + e.highlights.map(h => `<p style="font:400 14px/1.6 Spectral,Georgia,serif;
        margin:0 0 4px">${esc(h)}</p>`).join('') : ''}
    <p class="small" style="margin-top:14px">${T('end.again')}</p>`);
}

function openReceipt(r) {
  veil(`<h2>${T('month.title', {date: esc(r.date)})}</h2>
    ${r.lines.map(l => `<p style="font:400 14px/1.7 Spectral,Georgia,serif;
      margin:0 0 6px">${esc(l)}</p>`).join('')}
    ${r.timeline ? `<div class="panel" style="margin-top:12px;
      border-left:3px solid var(--warm)">
      <div class="small" style="margin-bottom:4px">${T('month.real')}</div>
      <p style="font:italic 400 14px/1.6 Spectral,Georgia,serif;margin:0">
        ${esc(r.timeline.text)}</p></div>` : ''}
    ${(r.who && r.who.length) ? `<div class="panel" style="margin-top:12px">
      ${r.who.map(w => `<div class="small">${esc(w)}</div>`).join('')}
      ${(r.moves || []).map(m => `<div class="small">${esc(m)}</div>`).join('')}
      </div>` : ''}
    <p class="small" style="margin-top:12px">Нажмите вне окна, чтобы продолжить.</p>`);
}

// --- поиск ---

// Строка поиска открывается по Ctrl+K или по кнопке и находит что
// угодно: страну, министерство, рычаг, группу, вопрос, человека,
// действующее соглашение. От запроса до нужного экрана один клик —
// это и делает глубину переносимой.

let SEARCH_TIMER = null;

function openSearch() {
  const box = veil(`
    <h2>${T('search.title')}</h2>
    <input id="q" placeholder="страна, министерство, рычаг, группа, человек"
      style="width:100%;padding:9px 11px;font:400 15px inherit;
      border:1px solid var(--rule);border-radius:3px;background:var(--panel)">
    <div id="res" style="margin-top:10px"></div>
    <p class="small" style="margin-top:10px">${T('search.enter')}</p>`);
  const q = box.querySelector('#q');
  q.focus();
  let rows = [];

  async function run() {
    if (q.value.trim().length < 2) { box.querySelector('#res').innerHTML = ''; return; }
    const d = await api.get('/search?q=' + encodeURIComponent(q.value));
    rows = d.results;
    box.querySelector('#res').innerHTML = rows.length ? rows.map((r, i) =>
      `<div class="hit" data-i="${i}">
        ${r.icon ? (r.icon.startsWith('/flags') ? `<img class="flag" src="${r.icon}" width="20">` : ico(r.icon)) : ''}
        <span class="lb">${esc(r.label)}</span>
        <span class="kd">${esc(r.kind)}</span>
        <span class="nt">${esc(r.note || '')}</span></div>`).join('')
      : `<div class="small">${T('search.empty')}</div>`;
    box.querySelectorAll('.hit').forEach(el =>
      el.onclick = () => go(rows[+el.dataset.i]));
  }

  function go(r) {
    if (!r) return;
    Audio_.play('click');
    if (r.tab === 'doss' && r.arg) SEL = r.arg;
    TAB = r.tab;
    box.remove();
    render();
  }

  q.oninput = () => { clearTimeout(SEARCH_TIMER); SEARCH_TIMER = setTimeout(run, 130); };
  q.onkeydown = e => {
    if (e.key === 'Enter') go(rows[0]);
    if (e.key === 'Escape') box.remove();
  };
}

document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault(); openSearch();
  }
});

// --- запуск --------------------------------------------------------------

const VIEWS = {dash: viewDash, cabinet: viewCabinet, course: viewCourse,
               world: viewWorld, doss: viewDoss};

async function render() {
  nav();
  await VIEWS[TAB]();
  if (DATA.dash && TAB !== 'dash') header(DATA.dash);
}

async function openingScreen() {
  const d = await api.get('/openings');
  const box = veil(`<h2 style="font-size:20px">${esc(d.question)}</h2>
    <p class="small" style="margin-bottom:14px">${T('open.note')}</p>
    <div class="cands" style="grid-template-columns:1fr">
      ${d.options.map(o => `<div class="cand" data-op="${esc(o.id)}">
        <div class="nm" style="font-size:15px">${esc(o.label)}</div>
        <div class="ar">${esc(o.body)}</div>
        <div class="wh">${T('open.playing', {country: esc(o.country_name)})}</div>
        <div class="wh">${esc(o.note)}</div>
      </div>`).join('')}
    </div>`);
  box.onclick = null;
  return new Promise(res => {
    box.querySelectorAll('[data-op]').forEach(el => el.onclick = async () => {
      await api.post('/start', {choice: el.dataset.op});
      box.remove(); res();
    });
  });
}

async function setLang(to) {
  const d = await api.get('/lang?to=' + to);
  LANG = d.lang; S = d.strings;
  document.documentElement.lang = LANG;
  $('#lang').textContent = LANG === 'ru' ? 'EN' : 'РУ';
  $('#next').textContent = T('ui.next');
  $('#save').textContent = T('ui.save');
  $('#load').textContent = T('ui.load');
  $('#find').innerHTML = `${T('ui.search')}<kbd>Ctrl K</kbd>`;
}

async function boot() {
  const d = await api.get('/strings');
  LANG = d.lang; S = d.strings;
  $('#lang').onclick = async () => {
    await setLang(LANG === 'ru' ? 'en' : 'ru');
    DATA.dash = await api.get('/dashboard');
    await render();
  };
  await setLang(LANG);
  await openingScreen();
  DATA.dash = await api.get('/dashboard');
  await render();
  $('#find').onclick = openSearch;
  $('#sound').onclick = () => {
    const on = Audio_.toggle();
    $('#sound').textContent = on ? 'Звук вкл' : 'Звук выкл';
    if (on && DATA.dash) Audio_.set(DATA.dash.ambience || {});
  };
  $('#save').onclick = async () => toast((await api.post('/save')).note);
  $('#load').onclick = async () => {
    const r = await api.post('/load');
    toast(r.note);
    if (r.ok) { DATA.dash = await api.get('/dashboard'); await render(); }
  };
  $('#next').onclick = async () => {
    Audio_.play('turn');
    const r = await api.post('/tick', {});
    DATA.dash = await api.get('/dashboard');
    await render();
    if (r.ambience && r.ambience.crisis > 0.6) Audio_.play('alert');
    if (r.ending) openEnding(r.ending);
    else openReceipt(Object.assign({}, r.receipt, {timeline: r.timeline}));
  };
}

boot();
