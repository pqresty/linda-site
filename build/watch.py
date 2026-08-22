#!/usr/bin/env python3
"""Утренний присмотр за афишей. Работает на серверах GitHub, не на Маке.

  python3 watch.py ask     — вчера был концерт? спросить в телеграме
  python3 watch.py apply   — пришло «да»? пересобрать сайт
  python3 watch.py report  — что изменилось у чужих афиш и не умерли ли ссылки

Сборка и так не показывает прошедшее, но в tour.json оно остаётся — иначе
вопрос про одну и ту же вчерашнюю дату приходил бы вечно. Поэтому на «да»
дата вычёркивается из данных, а сайт пересобирается. Заказчик просил не
делать этого молча, поэтому между «увидели» и «выложили» стоит его «да».

Токен бота и номер чата берутся из переменных окружения TG_TOKEN и TG_CHAT.
В коде и в репозитории их нет и быть не должно — они лежат в секретах GitHub.
"""
import datetime, json, os, pathlib, subprocess, sys
import urllib.error, urllib.parse, urllib.request

HERE    = pathlib.Path(__file__).parent
TOUR    = HERE / "tour.json"
PENDING = HERE / "pending.json"
INBOX   = HERE / "inbox.jsonl"

TOKEN = os.environ.get("TG_TOKEN", "")
CHAT  = os.environ.get("TG_CHAT", "")

# сколько ждём ответа, прежде чем спросить заново
PATIENCE = datetime.timedelta(days=2)

YES = {"да", "да.", "ага", "давай", "убирай", "убрать", "ок", "окей", "+"}
NO  = {"нет", "нет.", "не", "погоди", "подожди", "стой", "-"}


class NotSetUp(Exception):
    """Бота ещё не завели. Это не поломка — просто молчим и выходим по-хорошему."""


def tg(method, **params):
    """Запрос к боту."""
    if not TOKEN or not CHAT:
        raise NotSetUp
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=30) as r:
            out = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # Телеграм объясняет отказ в теле ответа, а urllib его проглатывает и
        # оставляет голый «403 Forbidden». Без этого текста причину не понять:
        # 403 — это и «не нажали Start у бота», и «бота заблокировали».
        try:   why = json.loads(e.read().decode()).get("description", "")
        except Exception: why = ""
        sys.exit(f"телеграм отказал ({e.code}): {why or e.reason}")
    if not out.get("ok"):
        sys.exit(f"телеграм отказал: {out.get('description')}")
    return out["result"]


def say(text):
    return tg("sendMessage", chat_id=CHAT, text=text,
              parse_mode="HTML", disable_web_page_preview="true")


def events():
    return json.loads(TOUR.read_text(encoding="utf-8"))["events"]


def past(today):
    """Даты, которые уже прошли, но всё ещё лежат в данных.

    Смотрим не только вчерашний день: если задача не отработала несколько
    суток подряд, накопившееся не должно потеряться."""
    return sorted([e for e in events() if e["date"] < today], key=lambda e: e["date"])


# ------------------------------------------------------------------ спросить
def ask():
    today = datetime.date.today().isoformat()
    gone  = past(today)
    if not gone:
        print("прошедших дат нет — молчим"); return

    if PENDING.exists():
        p = json.loads(PENDING.read_text(encoding="utf-8"))
        asked = datetime.datetime.fromisoformat(p["asked"])
        if datetime.datetime.now(datetime.timezone.utc) - asked < PATIENCE:
            print("вопрос уже задан, ждём ответа"); return

    lines = [f'· {e["date"]} — {e["city"]}' + (f' · {e["venue"]}' if e.get("venue") else "")
             for e in gone]
    word = "концерт прошёл" if len(gone) == 1 else "концерты прошли"
    msg = say(f"<b>Афиша</b>\n\nЭти {word}, но всё ещё висят на сайте:\n"
              + "\n".join(lines)
              + "\n\nУбрать? Ответь <b>да</b> — пересоберу и выложу.")

    PENDING.write_text(json.dumps({
        "asked":  datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "dates":  [e["date"] for e in gone],
        "ids":    [e["id"] for e in gone],
        "msg_id": msg["message_id"],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"спросил про {len(gone)} дат")


# ------------------------------------------------------------------ ответить
def apply():
    """Разбирает чат: ответ на заданный вопрос и всё остальное — в почтовый ящик.

    Печатает publish=1, если сайт надо перевыложить.

    Смещение (offset) намеренно не подтверждаем: телеграм и так держит
    непрочитанное сутки, а хранить счётчик между запусками — лишняя возня и
    лишний коммит в репозиторий. От повторной обработки спасает отметка
    времени: всё, что старше последнего разбора, пропускаем."""
    seen  = json.loads(INBOX.read_text(encoding="utf-8").splitlines()[-1])["at"] \
            if INBOX.exists() and INBOX.read_text(encoding="utf-8").strip() else 0
    p     = json.loads(PENDING.read_text(encoding="utf-8")) if PENDING.exists() else None
    asked = datetime.datetime.fromisoformat(p["asked"]).timestamp() if p else None

    verdict, letters, newest = None, [], seen
    for u in tg("getUpdates", timeout=0, allowed_updates='["message"]'):
        m = u.get("message") or {}
        if str(m.get("chat", {}).get("id")) != str(CHAT): continue
        when = m.get("date", 0)
        t = (m.get("text") or "").strip()
        low = t.lower()
        newest = max(newest, when)
        if p and when >= asked and low in YES: verdict = True;  continue
        if p and when >= asked and low in NO:  verdict = False; continue
        # всё прочее — это правки от заказчика: концерт в уже вышедший месяц,
        # отмена, новая ссылка. Скрипт их не понимает и понимать не должен —
        # он складывает их в ящик, разбирать буду я, когда мы сядем за сайт.
        if t and when > seen:
            letters.append({"at": when, "text": t})

    if letters:
        with INBOX.open("a", encoding="utf-8") as f:
            for l in letters:
                f.write(json.dumps(l, ensure_ascii=False) + "\n")
        say(f"Записал, {len(letters)} шт. Разберу, когда сядем за сайт — "
            f"покажу, что поменяю, и выложу после твоего слова.")
        print(f"в ящик легло {len(letters)}")

    if verdict is None:
        print("ответа пока нет"); print("publish=0"); return

    PENDING.unlink()
    if not verdict:
        say("Хорошо, оставляю как есть. Спрошу снова, когда появится ещё одна прошедшая дата.")
        print("сказано «нет»"); print("publish=0"); return

    # Вычёркиваем даты из самих данных. Сборка их и так не показывает, но в
    # tour.json они остаются — и тогда вопрос про них приходил бы каждое утро
    # до скончания века. История не теряется: она в истории репозитория.
    d = json.loads(TOUR.read_text(encoding="utf-8"))
    ids   = set(p.get("ids") or [])
    dates = set(p.get("dates") or [])
    keep  = (lambda e: e["id"] not in ids) if ids else (lambda e: e["date"] not in dates)
    before = len(d["events"])
    d["events"] = [e for e in d["events"] if keep(e)]
    TOUR.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"вычеркнуто из данных: {before - len(d['events'])}")

    subprocess.run([sys.executable, str(HERE / "site.py"), "build"], check=True)
    subprocess.run([sys.executable, str(HERE / "deploy.py")],        check=True)
    say("Убрал: " + ", ".join(p["dates"]) + ". Сайт обновлён.")
    print("publish=1")


# ------------------------------------------------------------------- сводка
def report():
    """Раз в неделю: чего у нас нет в афише и что перестало работать."""
    out = []
    for cmd, title in (("scan", "Сверка с чужой афишей"), ("check", "Проверка ссылок")):
        r = subprocess.run([sys.executable, str(HERE / "site.py"), cmd],
                           capture_output=True, text=True)
        body = (r.stdout or r.stderr).strip()
        if cmd == "check" and "БИТАЯ" not in body:
            body = "все ссылки живые"
        out.append(f"<b>{title}</b>\n<pre>{body[:1500]}</pre>")

    soon = [e for e in events() if e["status"] != "on_sale"]
    if soon:
        out.append("<b>Ещё без билетов</b>\n" + "\n".join(
            f'· {e["date"]} — {e["city"]}' + (f' · {e["venue"]}' if e.get("venue") else "")
            for e in soon))
    say("\n\n".join(out))
    print("сводка отправлена")


# ---------------------------------------------------------------- диагностика
def whoami():
    """Кто мы для телеграма и кто нам писал. Ничего не отправляет.

    Нужна, когда бот молчит: показывает, тот ли это бот и совпадает ли номер
    чата в секрете с тем, из которого реально приходят сообщения."""
    me = tg("getMe")
    print(f"бот: @{me.get('username')} (id {me.get('id')})")
    print(f"TG_CHAT в секрете: {CHAT}")
    chats = {}
    for u in tg("getUpdates", timeout=0, allowed_updates='["message"]'):
        c = (u.get("message") or {}).get("chat") or {}
        if c.get("id"):
            chats[c["id"]] = c.get("type", "?")
    if chats:
        print("писали из чатов:", ", ".join(f"{k} ({v})" for k, v in chats.items()))
        print("совпадает:", "да" if str(CHAT) in map(str, chats) else "НЕТ")
    else:
        print("сообщений в очереди нет — либо их уже разобрали, либо боту не писали")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    run = {"ask": ask, "apply": apply, "report": report, "whoami": whoami}.get(cmd)
    if not run:
        sys.exit(__doc__)
    try:
        run()
    except NotSetUp:
        # Пока в секретах нет токена, задача обязана завершаться успехом:
        # иначе она падает каждые двадцать минут и шлёт письма о сбоях.
        print("бот не настроен — TG_TOKEN и TG_CHAT пусты, пропускаю")
        print("publish=0")
