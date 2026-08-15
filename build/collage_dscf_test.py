#!/usr/bin/env python3
"""ТЕСТ: коллаж 8x4 только из кадров DSCF — один фотограф, проще договориться.

Метод тот же, что в reorder_collage.py: dHash + средний цвет + номер съёмки,
жадный отбор самых непохожих, потом 200k перестановок под максимин соседей.
Пишет отдельные файлы *-dscf.webp — боевые collage-sheet*.webp не трогает.
"""
import subprocess, pathlib, math, random, json, re

SRC   = pathlib.Path("/Users/pqresty/Documents/claude/фото сайт")
BUILD = pathlib.Path(__file__).parent
COLS, ROWS = 8, 4
N = COLS * ROWS

def probe(p):
    rgb = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(p), "-vf", "scale=1:1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-frames:v", "1", "-"],
        capture_output=True).stdout[:3]
    g = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(p), "-vf", "format=gray,scale=9:8",
         "-f", "rawvideo", "-pix_fmt", "gray", "-frames:v", "1", "-"],
        capture_output=True).stdout
    bits = 0
    spot = 0
    if len(g) >= 72:
        for y in range(8):
            for x in range(8):
                bits = (bits << 1) | (1 if g[y*9+x] > g[y*9+x+1] else 0)
        # «светлое пятно»: не средняя яркость, а среднее по самым светлым
        # клеткам — тёмный кадр с одной вспышкой света ловится именно так
        spot = sum(sorted(g[:72])[-10:]) / 10
    return tuple(rgb) if len(rgb) == 3 else (0, 0, 0), bits, spot

# только DSCF; один и тот же кадр может лежать оригиналом и _resized —
# считаем по номеру съёмки и берём одну копию (resized быстрее в обработке)
by_shot = {}
for p in sorted(SRC.glob("DSCF*.jpg")):
    shot = re.match(r"DSCF(\d+)", p.name).group(1)
    if shot not in by_shot or "_resized" in p.name:
        by_shot[shot] = p
files = [by_shot[k] for k in sorted(by_shot)]
print(f"кадров DSCF (уникальных): {len(files)} — считаю цвет и хеш…")

info = []
for i, p in enumerate(files):
    rgb, h, spot = probe(p)
    info.append({"path": p, "rgb": rgb, "hash": h, "shoot": i, "spot": spot,
                 "luma": 0.299*rgb[0] + 0.587*rgb[1] + 0.114*rgb[2]})

def ham(a, b): return bin(a ^ b).count("1")

def dist(a, b):
    dc = math.sqrt(sum((a["rgb"][i] - b["rgb"][i]) ** 2 for i in range(3)))
    ds = min(abs(a["shoot"] - b["shoot"]), 12)
    return ham(a["hash"], b["hash"]) * 8.0 + dc + ds * 3.0

start = max(info, key=lambda d: sum(d["rgb"]))
pool = [d for d in info if d is not start]
chosen = [start]
while len(chosen) < N and pool:
    best = max(pool, key=lambda c: min(dist(c, s) for s in chosen))
    chosen.append(best); pool.remove(best)

def neighbours(i):
    r, c = divmod(i, COLS)
    for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        rr, cc = r + dr, c + dc
        if 0 <= rr < ROWS and 0 <= cc < COLS:
            yield rr * COLS + cc

# Светлым кадрам нельзя стоять слева: там на сайте основной текст. Вес по
# колонкам штрафует яркость слева и поощряет справа. Колонка 4 — компромисс:
# на десктопе над ней ещё висят названия городов, а на телефоне cover
# показывает только центральные колонки, и 4-я — левая половина его экрана,
# 5-я — правая. Поэтому 4-я умеренно тёмная, света начинаются с 5-й.
W = [1.0, 0.9, 0.8, 0.8, -0.5, -0.35, -0.5, -0.55]

def placement(grid):
    return sum(grid[r*COLS+c]["spot"] * W[c] for r in range(ROWS) for c in range(COLS))

def score(grid):
    total, worst = 0, 1e9
    for r in range(ROWS):
        for c in range(COLS):
            i = r * COLS + c
            for j in ((i + 1) if c + 1 < COLS else None,
                      (i + COLS) if r + 1 < ROWS else None):
                if j is None: continue
                d = dist(grid[i], grid[j])
                total += d
                if d < worst: worst = d
    # приоритеты: непохожесть соседей (максимин) > света не слева > сумма
    return worst * 2000 + total - placement(grid) * 60

random.seed(11)
# стартуем не со случайной раскладки, а с посаженной по яркости:
# тёмные — в левые колонки, светлые — в правые; перестановки дальше
# наводят непохожесть соседей, не разваливая зонирование
cols_by_w = sorted(range(COLS), key=lambda c: W[c], reverse=True)   # тёмным — большие веса
by_dark = sorted(chosen, key=lambda d: d["spot"])
grid = [None] * N
k = 0
for c in cols_by_w:
    for r in range(ROWS):
        grid[r*COLS+c] = by_dark[k]; k += 1
best = score(grid)
for _ in range(200000):
    i, j = random.randrange(N), random.randrange(N)
    if i == j: continue
    grid[i], grid[j] = grid[j], grid[i]
    s = score(grid)
    if s > best: best = s
    else: grid[i], grid[j] = grid[j], grid[i]

worst = min(dist(grid[i], grid[j]) for i in range(N) for j in neighbours(i))
mh = min(ham(grid[i]["hash"], grid[j]["hash"]) for i in range(N) for j in neighbours(i))
print(f"самая похожая пара соседей: {worst:.0f}, мин. разница хешей: {mh} из 64")
for k_, name in (("luma","средняя яркость"), ("spot","яркость пятен")):
    vals = [sum(grid[r*COLS+c][k_] for r in range(ROWS)) / ROWS for c in range(COLS)]
    print(f"{name} по колонкам:", " ".join(f"{v:.0f}" for v in vals))

seq = BUILD / "seq_dscf"
subprocess.run(["rm", "-rf", str(seq)]); seq.mkdir(parents=True)
for k, d in enumerate(grid, 1):
    subprocess.run(["cp", str(d["path"]), str(seq / f"{k:03d}.jpg")])
(BUILD / "collage_order_dscf.json").write_text(
    json.dumps([d["path"].name for d in grid], ensure_ascii=False, indent=1), encoding="utf-8")

# нормализация размера И формата пикселей — см. грабли в reorder_collage.py
norm = BUILD / "norm_dscf"
subprocess.run(["rm", "-rf", str(norm)]); norm.mkdir(parents=True)
for f in sorted(seq.glob("*.jpg")):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(f),
        "-vf", "scale=440:440:force_original_aspect_ratio=increase,crop=440:440,format=yuvj420p",
        "-pix_fmt", "yuvj420p", "-q:v", "3", str(norm / f.name)])

fmts = {subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
        "-show_entries","stream=pix_fmt","-of","csv=p=0",str(f)],
        capture_output=True, text=True).stdout.strip() for f in norm.glob("*.jpg")}
assert len(fmts) == 1, f"форматы разъехались: {fmts}"

raw = BUILD / "collage_raw_dscf.jpg"
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(norm/"%03d.jpg"),
                "-vf","tile=%dx%d" % (COLS, ROWS), "-frames:v","1", str(raw)])

for name, crop in (("верхний","3520:440:0:0"), ("нижний","3520:440:0:1320")):
    b = subprocess.run(["ffmpeg","-v","error","-i",str(raw),"-vf",
        f"crop={crop},format=gray,scale=1:1","-f","rawvideo","-pix_fmt","gray","-frames:v","1","-"],
        capture_output=True).stdout
    assert b and b[0] > 5, f"{name} ряд полотна пустой"

A = BUILD.parent / "assets"
subprocess.run(["cwebp","-q","68","-m","5","-quiet","-resize","2400","0",str(raw),"-o",str(A/"collage-sheet-dscf.webp")])
subprocess.run(["cwebp","-q","58","-m","5","-quiet","-resize","1280","0",str(raw),"-o",str(A/"collage-sheet-dscf-sm.webp")])
for f in ("collage-sheet-dscf.webp","collage-sheet-dscf-sm.webp"):
    print(f"  {f}: {(A/f).stat().st_size/1024:.0f} КБ")
print("тестовое полотно готово")
