#!/usr/bin/env python3
"""Просим поисковики переобойти сайт — без входа в кабинеты.

  python3 indexnow.py

Протокол IndexNow: кладём на сайт файл с ключом, а поисковику сообщаем адрес
страницы и ключ. Он забирает файл, убеждается, что сайт наш, и ставит
страницу в очередь на обход. Работает для Яндекса и Bing; Google протокол не
поддерживает — туда только через Search Console.

Зачем это нам: афиша меняется каждую неделю — дата отыграна, дата
добавилась, — а поисковик сам заходит на молодой сайт редко. Пинг после
каждой выкладки говорит ему, что пора.

Ключ секретом не является: он и так лежит на сайте открытым файлом, иначе
поисковик не смог бы его проверить. Ошибка пинга никогда не роняет выкладку.
"""
import sys, urllib.parse, urllib.request

KEY  = "88ddeed887ff74861a022fcc99031cc1"
SITE = "https://lindaconcerts.ru"
ENDPOINTS = ("https://yandex.com/indexnow", "https://api.indexnow.org/indexnow")


def ping(url=SITE + "/"):
    q = urllib.parse.urlencode({"url": url, "key": KEY,
                                "keyLocation": f"{SITE}/{KEY}.txt"})
    for ep in ENDPOINTS:
        try:
            with urllib.request.urlopen(f"{ep}?{q}", timeout=20) as r:
                print(f"{ep}: {r.status}")
        except urllib.error.HTTPError as e:
            # 202 — принято, ключ ещё проверяют; 403 — ключ не нашёлся на сайте;
            # 422 — адрес не с того домена, что ключ; 429 — слишком часто.
            print(f"{ep}: {e.code} {e.reason}")
        except Exception as e:
            print(f"{ep}: не достучались ({type(e).__name__})")


if __name__ == "__main__":
    ping(*sys.argv[1:2])
