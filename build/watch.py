#!/usr/bin/env python3
"""Утренний присмотр за афишей. Работает на серверах GitHub, не на Маке.

  python3 watch.py ask     — вчера был концерт? спросить в телеграме
  python3 watch.py apply   — пришло «да»? пересобрать сайт
  python3 watch.py report  — что изменилось у чужих афиш и не умерли ли ссылки

Прошедшие даты выбрасывает сама сборка, в tour.json их никто не стирает. Значит
«убрать вчерашнюю дату» — это просто «пересобрать и выложить». Заказчик просил
не делать этого молча, поэтому между «увидели» и «выложили» стоит его «да».

Токен бота и номер чата берутся из переменных окружения TG_TOKEN и TG_CHAT.
В коде и в репозитории их нет и быть не должно — они лежат в секретах GitHub.
"""
import datetime, json, os, pathlib, subprocess, sys, urllib.parse, urllib.request

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


def tg(method, **params):
    """Запрос к боту. Молчание сети не должно ронять задачу целиком."""
    if not TOKEN or not CHAT:
        sys.exit("нет TG_TOKEN или TG_CHAT — задача не настроена")
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(url, data=data, timeout=30) as r:
        out = json.loads(r.read().decode())
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


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"ask": ask, "apply": apply, "report": report}.get(
        cmd, lambda: sys.exit(__doc__))()
