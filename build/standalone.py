#!/usr/bin/env python3
"""Собирает index.html в один самодостаточный .html.

Картинки и шрифты вшиты внутрь, внешних файлов не остаётся:
такой файл открывается двойным кликом, сервер не нужен, можно переслать.

  python3 standalone.py
"""
import base64, pathlib, re

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
SRC  = ROOT / "index.html"
DST  = ROOT / "linda-site.html"


def uri(rel, mime):
    return f"data:{mime};base64," + base64.b64encode((ROOT / rel).read_bytes()).decode()


def main():
    s = SRC.read_text(encoding="utf-8")

    for w in (500, 600, 800):
        s = s.replace(f'url("assets/fonts/Jost-{w}.woff2")',
                      'url("%s")' % uri(f"assets/fonts/Jost-{w}.woff2", "font/woff2"))

    for f in ("collage-sheet.webp", "collage-sheet-sm.webp"):
        s = s.replace(f'url("assets/{f}")', 'url("%s")' % uri("assets/" + f, "image/webp"))

    # предзагрузка внешних файлов в автономной версии не нужна
    s = re.sub(r'<link rel="preload"[^>]*>\s*', "", s)

    # герой: по одному кадру на десктоп и на телефон, остальные размеры не нужны —
    # всё равно всё лежит внутри файла и экономии от srcset нет
    d = uri("assets/hero/hero-wide-2880.avif", "image/avif")
    m = uri("assets/hero/hero-tall-1200.avif", "image/avif")
    pic = (
        '  <picture>\n'
        '    <source media="(min-width:900px)" srcset="' + d + '">\n'
        '    <img class="hero__img" src="' + m + '" fetchpriority="high" decoding="async"\n'
        '         alt="Линда с группой на сцене под открытым небом, зал с поднятыми руками">\n'
        '  </picture>'
    )
    s = re.sub(r'  <picture>.*?</picture>', lambda _: pic, s, flags=re.S)

    DST.write_text(s, encoding="utf-8")

    left = re.findall(r'(?:src|href|url\()="?(assets/[^"\')]+)', s)
    print(f"собрано: {DST}")
    print(f"размер:  {DST.stat().st_size / 1048576:.2f} МБ")
    print("внешних файлов:", ", ".join(sorted(set(left))) if left else "нет, файл автономный")


if __name__ == "__main__":
    main()
