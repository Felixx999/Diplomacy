// Звук, меняющийся от обстановки.
//
// Вертикальное наслоение: три слоя звучат одновременно, громкость
// каждого зависит от состояния мира. Слои синтезируются на месте, без
// файлов и чужих прав — сейчас важна работающая связь звука с
// состоянием, а не качество тембра. Настоящие записи подставятся позже
// без переделки механики.

const Audio_ = (() => {
  let ctx = null, layers = {}, on = false;

  // Ноты слоёв: основа спокойная, напряжение с дрожью, кризис низкий
  const SPEC = {
    base:    {freqs: [110, 164.81, 220], type: 'sine',     gain: 0.055, lfo: 0.05},
    tension: {freqs: [146.83, 220, 293.66], type: 'triangle', gain: 0.05,  lfo: 0.6},
    crisis:  {freqs: [55, 82.41, 98], type: 'sawtooth', gain: 0.035, lfo: 1.9},
  };

  function build(name) {
    const s = SPEC[name];
    const out = ctx.createGain();
    out.gain.value = 0;
    const filt = ctx.createBiquadFilter();
    filt.type = 'lowpass';
    filt.frequency.value = name === 'crisis' ? 420 : 1100;
    filt.connect(out);
    out.connect(ctx.destination);

    const lfo = ctx.createOscillator();
    const lfoGain = ctx.createGain();
    lfo.frequency.value = s.lfo;
    lfoGain.gain.value = s.gain * 0.4;
    lfo.connect(lfoGain);
    lfo.start();

    s.freqs.forEach((f, i) => {
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = s.type;
      osc.frequency.value = f;
      g.gain.value = s.gain / (i + 1.4);
      lfoGain.connect(g.gain);
      osc.connect(g); g.connect(filt);
      osc.start();
    });
    return out;
  }

  // Записанные петли вытесняют синтез: если файл есть, играет он.
  // Три слоя запускаются одновременно от одной точки, поэтому остаются
  // в фазе — это и есть условие вертикального наслоения.
  const MUSIC = {base: '/music/base.wav', tension: '/music/tension.wav',
                 crisis: '/music/crisis.wav'};
  let tracks = {}, usingFiles = false;

  async function loadMusic() {
    try {
      const bufs = {};
      for (const [name, url] of Object.entries(MUSIC)) {
        const r = await fetch(url);
        if (!r.ok) return false;
        bufs[name] = await ctx.decodeAudioData(await r.arrayBuffer());
      }
      const at = ctx.currentTime + 0.1;
      for (const [name, buf] of Object.entries(bufs)) {
        const src = ctx.createBufferSource();
        const g = ctx.createGain();
        src.buffer = buf; src.loop = true;
        g.gain.value = 0;
        src.connect(g); g.connect(ctx.destination);
        src.start(at);
        tracks[name] = g;
      }
      usingFiles = true;
      return true;
    } catch (e) { return false; }
  }

  async function start() {
    if (ctx) return;
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    on = true;
    if (!(await loadMusic())) {
      Object.keys(SPEC).forEach(n => layers[n] = build(n));
    }
  }

  function set(state) {
    if (!ctx || !on) return;
    const now = ctx.currentTime;
    const bank = usingFiles ? tracks : layers;
    Object.keys(bank).forEach(n => {
      const v = Math.max(0, Math.min(1, state[n] === undefined ? 0 : state[n]));
      bank[n].gain.cancelScheduledValues(now);
      bank[n].gain.setTargetAtTime(v * (usingFiles ? 0.5 : 0.9), now, 1.6);
    });
  }

  function toggle() {
    if (!ctx) { start(); return true; }
    on = !on;
    if (!on) Object.values(usingFiles ? tracks : layers).forEach(l =>
      l.gain.setTargetAtTime(0, ctx.currentTime, 0.4));
    return on;
  }

  // Карта звуков интерфейса. Каждому действию свой отклик, иначе всё
  // сливается в одну пищалку. Если рядом лежит записанный файл, играет
  // он; иначе синтез — так звук работает сразу, а записи подставляются
  // без переделки.
  const SFX = {
    click:   {f: 320, type: 'sine',     len: 0.09, vol: 0.030},
    tab:     {f: 420, type: 'sine',     len: 0.07, vol: 0.024},
    slider:  {f: 260, type: 'triangle', len: 0.05, vol: 0.018},
    good:    {f: 523, type: 'sine',     len: 0.24, vol: 0.045, to: 784},
    bad:     {f: 196, type: 'triangle', len: 0.30, vol: 0.050, to: 147},
    notify:  {f: 660, type: 'sine',     len: 0.36, vol: 0.038, to: 880},
    alert:   {f: 233, type: 'sawtooth', len: 0.52, vol: 0.050, to: 175},
    sign:    {f: 392, type: 'sine',     len: 0.42, vol: 0.045, to: 587},
    turn:    {f: 174, type: 'sine',     len: 0.55, vol: 0.042, to: 261},
    open:    {f: 349, type: 'sine',     len: 0.16, vol: 0.028, to: 466},
    close:   {f: 466, type: 'sine',     len: 0.14, vol: 0.024, to: 349},
  };
  // Отклики интерфейса лежат готовыми файлами; синтез остаётся
  // запасным вариантом, если файла нет.
  const files = {};
  Object.keys(SFX).forEach(n => files[n] = `/sfx/${n}.wav`);
  const cache = {};

  function load(name, url) { files[name] = url; }

  function play(name) {
    if (!ctx || !on) return;
    if (files[name]) {
      let a = cache[name];
      if (!a) { a = cache[name] = new Audio(files[name]); a.volume = 0.45; }
      a.currentTime = 0;
      a.play().catch(() => {});
      return;
    }
    const s = SFX[name] || SFX.click;
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = s.type;
    const t = ctx.currentTime;
    o.frequency.setValueAtTime(s.f, t);
    if (s.to) o.frequency.exponentialRampToValueAtTime(s.to, t + s.len * 0.8);
    g.gain.value = 0.0001;
    o.connect(g); g.connect(ctx.destination);
    g.gain.exponentialRampToValueAtTime(s.vol, t + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t + s.len);
    o.start(t); o.stop(t + s.len + 0.02);
  }

  const tick = play;   // прежнее имя оставлено рабочим

  return {start, set, toggle, tick, play, load,
          get enabled() { return on; }};
})();
