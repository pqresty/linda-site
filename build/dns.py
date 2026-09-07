#!/usr/bin/env python3
"""Слепок зоны DNS и сверка с ним.

  python3 dns.py snapshot        — записать нынешнюю зону в dns.json
  python3 dns.py check           — сверить то, что видит мир, со слепком
  python3 dns.py at ns1.reg.ru   — спросить конкретный сервер имён напрямую

Нужно ради переезда зоны с хостинга Host-0 на отдельный DNS-сервис. Порядок
такой: завести зону у нового провайдера, спросить его сервер через `at` и
убедиться, что он отдаёт ровно то же самое, и только потом менять NS у
регистратора. Иначе домен уедет на пустую зону и сайт пропадёт.

`check` ходит через DNS-over-HTTPS: он должен работать и на runner'е GitHub,
где `dig` может быть не установлен. `at` спрашивает сервер напрямую и потому
требует `dig` — но он и нужен только руками, до переключения.
"""
import json, pathlib, subprocess, sys, urllib.request, urllib.parse, datetime

HERE = pathlib.Path(__file__).parent
FILE = HERE / "dns.json"
DOMAIN = "lindaconcerts.ru"

# Что спрашиваем. У апекса — всё, у остальных имён только то, что там бывает.
ASK = {
    "":      ["A", "AAAA", "MX", "TXT", "NS"],
    # У www спрашиваем только CNAME: A и AAAA за ним — это уже адреса самого
    # GitHub, они меняются без нас и сверку бы ломали.
    "www":   ["CNAME"],
    "mail":  ["A"],
    "smtp":  ["A"],
    "pop":   ["A"],
    "ftp":   ["A"],
}
DOH = "https://dns.google/resolve"


def fqdn(sub):
    return f"{sub}.{DOMAIN}" if sub else DOMAIN


def norm(kind, data):
    """Приводим ответ к одному виду: без кавычек, с точкой на конце имени.

    Разные резолверы отдают TXT то в кавычках, то без, а имена — то с точкой,
    то без неё. Без нормализации сверка ловит различия, которых нет."""
    d = data.strip()
    if kind == "TXT":
        return d.strip('"').replace('" "', "")
    if kind in ("CNAME", "NS"):
        return d.rstrip(".").lower() + "."
    if kind == "MX":
        pref, _, host = d.partition(" ")
        return f"{pref} {host.strip().rstrip('.').lower()}."
    return d


def doh(name, kind):
    """Спрашиваем публичный резолвер по HTTPS. Пустой список — записи нет."""
    q = urllib.parse.urlencode({"name": name, "type": kind})
    req = urllib.request.Request(f"{DOH}?{q}", headers={"Accept": "application/dns-json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        js = json.loads(r.read().decode())
    types = {"A": 1, "NS": 2, "CNAME": 5, "MX": 15, "TXT": 16, "AAAA": 28}
    return sorted(norm(kind, a["data"]) for a in js.get("Answer", [])
                  if a.get("type") == types[kind])


def direct(name, kind, server):
    """То же самое, но у конкретного сервера имён — через dig."""
    r = subprocess.run(["dig", "+short", "+time=5", "+tries=2", kind, name, f"@{server}"],
                       capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l.strip() and not l.startswith(";")]
    return sorted(norm(kind, l) for l in lines)


def collect(fetch):
    out = {}
    for sub, kinds in ASK.items():
        rec = {}
        for kind in kinds:
            got = fetch(fqdn(sub), kind)
            if got:
                rec[kind] = got
        out[fqdn(sub)] = rec
    return out


def load():
    return json.loads(FILE.read_text(encoding="utf-8"))


def compare(now, want, было="в слепке", стало="сейчас"):
    """Возвращает список расхождений человеческим текстом."""
    def show(v): return ", ".join(v) if v else "пусто"
    bad = []
    for name in sorted(set(want) | set(now)):
        a, b = now.get(name, {}), want.get(name, {})
        for kind in sorted(set(a) | set(b)):
            here, there = a.get(kind, []), b.get(kind, [])
            if here != there:
                bad.append(f"{name} {kind}: {было} {show(there)}; {стало} {show(here)}")
    return bad


def cmd_snapshot():
    zone = collect(doh)
    FILE.write_text(json.dumps({
        "домен": DOMAIN,
        "снято": datetime.date.today().isoformat(),
        "зачем": "эталон для сверки при переезде зоны с Host-0 на отдельный DNS",
        "записи": zone,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"слепок записан: {FILE}")
    for name, rec in zone.items():
        for kind, vals in rec.items():
            print(f"  {name} {kind} → {', '.join(vals)}")


def cmd_check():
    want = load()["записи"]
    bad = compare(collect(doh), want)
    # Смена NS — это и есть переезд, а не поломка: показываем отдельно.
    ns  = [b for b in bad if b.split()[1] == "NS:"]
    rest = [b for b in bad if b not in ns]
    if ns:
        print("сервера имён сменились (так и задумано при переезде):")
        for b in ns: print("  " + b)
    if rest:
        print("ЗОНА РАЗОШЛАСЬ СО СЛЕПКОМ:")
        for b in rest: print("  " + b)
        return 1
    if not ns:
        print("зона в порядке, совпадает со слепком")
    return 0


def cmd_at(server):
    want = load()["записи"]
    now  = collect(lambda n, k: direct(n, k, server))
    bad  = [b for b in compare(now, want, стало=f"у {server}") if b.split()[1] != "NS:"]
    print(f"сервер {server} отдаёт:")
    for name, rec in now.items():
        for kind, vals in rec.items():
            print(f"  {name} {kind} → {', '.join(vals)}")
    if bad:
        print("\nНЕ СОВПАЛО СО СЛЕПКОМ — переключать NS нельзя:")
        for b in bad: print("  " + b)
        return 1
    print("\nвсё совпало со слепком — этот сервер готов принять делегирование")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "snapshot":
        cmd_snapshot(); return 0
    if cmd == "check":
        return cmd_check()
    if cmd == "at":
        if len(sys.argv) < 3:
            print("нужен адрес сервера имён: dns.py at ns1.reg.ru"); return 2
        return cmd_at(sys.argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
