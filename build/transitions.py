#!/usr/bin/env python3
"""Собирает transitions.html — боевую страницу с переключателем анимаций.

Берёт готовый index.html и подменяет в нём блок растворения героя на свой,
с четырьмя вариантами. Всё остальное — вёрстка, шрифты, картинки, афиша —
остаётся ровно тем же, поэтому сравнивать можно честно.

  python3 transitions.py
"""
import pathlib, re

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
MARK = "// [hero-fade]"

PANEL_CSS = """
/* ---------- пульт прототипа ---------- */
.tp{position:fixed;z-index:60;left:50%;transform:translateX(-50%);top:14px;
  width:min(760px,calc(100vw - 24px));background:rgba(6,8,11,.9);
  backdrop-filter:blur(18px);border:1px solid rgba(237,233,225,.18);
  padding:12px 14px 13px;display:grid;gap:9px;font-family:var(--face)}
.tp__r{display:flex;gap:1px;background:rgba(237,233,225,.16)}
.tp__r button{flex:1;background:var(--ink);color:var(--bone);border:0;cursor:pointer;
  padding:9px 6px;font-family:inherit;font-weight:600;font-size:10.5px;
  letter-spacing:.14em;text-transform:uppercase;transition:.14s}
.tp__r button[aria-pressed="true"]{background:var(--ember);color:#0B0603}
.tp__h{margin:0;font-size:11.5px;line-height:1.5;color:#B9BFC8;letter-spacing:.01em}
.tp__h b{color:var(--bone);font-weight:600}
@media (max-width:640px){
  .tp{top:8px;padding:10px}
  .tp__r button{font-size:9px;letter-spacing:.06em;padding:8px 3px}
  .tp__h{font-size:11px}
}
"""

PANEL_HTML = """
<div class="tp">
  <div class="tp__r" role="group" aria-label="Вариант перехода">
    <button type="button" data-v="0" aria-pressed="true">Проявление</button>
    <button type="button" data-v="1" aria-pressed="false">Параллакс</button>
    <button type="button" data-v="2" aria-pressed="false">Вглубь</button>
    <button type="button" data-v="3" aria-pressed="false">На месте</button>
  </div>
  <p class="tp__h" id="tph"></p>
</div>
"""

SCRIPT = """
// ---------- прототип: четыре перехода на выбор ----------
(function(){
  var hero = document.querySelector('.hero');
  if (!hero) return;

  var V = [
    ['Проявление',
     'Снимок едет вверх обычным ходом. Держится непрозрачным, пока нижний край не дойдёт до верха нижней трети экрана, дальше гаснет быстро — за восьмую часть экрана.'],
    ['Параллакс',
     'Снимок отстаёт от прокрутки вдвое: страница едет по нему, а не он вместе с ней. Гаснет так же быстро, но позже — успевает подольше побыть на экране.'],
    ['Вглубь',
     'Снимок едет вверх и одновременно чуть отдаляется — уходит на второй план, а не просто уезжает. Растворение то же, быстрое.'],
    ['На месте',
     'То, что стоит сейчас на сайте: снимок закреплён и растворяется не двигаясь, пока афиша поднимается снизу.']
  ];
  var cur = 0;

  function paint(){
    var vh = innerHeight || document.documentElement.clientHeight || 700,
        y = scrollY, o = 1, shift = 0, scale = 1, from, span = Math.max(60, vh * 0.12);

    if (cur === 0) {
      from = vh / 3;
    } else if (cur === 1) {
      // отстаёт вдвое: нижний край идёт вниз медленнее, значит и порог дальше
      shift = y * 0.45;
      from = vh / 3 + vh * 0.3;
    } else if (cur === 2) {
      from = vh / 3;
      scale = 1 - Math.min(1, y / vh) * 0.07;
    } else {
      shift = y;                      // стоит на месте, компенсируя прокрутку
      from = 0;
      span = Math.max(240, vh * 0.8); // здесь растворение длинное, как сейчас
    }
    o = 1 - Math.min(1, Math.max(0, (y - from) / span));

    hero.style.opacity = o;
    hero.style.visibility = o > 0 ? '' : 'hidden';
    hero.style.transform = (shift || scale !== 1)
      ? 'translate3d(0,' + shift.toFixed(1) + 'px,0) scale(' + scale.toFixed(4) + ')'
      : '';
  }

  function pick(i){
    cur = i;
    [].forEach.call(document.querySelectorAll('.tp__r button'), function(b, k){
      b.setAttribute('aria-pressed', k === i ? 'true' : 'false');
    });
    document.getElementById('tph').innerHTML = '<b>' + V[i][0] + '.</b> ' + V[i][1];
    paint();
  }

  document.querySelector('.tp__r').addEventListener('click', function(e){
    var b = e.target.closest('button');
    if (b) { pick(+b.dataset.v); scrollTo({top:0, behavior:'smooth'}); }
  });

  pick(0);
  addEventListener('scroll', paint, {passive:true});
  addEventListener('resize', paint);
})();
"""


def main():
    html = (ROOT / "index.html").read_text(encoding="utf-8")

    # герой должен уметь и стоять на месте, и ехать — из потока его не вынимаем,
    # сдвиг делаем трансформом, поэтому нужен только источник трансформации
    html = html.replace("</style>", PANEL_CSS + "</style>", 1)

    # вырезаем боевой блок растворения целиком — от метки до конца IIFE.
    # Метка, а не текст комментария: формулировку я переписываю каждый раз,
    # когда меняется сама анимация, и привязка к ней ломалась.
    if MARK not in html:
        raise SystemExit(f"в index.html нет метки {MARK} — искать нечего")
    start = html.index(MARK)
    end = html.index("})();", start) + len("})();")
    html = html.replace(html[start:end], SCRIPT.strip(), 1)

    # пульт обязан стоять ДО скрипта: тот сразу вешает обработчик на кнопки,
    # а если их ещё нет в документе — падает, не дойдя до отрисовки
    assert html.count("<script>") == 1, "ожидался ровно один <script>"
    html = html.replace("<script>", PANEL_HTML + "<script>", 1)
    html = html.replace("<title>ЛИNДА — официальный сайт</title>",
                        "<title>ЛИNДА — примерка переходов</title>", 1)

    out = ROOT / "transitions.html"
    out.write_text(html, encoding="utf-8")

    # контроль: боевой обработчик не остался, пульт на месте
    assert MARK not in html, "боевой блок не вырезан"
    assert html.count("class=\"tp\"") == 1, "пульт не вставлен"
    assert re.search(r"data-v=\"3\"", html), "кнопки не вставлены"
    assert html.index("class=\"tp__r\"") < html.index("прототип: четыре перехода"), \
        "пульт оказался ниже скрипта"
    print(f"собрано: {out}")
    print(f"вариантов: 4, вес: {out.stat().st_size/1024:.0f} КБ")


if __name__ == "__main__":
    main()
