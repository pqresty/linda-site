#!/usr/bin/env python3
"""Собирает папку site/ — ровно то, что выкладывается на хостинг.

Берёт index.html, вычитывает из него все ссылки на локальные файлы
и копирует только их. Прототипы, исходники и лишние размеры не попадают.

  python3 deploy.py
"""
import pathlib, re, shutil, subprocess

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
OUT  = ROOT / "site"

# Страницы-примерки. Ни с чего не слинкованы, наружу видны только по прямому
# адресу — нужны, чтобы смотреть варианты с телефона. Убрать: очистить список.
EXTRA = ["transitions.html", "mobile-crop.html", "scrim.html"]

# Файлы для роботов. На них никто не ссылается — поисковик берёт их по
# фиксированному адресу, поэтому в списке ссылок они не всплывут никогда.
ROBOTS = ["robots.txt", "sitemap.xml"]

# Свой домен. Пока пусто — GitHub раздаёт сайт по адресу вида
# pqresty.github.io/linda-site/. Как только записи DNS будут указывать на
# GitHub, впишите сюда "lindaconcerts.ru": сборка положит рядом файл CNAME,
# и Pages переключится на домен и выпустит сертификат.
# ВАЖЕН ПОРЯДОК: сначала DNS, потом эта строка. Наоборот — Pages начнёт
# перенаправлять на домен, которого ещё нет, и сайт на время пропадёт.
DOMAIN = "lindaconcerts.ru"


def referenced(html_text):
    """Все локальные пути из src / href / srcset / url().

    Отпечаток содержимого (?v=…) с пути снимаем: на диске файл лежит без него."""
    paths = set()
    paths |= set(re.findall(r'(?:src|href)="(?!https?:|data:|#|mailto:|tel:)([^"]+)"', html_text))
    paths |= set(re.findall(r'url\("(?!data:)([^"]+)"\)', html_text))
    for ss in re.findall(r'srcset="([^"]+)"', html_text):
        for part in ss.split(","):
            p = part.strip().split()[0]
            if p and not p.startswith(("http", "data:")):
                paths.add(p)
    # Картинка для соцсетей и разметки указывается абсолютным адресом — иначе
    # телеграм и вконтакте её не заберут. В src/href она при этом не попадает,
    # поэтому любой путь вида assets/… забираем, где бы он в странице ни лежал.
    paths |= set(re.findall(
        r'assets/[A-Za-z0-9._/-]+\.(?:webp|avif|woff2|svg|jpg|jpeg|png)', html_text))
    return sorted(p.split("?", 1)[0] for p in paths)


def main():
    pages = ["index.html"] + [p for p in EXTRA if (ROOT / p).exists()]
    files = set()
    for p in pages:
        files |= set(referenced((ROOT / p).read_text(encoding="utf-8")))
    files = sorted(files)

    if OUT.exists():
        for p in OUT.iterdir():
            if p.name != ".git":
                shutil.rmtree(p) if p.is_dir() else p.unlink()
    OUT.mkdir(exist_ok=True)

    total = 0
    for p in pages + [r for r in ROBOTS if (ROOT / r).exists()]:
        shutil.copy2(ROOT / p, OUT / p)
        total += (OUT / p).stat().st_size
    missing = []
    for rel in files:
        src = ROOT / rel
        if not src.exists():
            missing.append(rel); continue
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        total += dst.stat().st_size

    # GitHub Pages иначе прогоняет всё через Jekyll и может съесть папки с _
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    if DOMAIN:
        (OUT / "CNAME").write_text(DOMAIN + "\n", encoding="utf-8")
        print(f"свой домен: {DOMAIN}")

    if missing:
        print("НЕ НАЙДЕНЫ:", *missing, sep="\n  ")
    print(f"собрано: {OUT}")
    print(f"страниц: {len(pages)} ({', '.join(pages)})")
    print(f"файлов: {len(files) + len(pages)}, вес: {total/1048576:.2f} МБ")

    # контроль: не осталось ли в готовой папке ссылок на то, чего мы не положили
    left = sorted({f for p in pages
                   for f in referenced((OUT / p).read_text(encoding="utf-8"))
                   if not (OUT / f).exists()})
    print("битых путей:", left if left else "нет")

    if not (OUT / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=OUT)
        print("git-репозиторий создан")


if __name__ == "__main__":
    main()
