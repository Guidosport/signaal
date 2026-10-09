#!/usr/bin/env python3
"""Generate clean PNG app icons (no external deps) for the Signaal PWA.
Draws a sound-wave glyph on a purple-to-orange gradient."""
import struct, zlib, math, os

ACCENT = (255, 84, 54)      # brand accent (coral)
WHITE  = (255, 255, 255)
S = 512                      # master render size (supersampled)

def blank(w, h, color):
    return [[list(color) for _ in range(w)] for _ in range(h)]

def blend(buf, x, y, color, a):
    if x < 0 or y < 0 or x >= len(buf[0]) or y >= len(buf):
        return
    p = buf[y][x]
    for i in range(3):
        p[i] = int(p[i] * (1 - a) + color[i] * a)

def fill_disc(buf, cx, cy, r, color):
    for y in range(int(cy - r - 1), int(cy + r + 2)):
        for x in range(int(cx - r - 1), int(cx + r + 2)):
            d = math.hypot(x - cx, y - cy)
            a = max(0.0, min(1.0, r - d + 0.5))
            if a > 0:
                blend(buf, x, y, color, a)

def ring(buf, cx, cy, r_out, r_in, color):
    for y in range(int(cy - r_out - 1), int(cy + r_out + 2)):
        for x in range(int(cx - r_out - 1), int(cx + r_out + 2)):
            d = math.hypot(x - cx, y - cy)
            a_out = max(0.0, min(1.0, r_out - d + 0.5))
            a_in = max(0.0, min(1.0, d - r_in + 0.5))
            a = min(a_out, a_in)
            if a > 0:
                blend(buf, x, y, color, a)

def thick_line(buf, x0, y0, x1, y1, w, color):
    steps = int(math.hypot(x1 - x0, y1 - y0)) + 1
    for i in range(steps + 1):
        t = i / steps
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        fill_disc(buf, x, y, w / 2, color)

def round_rect(buf, x0, y0, x1, y1, r, color):
    thick_line(buf, x0 + r, y0, x1 - r, y0, 1, color)  # noop guard
    for y in range(int(y0), int(y1) + 1):
        for x in range(int(x0), int(x1) + 1):
            dx = max(x0 + r - x, 0, x - (x1 - r))
            dy = max(y0 + r - y, 0, y - (y1 - r))
            d = math.hypot(dx, dy)
            a = max(0.0, min(1.0, r - d + 0.5)) if (dx > 0 and dy > 0) else 1.0
            if x0 <= x <= x1 and y0 <= y <= y1:
                blend(buf, x, y, color, a)

def downscale(buf, src, dst):
    out = blank(dst, dst, (0, 0, 0))
    scale = src / dst
    for y in range(dst):
        for x in range(dst):
            r = g = b = 0.0
            cnt = 0
            for sy in range(int(y * scale), int((y + 1) * scale)):
                for sx in range(int(x * scale), int((x + 1) * scale)):
                    p = buf[sy][sx]
                    r += p[0]; g += p[1]; b += p[2]; cnt += 1
            out[y][x] = [int(r / cnt), int(g / cnt), int(b / cnt)]
    return out

def write_png(path, buf):
    h = len(buf); w = len(buf[0])
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            raw += bytes(buf[y][x])
    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 9)
    with open(path, "wb") as f:
        f.write(sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))

# --- compose master ---
PURPLE = (124, 58, 237)
ORANGE = (255, 122, 26)
buf = blank(S, S, PURPLE)
for y in range(S):            # diagonale verloop paars -> oranje
    for x in range(S):
        t = (x + y) / (2 * S)
        buf[y][x] = [int(PURPLE[i] + (ORANGE[i] - PURPLE[i]) * t) for i in range(3)]
cx = cy = S / 2
# geluidsgolf: afgeronde staven van verschillende hoogte
heights = [70, 150, 250, 330, 250, 150, 70]
gap = 58
for i, h in enumerate(heights):
    x = cx + (i - 3) * gap
    thick_line(buf, x, cy - h / 2, x, cy + h / 2, 34, WHITE)

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
icons = os.path.join(here, "icons")
write_png(os.path.join(icons, "icon-512.png"), buf)
write_png(os.path.join(icons, "icon-192.png"), downscale(buf, S, 192))
write_png(os.path.join(icons, "apple-touch-icon.png"), downscale(buf, S, 180))
print("icons written")
