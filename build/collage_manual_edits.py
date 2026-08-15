#!/usr/bin/env python3
"""Точечные правки DSCF-коллажа по указаниям из чата 2026-08-03.

Применять ПОСЛЕ collage_dscf_test.py: тот пишет collage_order_dscf.json,
а этот скрипт правит его и пересобирает полотно. Повторный запуск
test-скрипта правки сотрёт — тогда прогнать этот ещё раз.

Правки:
  · клавишник в белом дыму (i12, ряд 2 кол 5 — правая половина телефона)
    съезжает на ряд ниже, в i20;
  · толпа с руками (9767), стоявшая в i20, выходит из коллажа;
  · в i12 встаёт тёмный кадр 9237 (не использовался);
  · на десктопе i18 (Линда у стойки) меняется местами с i29 (сцена с экраном).
"""
import subprocess, pathlib, math, json

BUILD = pathlib.Path(__file__).parent
SRC   = pathlib.Path("/Users/pqresty/Documents/claude/фото сайт")
COLS, ROWS = 8, 4
N = COLS * ROWS
ORDER = BUILD / "collage_order_dscf.json"

def probe(p):
    rgb = subprocess.run(["ffmpeg","-v","error","-i",str(p),"-vf","scale=1:1",
        "-f","rawvideo","-pix_fmt","rgb24","-frames:v","1","-"],capture_output=True).stdout[:3]
    g = subprocess.run(["ffmpeg","-v","error","-i",str(p),"-vf","format=gray,scale=9:8",
        "-f","rawvideo","-pix_fmt","gray","-frames:v","1","-"],capture_output=True).stdout
    bits, spot = 0, 0
    if len(g) >= 72:
        for y in range(8):
            for x in range(8):
                bits = (bits << 1) | (1 if g[y*9+x] > g[y*9+x+1] else 0)
        spot = sum(sorted(g[:72])[-10:]) / 10
    return (tuple(rgb) if len(rgb) == 3 else (0,0,0)), bits, spot

order = json.loads(ORDER.read_text(encoding="utf-8"))
assert len(order) == N

# --- правки -----------------------------------------------------------------
kb = order[12]                       # клавишник
assert kb == "DSCF9091_resized.jpg", f"в i12 неожиданно {kb}"
assert order[20] == "DSCF9767_resized.jpg", f"в i20 неожиданно {order[20]}"
order[20] = kb
order[12] = "DSCF9237_resized.jpg"
order[18], order[29] = order[29], order[18]

# --- контроль: не появилось ли похожих соседей ------------------------------
files = {n: SRC / n for n in order}
meta = {}
for n, p in files.items():
    rgb, h, spot = probe(p)
    meta[n] = {"rgb": rgb, "hash": h, "spot": spot}
shoot = {n: i for i, n in enumerate(sorted(set(order)))}

def dist(a, b):
    dc = math.sqrt(sum((meta[a]["rgb"][i]-meta[b]["rgb"][i])**2 for i in range(3)))
    dh = bin(meta[a]["hash"] ^ meta[b]["hash"]).count("1")
    ds = min(abs(shoot[a]-shoot[b]), 12)
    return dh*8.0 + dc + ds*3.0

worst, wpair = 1e9, None
for r in range(ROWS):
    for c in range(COLS):
        i = r*COLS+c
        for j in ((i+1) if c+1 < COLS else None, (i+COLS) if r+1 < ROWS else None):
            if j is None: continue
            d = dist(order[i], order[j])
            if d < worst: worst, wpair = d, (order[i], order[j])
print(f"самая похожая пара соседей после правок: {worst:.0f}  ({wpair[0]} / {wpair[1]})")
spots = [sum(meta[order[r*COLS+c]]["spot"] for r in range(ROWS))/ROWS for c in range(COLS)]
print("пятна по колонкам:", " ".join(f"{v:.0f}" for v in spots))

ORDER.write_text(json.dumps(order, ensure_ascii=False, indent=1), encoding="utf-8")

# --- сборка полотна (как в test-скрипте) ------------------------------------
seq = BUILD / "seq_dscf"
subprocess.run(["rm","-rf",str(seq)]); seq.mkdir(parents=True)
for k, n in enumerate(order, 1):
    subprocess.run(["cp", str(SRC/n), str(seq/f"{k:03d}.jpg")])

norm = BUILD / "norm_dscf"
subprocess.run(["rm","-rf",str(norm)]); norm.mkdir(parents=True)
for f in sorted(seq.glob("*.jpg")):
    subprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(f),
        "-vf","scale=440:440:force_original_aspect_ratio=increase,crop=440:440,format=yuvj420p",
        "-pix_fmt","yuvj420p","-q:v","3",str(norm/f.name)])

fmts = {subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
        "-show_entries","stream=pix_fmt","-of","csv=p=0",str(f)],
        capture_output=True,text=True).stdout.strip() for f in norm.glob("*.jpg")}
assert len(fmts) == 1, f"форматы разъехались: {fmts}"

raw = BUILD / "collage_raw_dscf.jpg"
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(norm/"%03d.jpg"),
                "-vf",f"tile={COLS}x{ROWS}","-frames:v","1",str(raw)])
for name, crop in (("верхний","3520:440:0:0"), ("нижний","3520:440:0:1320")):
    b = subprocess.run(["ffmpeg","-v","error","-i",str(raw),"-vf",
        f"crop={crop},format=gray,scale=1:1","-f","rawvideo","-pix_fmt","gray","-frames:v","1","-"],
        capture_output=True).stdout
    assert b and b[0] > 5, f"{name} ряд полотна пустой"

A = BUILD.parent / "assets"
subprocess.run(["cwebp","-q","68","-m","5","-quiet","-resize","2400","0",str(raw),"-o",str(A/"collage-sheet-dscf.webp")])
subprocess.run(["cwebp","-q","58","-m","5","-quiet","-resize","1280","0",str(raw),"-o",str(A/"collage-sheet-dscf-sm.webp")])
print("полотно пересобрано с правками")
