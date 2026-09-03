#!/usr/bin/env python3
"""Сборка сайта Линды.

  python3 site.py build   — проверить данные и собрать index.html
  python3 site.py check   — проверить, что все ссылки живые
  python3 site.py scan    — сверить наши даты с афишей на rolld.ru
  python3 site.py times   — сверить время начала с сайтами площадок

Редактируется только tour.json. День недели считается сам — руками не вводить.
"""
import json, pathlib, html, sys, datetime, re
import urllib.request, concurrent.futures

HERE  = pathlib.Path(__file__).parent
ROOT  = HERE.parent
TOUR  = HERE / "tour.json"
VEN   = HERE / "venues.json"
TPL   = HERE / "template.html"
OUT   = ROOT / "index.html"

WD     = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = {1:"Январь",2:"Февраль",3:"Март",4:"Апрель",5:"Май",6:"Июнь",
          7:"Июль",8:"Август",9:"Сентябрь",10:"Октябрь",11:"Ноябрь",12:"Декабрь"}
STATUSES = {"on_sale", "not_on_sale", "unknown"}
# страну показываем только для зарубежных площадок — для России она очевидна
COUNTRY  = {"KZ": "Казахстан", "BY": "Беларусь", "IL": "Израиль"}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

def esc(s): return html.escape(str(s), quote=True)

def load():
    data   = json.loads(TOUR.read_text(encoding="utf-8"))
    venues = json.loads(VEN.read_text(encoding="utf-8"))
    return data["events"], venues, data.get("ignored", [])

def venue_url(ev, venues):
    v = venues.get(ev.get("venue") or "")
    return v.get(ev["city"]) if isinstance(v, dict) else v

def host(u):
    m = re.match(r"https?://(?:www\.)?([^/]+)", u or "")
    return m.group(1).lower() if m else ""

def is_direct(ev, venues):
    """Билет ведёт на площадку, если хост совпал с её сайтом
    либо помечен вручную как оператор, выбранный площадкой."""
    t = ev.get("ticketUrl")
    if not t: return False
    if ev.get("source") == "venue": return True
    vu = venue_url(ev, venues)
    if not vu: return False
    a, b = host(t), host(vu)
    return a == b or a.endswith("." + b) or b.endswith("." + a)

# ---------------------------------------------------------------- проверки
def validate(events, venues):
    problems, notes = [], []
    seen = set()
    for e in events:
        who = f'{e.get("date","?")} {e.get("city","?")}'
        for f in ("id", "date", "city", "status"):
            if not e.get(f):
                problems.append(f"{who}: не заполнено поле «{f}»")
        if e.get("id") in seen:
            problems.append(f"{who}: id повторяется — {e['id']}")
        seen.add(e.get("id"))
        try:
            datetime.date.fromisoformat(e["date"])
        except Exception:
            problems.append(f"{who}: дата не в формате ГГГГ-ММ-ДД")
        if e.get("status") not in STATUSES:
            problems.append(f'{who}: статус «{e.get("status")}» — можно только {", ".join(sorted(STATUSES))}')
        if e.get("status") == "on_sale" and not e.get("ticketUrl"):
            problems.append(f"{who}: статус on_sale, но ссылки на билет нет")
        if e.get("time") and not re.fullmatch(r"\d{1,2}:\d{2}", e["time"]):
            problems.append(f'{who}: время «{e["time"]}» — нужен формат ЧЧ:ММ')
        # aggregatorOk — площадка продаёт только через агрегатор, решение принято.
        # Без этой пометки одни и те же строки всплывали бы при каждой сборке.
        if not is_direct(e, venues) and e.get("ticketUrl") and not e.get("aggregatorOk"):
            notes.append(f"{who} · {e.get('venue','площадка не указана')}: "
                         f"билет ведёт на агрегатор, стоит поискать площадку")
        if e.get("venue") and not venue_url(e, venues):
            notes.append(f"{who} · {e['venue']}: нет сайта площадки в venues.json")
        if not e.get("venue"):
            notes.append(f"{who}: площадка ещё не указана — в строке будет только город")
    return problems, notes

# ---------------------------------------------------------------- сборка
def render(events, venues):
    # Прошедшее не показываем. Иначе афишу приходится подчищать руками, а
    # забытая вчерашняя дата в списке предстоящих выглядит хуже пустоты.
    # Сегодняшний концерт остаётся — он ещё впереди.
    today = datetime.date.today().isoformat()
    events = [e for e in events if e["date"] >= today]

    groups = {}
    for e in sorted(events, key=lambda x: x["date"]):
        d = datetime.date.fromisoformat(e["date"])
        groups.setdefault((d.year, d.month), []).append((d, e))

    parts = []
    for (y, m), items in groups.items():
        parts.append('<div class="mon">')
        parts.append(f'  <h3 class="mon__h">{MONTHS[m]}</h3>')
        for d, e in items:
            cls = "row"
            if e["status"] == "not_on_sale": cls += " row--soon"
            elif e["status"] == "unknown":   cls += " row--tbd"

            if e["status"] == "on_sale" and e.get("ticketUrl"):
                act = (f'<a class="row__b" href="{esc(e["ticketUrl"])}" target="_blank" '
                       f'rel="noopener noreferrer">Билеты</a>')
            else:
                # билетов нет — неважно, не открыли продажу или ссылка не найдена
                act = '<span class="row__b row__b--off">Скоро</span>'

            # площадки может ещё не быть — тогда в строке остаётся один город
            vu, vn = venue_url(e, venues), e.get("venue")
            if not vn:
                venue = ""
            elif vu:
                venue = (f'<a class="row__v" href="{esc(vu)}" target="_blank" '
                         f'rel="noopener noreferrer">{esc(vn)}</a>')
            else:
                venue = f'<span class="row__v">{esc(vn)}</span>'

            country = COUNTRY.get(e.get("country", "RU"))
            city = (f'<span class="row__city">{esc(e["city"])}'
                    + (f'<i class="row__f">{country}</i>' if country else "")
                    + "</span>")

            # Площадка объявляет два времени — показываем оба в строку через
            # косую: сначала сбор, к нему приходить, следом начало концерта.
            # Где объявлено одно — оно и стоит, без всяких пояснений.
            # Показываем одно время — самое раннее из объявленных площадкой.
            # Где объявлены и сбор, и начало, это сбор: к нему и приходить,
            # заведение на том и стоит — люди успевают поесть до первой ноты.
            # Второе время не пропадает: оно лежит в данных, уходит в машинную
            # разметку и участвует в еженедельной сверке с сайтом площадки.
            when = min(x for x in (e.get("doors"), e.get("time")) if x) \
                   if (e.get("doors") or e.get("time")) else ""
            meta = esc(" · ".join([WD[d.weekday()]] + ([when] if when else [])))
            parts.append(f'''  <div class="{cls}">
    <span class="row__d">{d.day:02d}</span>
    <span class="row__m">{meta}</span>
    <span class="row__c">{city}{venue}</span>
    {act}
  </div>''')
        parts.append('</div>')

    page = (TPL.read_text(encoding="utf-8")
            .replace("__ROWS__", "\n".join(parts))
            .replace("__JSONLD__", jsonld(events, venues)))
    OUT.write_text(stamp(page), encoding="utf-8")
    sidecars()


SITE = "https://lindaconcerts.ru"
# Код страны из ISO — в разметке он нужен всегда, в том числе для России,
# где в самой афише мы его не показываем.
ISO = {"RU": "RU", "KZ": "KZ", "BY": "BY", "IL": "IL"}

def jsonld(events, venues):
    """Артист и его концерты машинным языком.

    Из этого поисковик собирает карточку исполнителя и понимает, что сайт
    официальный, а не очередная перепечатка афиши. Список тот же, что и на
    странице, — расходиться им нельзя, поэтому собирается из тех же данных."""
    artist = {
        "@type": "MusicGroup",
        "@id": SITE + "/#artist",
        "name": "Линда",
        "alternateName": ["ЛИNДА", "Linda", "Светлана Гейман"],
        "url": SITE + "/",
        "image": SITE + "/assets/og/og-cover.jpg",
        "sameAs": ["https://vk.com/linda_official", "https://t.me/lindamusic"],
    }
    graph = [artist, {
        "@type": "WebSite",
        "@id": SITE + "/#site",
        "url": SITE + "/",
        "name": "ЛИNДА — официальный сайт",
        "inLanguage": "ru-RU",
        "about": {"@id": SITE + "/#artist"},
    }]

    for e in sorted(events, key=lambda x: x["date"]):
        place = {"@type": "Place", "address": {
            "@type": "PostalAddress",
            "addressLocality": e["city"],
            "addressCountry": ISO.get(e.get("country", "RU"), "RU"),
        }}
        if e.get("venue"):
            place["name"] = e["venue"]
            vu = venue_url(e, venues)
            if vu: place["url"] = vu

        ev = {
            "@type": "MusicEvent",
            "name": f'Линда — концерт в городе {e["city"]}',
            # Без смещения: у нас города в пяти поясах, а местное время
            # схема допускает. Врать про +03:00 хуже, чем не указать вовсе.
            "startDate": e["date"] + ("T" + e["time"] if e.get("time") else ""),
            **({"doorTime": e["date"] + "T" + e["doors"]} if e.get("doors") else {}),
            "eventStatus": "https://schema.org/EventScheduled",
            "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
            "location": place,
            # organizer не ставим: концерты собирают промоутеры, а не артистка
            "performer": {"@id": SITE + "/#artist"},
            "image": SITE + "/assets/og/og-cover.jpg",
            "url": SITE + "/",
        }
        if e["status"] == "on_sale" and e.get("ticketUrl"):
            ev["offers"] = {
                "@type": "Offer",
                "url": e["ticketUrl"],
                "availability": "https://schema.org/InStock",
                "validFrom": e["date"],
            }
        graph.append(ev)

    body = json.dumps({"@context": "https://schema.org", "@graph": graph},
                      ensure_ascii=False, indent=1)
    return f'<script type="application/ld+json">\n{body}\n</script>'


def sidecars():
    """robots.txt и sitemap.xml — их никто не линкует, роботы берут по адресу."""
    # Страницы-примерки лежат рядом и открываются по прямому адресу. В поиске
    # им не место: это черновики, и они тянут на себя запросы про Линду.
    (ROOT / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n"
        "Disallow: /transitions.html\n"
        "Disallow: /mobile-crop.html\n"
        "Disallow: /scrim.html\n\n"
        f"Sitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
    today = datetime.date.today().isoformat()
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <url>\n    <loc>{SITE}/</loc>\n'
        f'    <lastmod>{today}</lastmod>\n'
        '    <changefreq>weekly</changefreq>\n'
        '    <priority>1.0</priority>\n  </url>\n'
        '</urlset>\n', encoding="utf-8")


ASSET = re.compile(r'assets/[A-Za-z0-9._/-]+\.(?:webp|avif|woff2|svg|jpg|jpeg|png)')

def stamp(page):
    """Дописывает к адресам файлов отпечаток их содержимого.

    Иначе после подмены картинки браузер ещё сутками показывает старую: имя
    файла не изменилось, значит перезапрашивать нечего. С отпечатком адрес
    меняется вместе с содержимым, и это происходит само — руками ничего
    переименовывать не нужно."""
    import hashlib
    seen = {}

    def one(m):
        rel = m.group(0)
        if rel not in seen:
            f = ROOT / rel
            seen[rel] = hashlib.sha256(f.read_bytes()).hexdigest()[:8] if f.exists() else None
        h = seen[rel]
        return f"{rel}?v={h}" if h else rel

    out = ASSET.sub(one, page)
    missing = [k for k, v in seen.items() if v is None]
    if missing:
        print("  файлы не найдены:", *missing, sep="\n    ")
    return out

# ------------------------------------------------------------ время начала
RU_MON = {1:"январ",2:"феврал",3:"март",4:"апрел",5:"ма",6:"июн",7:"июл",
          8:"август",9:"сентябр",10:"октябр",11:"ноябр",12:"декабр"}

def times(events):
    """Сверяет наше время начала с тем, что написано на странице площадки.

    Площадки время двигают и никого не предупреждают. Кроме того, легко
    записать «сбор гостей» вместо начала: у «Максимилианса» так и вышло —
    три даты стояли с 20:00, тогда как сбор в 20:00, а выступление в 21:00.
    Поэтому ищем прямую формулировку «начало ... 21:00», а не первое попавшееся
    время: на странице клуба их всегда много — часы работы, бронь, кухня."""
    NACH = re.compile(
        r'(?:[Сс]бор[^.]{0,40}?(\d{1,2}:\d{2})[^.]{0,15}?)?'
        r'[Нн]ачал\w*\s+(?:выступлени\w*|концерта|программы|шоу|в)\s*:?\s*(?:в\s*)?(\d{1,2}:\d{2})')

    def body(u):
        """http() выше отдаёт код ответа, а не текст — здесь нужен сам текст."""
        try:
            return urllib.request.urlopen(
                urllib.request.Request(u, headers=UA), timeout=25
            ).read().decode("utf-8", "replace")
        except Exception:
            return ""

    def look(e):
        u = e.get("ticketUrl")
        if not u or not e.get("time"): return e, "нет ссылки или времени", None
        page = body(u)
        if not page: return e, "страница не открылась", None
        txt = re.sub(r"<script.*?</script>", " ", page, flags=re.S)
        txt = re.sub(r"<[^>]+>", " ", txt)
        txt = re.sub(r"&nbsp;|&#160;", " ", txt)
        txt = re.sub(r"\s+", " ", txt)
        m = NACH.search(txt)
        if m: return e, None, (m.group(1), m.group(2))
        # прямой формулировки нет — берём время рядом с датой события
        d = datetime.date.fromisoformat(e["date"])
        near = re.search(rf'{d.day}\s*{RU_MON[d.month]}\w*[^.]{{0,80}}?(\d{{1,2}}:\d{{2}})', txt)
        if near: return e, None, (None, near.group(1))
        return e, "время на странице не указано", None

    today = datetime.date.today().isoformat()
    live  = [e for e in events if e["date"] >= today]
    diff, unknown = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for e, why, found in ex.map(look, live):
            if why: unknown.append((e, why)); continue
            sbor, start = found
            if start != e["time"]:
                diff.append((e, e["time"], start, sbor))

    if diff:
        print("время начала разошлось с площадкой:")
        for e, ours, theirs, sbor in sorted(diff, key=lambda x: x[0]["date"]):
            add = f" (сбор {sbor})" if sbor else ""
            print(f'  {e["date"]} {e["city"]} · {e.get("venue","")}: '
                  f'у нас {ours}, на странице {theirs}{add}')
    else:
        print("время начала везде совпадает")
    if unknown:
        print(f"не удалось сверить: {len(unknown)}")
        for e, why in sorted(unknown, key=lambda x: x[0]["date"]):
            print(f'  {e["date"]} {e["city"]}: {why}')
    return diff


# ---------------------------------------------------------------- ссылки
def http(url, tries=3):
    """Сетевую ошибку пробуем ещё раз, прежде чем звать ссылку битой.

    Живые площадки регулярно не отвечают на одиночный запрос — так уже дважды
    останавливалась выкладка на groove-events.ru, хотя со второго раза сайт
    отдавал 200. Коды ответа (404, 500) повторять незачем: это ответ сервера,
    а не обрыв."""
    import time
    for n in range(tries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25)
            return url, r.status
        except urllib.error.HTTPError as e:
            return url, e.code
        except Exception as e:
            if n == tries - 1:
                return url, type(e).__name__
            time.sleep(1.5 * (n + 1))

def check_links():
    urls = sorted(set(re.findall(r'href="(https://[^"]+)"', OUT.read_text(encoding="utf-8"))))
    bad = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for u, code in ex.map(http, urls):
            if code != 200:
                bad.append((u, code))
    print(f"ссылок проверено: {len(urls)}")
    for u, c in bad:
        print(f"  БИТАЯ [{c}] {u}")
    if not bad:
        print("  все живые")
    return bad

# ---------------------------------------------------------------- сверка
def scan(events, ignored=()):
    """Тянет афишу артиста с rolld и показывает, чего у нас нет.

    Читает машинную разметку ld+json, а не видимый текст. В тексте у строк
    нет года: 19 августа там значит 2027-й, а разбор по дню и месяцу считал
    это пропущенной датой 2026-го и выдавал ложную тревогу — на Petter, у
    которого стоит абонемент на каждый месяц, таких «пропаж» набиралось пять.
    """
    def fetch(u):
        return urllib.request.urlopen(
            urllib.request.Request(u, headers=UA), timeout=30
        ).read().decode("utf-8", "ignore")

    try:
        raw = fetch("https://rolld.ru/artist/linda")
    except Exception as e:
        print("не удалось получить rolld.ru/artist/linda:", e); return

    found = []
    def walk(o):
        if isinstance(o, dict):
            if o.get("@type") in ("Event", "MusicEvent") and o.get("startDate"):
                loc  = o.get("location") if isinstance(o.get("location"), dict) else {}
                addr = loc.get("address") if isinstance(loc.get("address"), dict) else {}
                found.append({"date": o["startDate"][:10], "time": o["startDate"][11:16],
                              "city": addr.get("addressLocality") or "?",
                              "venue": loc.get("name") or "?", "url": o.get("url", "")})
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    def dig(page):
        for b in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S):
            try: walk(json.loads(b))
            except Exception: pass

    dig(raw)
    if not found:
        # С августа 2026 на странице артиста дат нет вовсе — только ItemList со
        # ссылками на события, а startDate уехал на сами страницы. Значит идём
        # по ссылкам. Сорок штук, поэтому в несколько потоков.
        urls = []
        for b in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', raw, re.S):
            try: o = json.loads(b)
            except Exception: continue
            if isinstance(o, dict) and o.get("@type") == "ItemList":
                urls = [i.get("url") for i in o.get("itemListElement", []) if i.get("url")]
        if not urls:
            print("на странице артиста нет ни дат, ни списка событий — вёрстка снова другая")
            return
        print(f"на странице артиста дат нет, читаю {len(urls)} страниц событий…")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for page in ex.map(lambda u: (lambda: fetch(u))() if u else "", urls):
                if page: dig(page)
    if not found:
        print("в разметке rolld событий не найдено — возможно, поменялась вёрстка"); return

    def norm(c):
        c = (c or "").lower().replace("ё", "е")
        return {"санкт-петербург": "спб", "москва": "мск", "королев": "королев"}.get(c, c)

    ours = {(e["date"], norm(e["city"])) for e in events}
    # решённое однажды не показываем снова: список в tour.json, ключ ignored
    skip = {(i["date"], norm(i["city"])): (i["city"], i.get("reason", "")) for i in ignored}
    lo = min(e["date"] for e in events)
    hi = max(e["date"] for e in events)
    print(f"наш период: {lo} … {hi}, у нас {len(events)} дат; на rolld {len(found)}")

    inside  = [f for f in found if lo <= f["date"] <= hi
               and (f["date"], norm(f["city"])) not in ours
               and (f["date"], norm(f["city"])) not in skip]
    after   = [f for f in found if f["date"] > hi]
    same    = {}
    for f in found:
        same.setdefault(f["date"], []).append(f)

    if inside:
        print("в нашем периоде есть на rolld, у нас нет:")
        for f in sorted(inside, key=lambda x: x["date"]):
            print(f"  {f['date']} {f['time']}  {f['city']} · {f['venue']}")
    else:
        print("в нашем периоде расхождений нет")
    if skip:
        print(f"пропущено по прежним решениям: {len(skip)}")
        for (d, _), (city, reason) in sorted(skip.items()):
            print(f"  {d} {city} — {reason}")

    clash = [d for d, fs in same.items() if len({norm(x['city']) for x in fs}) > 1]
    if clash:
        print("на rolld два города в один день — стоит уточнить у промоутеров:")
        for d in sorted(clash):
            print(f"  {d}: " + "; ".join(f"{x['city']} · {x['venue']}" for x in same[d]))

    if after:
        print(f"позже нашего периода: {len(after)} дат — ближайшие:")
        for f in sorted(after, key=lambda x: x["date"])[:4]:
            print(f"  {f['date']} {f['time']}  {f['city']} · {f['venue']}")

# ---------------------------------------------------------------- запуск
def main():
    events, venues, ignored = load()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"

    if cmd == "build":
        problems, notes = validate(events, venues)
        if problems:
            print("Ошибки:", *problems, sep="\n  ")
            print("\nСборка остановлена — сначала поправьте tour.json")
            sys.exit(1)
        render(events, venues)
        # считаем только те, у кого билет вообще есть: даты без ссылки —
        # это «скоро», их не за что записывать в агрегаторы
        sold   = [e for e in events if e.get("ticketUrl")]
        direct = sum(1 for e in sold if is_direct(e, venues))
        agreed = sum(1 for e in sold if not is_direct(e, venues) and e.get("aggregatorOk"))
        print(f"собрано: {OUT}")
        print(f"событий {len(events)} · в продаже {len(sold)} · на площадку {direct} · "
              f"агрегатор по договорённости {agreed} · осталось разобрать {len(sold)-direct-agreed}")
        for n in notes:
            print("  ·", n)

    elif cmd == "check":
        sys.exit(1 if check_links() else 0)

    elif cmd == "scan":
        scan(events, ignored)

    elif cmd == "times":
        times(events)

    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
