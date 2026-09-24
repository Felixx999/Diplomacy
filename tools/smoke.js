// Проверка интерфейса целиком.
//
// Пять проверок проекта смотрят в движок и ни одна не открывала
// интерфейс. Поэтому синтаксическая ошибка в app.js прожила несколько
// сессий: сервер исправно отдавал файл, а браузер не мог его разобрать, и
// страница не загружалась вовсе.
//
// Здесь страница поднимается в эмуляторе браузера, скрипты выполняются
// против живого сервера, и проверяется то, что видит человек: первый
// экран, депеши на пульте, все пять разделов, переключение языка.
//
//   node tools/smoke.js http://localhost:8000
//
// Нужен jsdom: npm install jsdom

const {JSDOM} = require('jsdom');
const fs = require('fs');
const path = require('path');

const BASE = process.argv[2] || 'http://localhost:8000';
const WEB = path.join(__dirname, '..', 'web');
const wait = ms => new Promise(r => setTimeout(r, ms));

const results = [];
function check(name, ok, detail) {
  results.push({name, ok, detail});
  console.log(`  ${ok ? 'ок    ' : 'ОШИБКА'} ${name}${detail ? ' — ' + detail : ''}`);
}

(async () => {
  const html = fs.readFileSync(path.join(WEB, 'index.html'), 'utf8')
    .replace(/<script src="[^"]+"><\/script>/g, '')
    .replace(/<link[^>]+>/g, '');
  const errors = [];
  const dom = new JSDOM(html, {runScripts: 'outside-only', url: BASE + '/'});
  const w = dom.window;

  w.fetch = (url, opts) => fetch(new URL(url, BASE), opts);
  w.Audio = function () { return {play: () => Promise.resolve(), volume: 1, currentTime: 0}; };
  w.addEventListener('error', e => errors.push(e.message));
  w.console.error = (...a) => errors.push(a.join(' '));

  // В браузере объявления верхнего уровня из разных скриптов видны друг
  // другу; при раздельном eval — нет. Поэтому скрипты склеиваются в том
  // же порядке, в каком их подключает страница.
  const code = ['audio.js', 'app.js']
    .map(f => fs.readFileSync(path.join(WEB, f), 'utf8')).join('\n;\n');
  try {
    w.eval(code);
    check('скрипты страницы выполняются', true);
  } catch (e) {
    check('скрипты страницы выполняются', false, e.message);
    process.exit(1);
  }

  const $ = s => w.document.querySelector(s);
  const $$ = s => w.document.querySelectorAll(s);

  await wait(900);
  const opening = $$('[data-op]');
  check('первый экран предлагает выбор', opening.length >= 3, `вариантов: ${opening.length}`);
  if (!opening.length) process.exit(1);
  opening[0].click();
  await wait(1500);

  check('верхняя полоса: страна и флаг', !!$('#who h1') && !!$('#who img'),
        $('#who h1') ? $('#who h1').textContent : 'пусто');
  check('верхняя полоса: показатели', $$('#gauges .gauge').length >= 3,
        `полос: ${$$('#gauges .gauge').length}`);
  check('обстановка в мире подписана', ($('#air').textContent || '').trim().length > 0,
        $('#air').textContent.trim());
  const cables = $$('.cable');
  check('депеши на столе', cables.length > 0, `депеш: ${cables.length}`);
  check('у депеши есть штамп', cables.length && !!cables[0].querySelector('.stamp'));
  check('в депеше участники с портретами', $$('.cable .fig').length > 0,
        `лиц: ${$$('.cable .fig').length}`);
  check('граф отношений нарисован', $$('svg.graph circle').length >= 30,
        `узлов: ${$$('svg.graph circle').length}`);
  check('кабинет в лицах', $$('.roster .m').length >= 8, `мест: ${$$('.roster .m').length}`);
  check('в интерфейсе нет сырых дробей',
        !/\d\.\d{2,}/.test($('#view').textContent), '');

  const tabs = ['cabinet', 'course', 'world', 'doss', 'dash'];
  for (const t of tabs) {
    const b = $(`nav [data-tab="${t}"]`);
    if (!b) { check(`раздел ${t}`, false, 'нет кнопки'); continue; }
    b.click();
    await wait(900);
    const txt = $('#view').textContent.trim();
    check(`раздел ${t} открывается`, txt.length > 40, `${txt.length} знаков`);
  }

  const ruTab = $('nav [data-tab="cabinet"]').textContent.trim();
  $('#lang').click();
  await wait(1400);
  const enTab = $('nav [data-tab="cabinet"]').textContent.trim();
  check('язык переключается', ruTab !== enTab, `${ruTab} → ${enTab}`);
  const leftovers = ($('#view').textContent.match(/[а-яё]{4,}/gi) || []);
  check('после переключения русского почти не осталось', leftovers.length < 12,
        `русских слов на экране: ${leftovers.length}` +
        (leftovers.length ? ` (${[...new Set(leftovers)].slice(0, 5).join(', ')})` : ''));

  $('#next').click();
  await wait(1800);
  check('ход проходит и открывается итог месяца', !!$('.veil .sheet'));

  check('ошибок в консоли нет', errors.length === 0,
        errors.length ? errors.slice(0, 2).join(' | ') : '');

  const bad = results.filter(r => !r.ok).length;
  console.log(`\nпроверок ${results.length}, провалено ${bad}`);
  process.exit(bad ? 1 : 0);
})();
