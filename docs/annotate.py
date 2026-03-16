#!/usr/bin/env python3
"""
Adds numbered callout circles to window_layout.png and appends a key strip.
Output: window_layout_annotated.png
"""
from PIL import Image, ImageDraw, ImageFont
import os

HERE  = os.path.dirname(os.path.abspath(__file__))
SRC   = os.path.join(HERE, 'window_layout.png')
DST   = os.path.join(HERE, 'window_layout_annotated.png')

FONT_REG  = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

# ── Image dimensions: 1499 × 978 ─────────────────────────────────────────────
#
#  Coordinate notes (light-theme screenshot):
#  Button row:  y ≈ 35–78   (band buttons only — All, 40m … 10m)
#  SWR plot:    x ≈ 77–1345,  y ≈ 100–455
#  Imp plot:    x ≈ 77–1345,  y ≈ 475–840
#  Toolbar:     y ≈ 930–978   (Home/Pan/Zoom/Save | Dark | Minimum SWR by band)

# ── Callouts: (dot_x, dot_y, number, description) ────────────────────────────
CALLOUTS = [
    # ── top button row ──────────────────────────────────────────────────────
    ( 490,  57,  1, "Band zoom buttons  (All, 40 m … 10 m)"),

    # ── SWR plot ─────────────────────────────────────────────────────────────
    ( 175, 310,  2, "SWR data curve  (one per loaded file)"),
    ( 163, 118,  3, "Ham-band label & colour shading"),
    ( 490, 440,  4, "Band-minimum SWR marker  (dot + value)"),
    ( 700, 443,  5, "Reference lines  (SWR 1.5 : 1 / 2 : 1 / 3 : 1)"),
    (1340, 133,  6, "SWR plot legend"),

    # ── Impedance plot ───────────────────────────────────────────────────────
    ( 290, 595,  7, "R — resistance  (solid line, Ω)"),
    ( 260, 730,  8, "X — reactance  (dashed line, Ω)"),
    ( 700, 660,  9, "Zero-impedance reference line"),
    (1340, 505, 10, "Impedance plot legend"),

    # ── toolbar ──────────────────────────────────────────────────────────────
    (  85, 950, 11, "Matplotlib toolbar  (pan / zoom / save)"),
    ( 193, 950, 12, "Dark / Light theme toggle button"),
    ( 313, 950, 13, "Minimum SWR by band popup button"),
]

# ── Layout constants ──────────────────────────────────────────────────────────
KEY_H       = 340     # pixels added at the bottom for the key strip
CR          = 14      # callout circle radius (slightly larger for readability)
CIRC_FILL   = (90, 20, 140)
CIRC_BORDER = (255, 255, 255)

COL1_X = 30           # key column 1 left edge
COL2_X = 762          # key column 2 left edge  (≈ image centre)
COL_LINE_H  = 40      # vertical spacing between key rows (> 2*(CR+2) to avoid overlap)

# ── Load & extend canvas ──────────────────────────────────────────────────────
img   = Image.open(SRC).convert('RGB')
W, H  = img.size

canvas = Image.new('RGB', (W, H + KEY_H), (248, 248, 248))
canvas.paste(img, (0, 0))

draw = ImageDraw.Draw(canvas)

# Separator line between image and key
draw.rectangle([(0, H), (W, H + 2)], fill='#b0b0b0')

# ── Fonts ─────────────────────────────────────────────────────────────────────
try:
    f_key   = ImageFont.truetype(FONT_REG,  16)
    f_num   = ImageFont.truetype(FONT_BOLD, 13)
    f_title = ImageFont.truetype(FONT_BOLD, 18)
except Exception:
    f_key = f_num = f_title = ImageFont.load_default()


def draw_circle(x, y, number):
    """Draw a filled numbered circle at (x, y)."""
    r = CR
    # White halo so circle stands out over any background colour
    draw.ellipse([x-r-2, y-r-2, x+r+2, y+r+2], fill=CIRC_BORDER)
    draw.ellipse([x-r,   y-r,   x+r,   y+r],   fill=CIRC_FILL)
    label = str(number)
    bb = draw.textbbox((0, 0), label, font=f_num)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    draw.text((x - tw // 2, y - th // 2 - 1), label,
              fill='white', font=f_num)


def draw_key_row(col_x, row_y, number, description):
    """Draw one row in the key strip."""
    cx = col_x + CR + 2
    cy = row_y + CR + 2
    draw.ellipse([cx-CR-2, cy-CR-2, cx+CR+2, cy+CR+2], fill=CIRC_BORDER)
    draw.ellipse([cx-CR,   cy-CR,   cx+CR,   cy+CR],   fill=CIRC_FILL)
    label = str(number)
    bb = draw.textbbox((0, 0), label, font=f_num)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    draw.text((cx - tw // 2, cy - th // 2 - 1), label,
              fill='white', font=f_num)
    draw.text((col_x + CR*2 + 8, row_y + 3), description,
              fill='#1a1a1a', font=f_key)


# ── Draw callout circles on the image ────────────────────────────────────────
for dot_x, dot_y, num, _ in CALLOUTS:
    draw_circle(dot_x, dot_y, num)

# ── Key strip ─────────────────────────────────────────────────────────────────
draw.text((COL1_X, H + 8), "Key:", fill='#333333', font=f_title)

col1 = [(n, d) for _, _, n, d in CALLOUTS if n <= 6]
col2 = [(n, d) for _, _, n, d in CALLOUTS if n >  6]

y1 = H + 32
for num, desc in col1:
    draw_key_row(COL1_X, y1, num, desc)
    y1 += COL_LINE_H

y2 = H + 32
for num, desc in col2:
    draw_key_row(COL2_X, y2, num, desc)
    y2 += COL_LINE_H

# ── Save ─────────────────────────────────────────────────────────────────────
canvas.save(DST, optimize=True)
print(f"Saved {DST}  ({W} × {H + KEY_H} px)")
