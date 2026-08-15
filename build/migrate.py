#!/usr/bin/env python3
"""Разовая сборка: linda-tour-2026.json + все проверенные правки -> tour.json.

После этого редактируется ТОЛЬКО tour.json — он единственный источник правды.
"""
import json, pathlib, datetime

SRC = pathlib.Path("/Users/pqresty/Documents/claude/фото сайт/linda-tour-2026.json")
OUT = pathlib.Path(__file__).parent / "tour.json"
VEN = pathlib.Path(__file__).parent / "venues.json"

# --- проверенные прямые страницы билетов (площадка или её оператор)
TICKET = {
    "2026-08-05-msk-petter":         "https://iframeab-pre2535.intickets.ru/seance/72518164/",
    "2026-08-06-msk-16tonn":         "https://www.16tons.ru/concert/2026-linda-06aug/",
    "2026-08-31-msk-korabl":         "https://cruisefest.moscow/linda2026",
    "2026-09-11-msk-rodnya":         "https://rodnya.rest/concerts/linda/",
    "2026-09-19-msk-modnaya-sreda":  "https://moscow.qtickets.events/246667-linda-puteshestvie-v-mir-teney-i-sveta",
    "2026-09-26-ryazan-rvb":         "https://ryazan.rvbar.ru/poster/linda-vse-hity/",
    "2026-09-30-ekb-maximilians":    "https://ekb.maximilians.ru/linda-2026/",
    "2026-10-01-chel-maximilians":   "https://chel.maximilians.ru/linda-2026/",
    "2026-10-03-msk-strogino-rvb":   "https://strogino.rvbar.ru/poster/linda/",
    "2026-10-09-msk-16tonn":         "https://www.16tons.ru/concert/2026-linda-09oct/",
    "2026-10-21-kazan-maximilians":  "https://kazan.maximilians.ru/linda-2026/",
    "2026-10-22-samara-maximilians": "https://samara.maximilians.ru/linda-2026/",
    "2026-10-23-korolev-duplex":     "https://www.clubduplex.ru/linda2310",
    "2026-10-24-spb-avrora":         "https://aurora.fm/linda",
    "2026-10-25-vnovgorod-serdce":   "https://nov.ticketland.ru/kluby/klub-serdce-nn/linda-velikiy-novgorod/t_20261025_1900_p_28908163/",
}

# --- время начала концерта, подтверждённое на сайте площадки
#     (в исходном файле стояло время дверей/посадки)
TIME = {
    "2026-08-31-msk-korabl": "20:00",   # сбор 18:00, посадка 19:00, отход 19:30
    "2026-10-24-spb-avrora": "20:00",   # двери 19:00
}

# --- реестр площадок: название -> официальный сайт
VENUES = {
    "Petter":                            "https://petter.su/",
    "16 Тонн":                           "https://www.16tons.ru/",
    "Поместье Грув":                     "https://groove.estate/",
    "Академ Джаз Клуб":                  "https://academjazzclub.ru/",
    "Family Rock Fest — ASP Arena":      "https://familyfest.kz/",
    "Теплоход, Северный речной вокзал":  "https://cruisefest.moscow/",
    "Родня":                             "https://rodnya.rest/",
    "Модная среда 1823":                 "https://modnaya-sreda.ru/",
    "Руки Вверх! Бар":                   "https://ruki.club/",
    "Руки Вверх! Бар (ex. Deep)":        "https://ryazan.rvbar.ru/",
    "Руки Вверх! Бар — Строгино":        "https://strogino.rvbar.ru/",
    "Duplex":                            "https://www.clubduplex.ru/",
    "Аврора Концерт Холл":               "https://aurora.fm/",
    "Сердце":                            "https://serdcevn.ru/",
    # сеть с поддоменом на каждый город
    "Максимилианс": {
        "Екатеринбург": "https://ekb.maximilians.ru/",
        "Челябинск":    "https://chel.maximilians.ru/",
        "Казань":       "https://kazan.maximilians.ru/",
        "Самара":       "https://samara.maximilians.ru/",
    },
}

WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

src = json.loads(SRC.read_text(encoding="utf-8"))
out = []
for e in src["events"]:
    d = datetime.date.fromisoformat(e["date"])
    out.append({
        "id":       e["id"],
        "date":     e["date"],
        "time":     TIME.get(e["id"], e.get("time")),
        "city":     e["city"],
        "country":  e.get("country", "RU"),
        "venue":    e.get("venue"),
        "ticketUrl": TICKET.get(e["id"]) or e.get("ticketUrl"),
        "status":   e.get("ticketStatus", "unknown"),
        # откуда взята ссылка: venue = сайт площадки/её оператор, agg = агрегатор
        "source":   "venue" if e["id"] in TICKET else ("agg" if e.get("ticketUrl") else None),
    })

out.sort(key=lambda x: x["date"])
OUT.write_text(json.dumps({"events": out}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
VEN.write_text(json.dumps(VENUES, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

direct = sum(1 for e in out if e["source"] == "venue")
print(f"tour.json: {len(out)} событий, из них на площадку {direct}")
print(f"venues.json: {len(VENUES)} площадок")
