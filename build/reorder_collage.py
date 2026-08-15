#!/usr/bin/env python3
"""Раскладывает кадры в сетку 8x4 так, чтобы соседи не были похожи.

Похожесть считается по трём признакам сразу:
  · перцептивный хеш (dHash) — ловит одинаковый сюжет и композицию,
    даже если цвет разный. Средний цвет этого не видит;
  · средний цвет — один и тот же сценический свет;
  · номер файла — кадры одной съёмки идут подряд.
"""
import subprocess, pathlib, math, random, json

SRC   = pathlib.Path("/Users/pqresty/Documents/claude/фото сайт")
BUILD = pathlib.Path(__file__).parent
COLS, ROWS = 8, 4
N = COLS * ROWS

def probe(p):
    """Возвращает (средний цвет, dHash) одним проходом ffmpeg на каждый признак."""
    rgb = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(p), "-vf", "scale=1:1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-frames:v", "1", "-"],
        capture_output=True).stdout[:3]
    g = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(p), "-vf", "format=gray,scale=9:8",
         "-f", "rawvideo", "-pix_fmt", "gray", "-frames:v", "1", "-"],
        capture_output=True).stdout
    bits = 0
    if len(g) >= 72:
        for y in range(8):
            for x in range(8):
                bits = (bits << 1) | (1 if g[y*9+x] > g[y*9+x+1] else 0)
    return tuple(rgb) if len(rgb) == 3 else (0, 0, 0), bits

files = sorted(SRC.glob("*.jpg"))
print(f"кадров: {len(files)} — считаю цвет и хеш…")
info = []
for i, p in enumerate(files):
    rgb, h = probe(p)
    info.append({"path": p, "rgb": rgb, "hash": h, "shoot": i})

def ham(a, b):
    return bin(a ^ b).count("1")          # 0 = одинаковые, 64 = максимально разные

def dist(a, b):
    dc = math.sqrt(sum((a["rgb"][i] - b["rgb"][i]) ** 2 for i in range(3)))
    dh = ham(a["hash"], b["hash"])
    ds = min(abs(a["shoot"] - b["shoot"]), 12)
    # хеш весомее цвета: именно он ловит «то же самое другими словами»
    return dh * 8.0 + dc + ds * 3.0

# отбираем N кадров, максимально непохожих друг на друга
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

def score(grid):
    """Главное — поднять САМУЮ похожую пару соседей.
    Сумма идёт вторым приоритетом: её можно набрать, стерпев пару плохих
    соседей, а нам важно чтобы плохих не было вовсе."""
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
    return worst * 1000 + total

def worst_pair(grid):
    return min(dist(grid[i], grid[j]) for i in range(N) for j in neighbours(i))

random.seed(11)
grid = chosen[:]
random.shuffle(grid)
best = score(grid)
for _ in range(200000):
    i, j = random.randrange(N), random.randrange(N)
    if i == j: continue
    grid[i], grid[j] = grid[j], grid[i]
    s = score(grid)
    if s > best: best = s
    else: grid[i], grid[j] = grid[j], grid[i]

print(f"суммарная разнородность: {best:.0f}")
print(f"самая похожая пара соседей: {worst_pair(grid):.0f} (чем больше, тем лучше)")
mh = min(ham(grid[i]["hash"], grid[j]["hash"]) for i in range(N) for j in neighbours(i))
print(f"минимальная разница хешей у соседей: {mh} из 64")

seq = BUILD / "seq2"
subprocess.run(["rm", "-rf", str(seq)]); seq.mkdir(parents=True)
for k, d in enumerate(grid, 1):
    subprocess.run(["cp", str(d["path"]), str(seq / f"{k:03d}.jpg")])
(BUILD / "collage_order.json").write_text(
    json.dumps([d["path"].name for d in grid], ensure_ascii=False, indent=1), encoding="utf-8")
print(f"разложено в {seq}")

# ---- сборка полотна -------------------------------------------------------
# ВАЖНО: перед плиткой кадры приводятся не только к одному размеру, но и к
# одному формату пикселей. Один кадр в yuvj444p среди yuvj420p заставляет
# фильтр tile пересоздаться и выбросить всё накопленное — в полотне окажется
# пустой ряд. То же самое раньше случалось из-за разных размеров.
norm = BUILD / "norm2"
subprocess.run(["rm", "-rf", str(norm)]); norm.mkdir(parents=True)
for f in sorted(seq.glob("*.jpg")):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(f),
        "-vf", "scale=440:440:force_original_aspect_ratio=increase,crop=440:440,format=yuvj420p",
        "-pix_fmt", "yuvj420p", "-q:v", "3", str(norm / f.name)])

fmts = {subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
        "-show_entries","stream=pix_fmt","-of","csv=p=0",str(f)],
        capture_output=True, text=True).stdout.strip() for f in norm.glob("*.jpg")}
assert len(fmts) == 1, f"форматы разъехались: {fmts}"

raw = BUILD / "collage_raw2.jpg"
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(norm/"%03d.jpg"),
                "-vf","tile=%dx%d" % (COLS, ROWS), "-frames:v","1", str(raw)])

# контроль: если ряд пустой, его средняя яркость будет 0
for name, crop in (("верхний","3520:440:0:0"), ("нижний","3520:440:0:1320")):
    b = subprocess.run(["ffmpeg","-v","error","-i",str(raw),"-vf",
        f"crop={crop},format=gray,scale=1:1","-f","rawvideo","-pix_fmt","gray","-frames:v","1","-"],
        capture_output=True).stdout
    lum = b[0] if b else 0
    assert lum > 5, f"{name} ряд полотна пустой — плитка собралась не полностью"
    print(f"  {name} ряд: яркость {lum}")

A = BUILD.parent / "assets"
subprocess.run(["cwebp","-q","68","-m","5","-quiet","-resize","2400","0",str(raw),"-o",str(A/"collage-sheet.webp")])
subprocess.run(["cwebp","-q","58","-m","5","-quiet","-resize","1280","0",str(raw),"-o",str(A/"collage-sheet-sm.webp")])
for f in ("collage-sheet.webp","collage-sheet-sm.webp"):
    print(f"  {f}: {(A/f).stat().st_size/1024:.0f} КБ")
print("полотно готово")
