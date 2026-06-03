#!/usr/bin/env python3
"""
Draw the governance comparison diagram programmatically using PIL/Pillow.
Two side-by-side panels: stitched point tools vs one governed platform.
"""
from PIL import Image, ImageDraw, ImageFont
import os

# ─── Canvas setup ───────────────────────────────────────────────────────────
W, H = 3200, 1900
img = Image.new("RGB", (W, H), "white")
draw = ImageDraw.Draw(img)

# ─── Colors ──────────────────────────────────────────────────────────────────
RED_FILL    = "#FEE2E2"
RED_BORDER  = "#DC2626"
RED_TEXT    = "#7F1D1D"
RED_CAPTION = "#991B1B"

GRN_FILL    = "#DCFCE7"
GRN_BORDER  = "#16A34A"
GRN_TEXT    = "#14532D"
GRN_CAPTION = "#14532D"

PANEL_L_BG  = "#FFF5F5"
PANEL_L_BOR = "#EF4444"
PANEL_R_BG  = "#F0FDF4"
PANEL_R_BOR = "#16A34A"
GOV_BG      = "#A7F3D0"
GOV_BOR     = "#059669"
ARROW_RED   = "#DC2626"
TITLE_COLOR = "#1E1E2E"

# ─── Fonts ───────────────────────────────────────────────────────────────────
def load_font(size, bold=False):
    for d in ["/System/Library/Fonts/", "/Library/Fonts/",
              "/System/Library/Fonts/Supplemental/"]:
        for c in (["Arial Bold.ttf","Helvetica.ttc","ArialHB.ttc"] if bold
                  else ["Arial.ttf","Helvetica.ttc","Arial Unicode.ttf"]):
            path = os.path.join(d, c)
            if os.path.exists(path):
                try: return ImageFont.truetype(path, size)
                except: pass
    return ImageFont.load_default()

TITLE_FONT   = load_font(62, bold=True)
PANEL_FONT   = load_font(50, bold=True)
BOX_TITLE    = load_font(40, bold=True)
SUB_FONT     = load_font(32)
CAPTION_FONT = load_font(36)
LABEL_FONT   = load_font(28)
GOV_HDR_FONT = load_font(34, bold=True)

# ─── Helpers ─────────────────────────────────────────────────────────────────
def rrect(draw, xy, r=20, fill=None, outline=None, lw=3):
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=lw)

def tw(draw, text, font):
    b = draw.textbbox((0,0), text, font=font)
    return b[2]-b[0]

def ctext(draw, cx, y, text, font, fill):
    w = tw(draw, text, font)
    draw.text((cx - w//2, y), text, font=font, fill=fill)

def bidir_v(draw, cx, y1, y2, color, label, font):
    draw.line([(cx, y1), (cx, y2)], fill=color, width=5)
    draw.polygon([(cx-11, y1+20), (cx+11, y1+20), (cx, y1)], fill=color)
    draw.polygon([(cx-11, y2-20), (cx+11, y2-20), (cx, y2)], fill=color)
    mid = (y1+y2)//2
    ctext(draw, cx, mid - font.size//2, label, font, color)

def bidir_h(draw, cy, x1, x2, color, label, font):
    draw.line([(x1, cy), (x2, cy)], fill=color, width=5)
    draw.polygon([(x1+20, cy-11), (x1+20, cy+11), (x1, cy)], fill=color)
    draw.polygon([(x2-20, cy-11), (x2-20, cy+11), (x2, cy)], fill=color)
    mid = (x1+x2)//2
    # label above the arrow line
    ctext(draw, mid, cy - font.size - 10, label, font, color)

# ─── Title ───────────────────────────────────────────────────────────────────
PAD  = 70
TITL = 45
ctext(draw, W//2, TITL, "One governed platform vs. stitching point tools together",
      TITLE_FONT, TITLE_COLOR)

# ─── Panel boundaries ────────────────────────────────────────────────────────
PT = 145          # panel top
PB = H - 60       # panel bottom
MID = W // 2
GW  = 60          # gap between panels

LX0, LY0, LX1, LY1 = PAD, PT, MID - GW//2, PB
RX0, RY0, RX1, RY1 = MID + GW//2, PT, W - PAD, PB

rrect(draw, [LX0, LY0, LX1, LY1], r=28, fill=PANEL_L_BG, outline=PANEL_L_BOR, lw=5)
rrect(draw, [RX0, RY0, RX1, RY1], r=28, fill=PANEL_R_BG, outline=PANEL_R_BOR, lw=5)

L_CX = (LX0 + LX1) // 2
R_CX = (RX0 + RX1) // 2

ctext(draw, L_CX, LY0 + 22, "Stitched Point Tools", PANEL_FONT, "#C41919")
ctext(draw, R_CX, RY0 + 22, "One Governed Platform", PANEL_FONT, "#145A2C")

# ─── LEFT: 3×2 grid of tool boxes ────────────────────────────────────────────
TOOLS = [
    "Vector database",
    "Transactional Postgres",
    "Data warehouse",
    "Model gateway",
    "App hosting",
    "Eval tool",
]

# Fit two wide boxes inside left panel with comfortable margins
L_INNER_W = LX1 - LX0 - 120   # usable width inside left panel
BW = (L_INNER_W - 160) // 2   # box width: half minus gap
BH = 160
HG = 160                        # horizontal gap between columns
VG = 100                        # vertical gap between rows

GRID_W = 2 * BW + HG
GRID_H = 3 * BH + 2 * VG

gx0 = L_CX - GRID_W // 2       # grid left edge
CAPTION_H = 70
gy0 = LY0 + 108 + ((LY1 - LY0 - 108 - CAPTION_H) - GRID_H) // 2

pos = {}
for row in range(3):
    for col in range(2):
        x0 = gx0 + col * (BW + HG)
        y0 = gy0 + row * (BH + VG)
        pos[(row, col)] = (x0, y0, x0 + BW, y0 + BH)

for i, name in enumerate(TOOLS):
    row, col = i // 2, i % 2
    x0, y0, x1, y1 = pos[(row, col)]
    rrect(draw, [x0, y0, x1, y1], r=18, fill=RED_FILL, outline=RED_BORDER, lw=4)
    cx = (x0+x1)//2
    cy = (y0+y1)//2
    ctext(draw, cx, cy - BOX_TITLE.size - 4, name, BOX_TITLE, RED_TEXT)
    ctext(draw, cx, cy + 6, "separate security model", SUB_FONT, "#B91C1C")

# vertical bidir arrows
for row in range(2):
    for col in range(2):
        _, _, _, y_b = pos[(row, col)]
        _, y_t, _, _ = pos[(row+1, col)]
        cx = (pos[(row, col)][0] + pos[(row, col)][2]) // 2
        bidir_v(draw, cx, y_b, y_t, ARROW_RED, "data copy", LABEL_FONT)

# horizontal bidir arrows (drawn in gap between columns, with label above midpoint)
for row in range(3):
    x0l, y0l, x1l, y1l = pos[(row, 0)]
    x0r, y0r, x1r, y1r = pos[(row, 1)]
    cy = (y0l + y1l) // 2
    bidir_h(draw, cy, x1l, x0r, ARROW_RED, "data copy", LABEL_FONT)

# Caption
ctext(draw, L_CX, LY1 - CAPTION_H + 16,
      "N credentials  ·  copies cross boundaries  ·  larger attack surface",
      CAPTION_FONT, RED_CAPTION)

# ─── RIGHT: Governed boundary ─────────────────────────────────────────────────
GI = ["memory", "data", "tools", "model", "observability"]
GBW = 440; GBH = 130; GVG = 38; GPH = 55; GPV = 48; GHDR = 56

inner_h = len(GI) * GBH + (len(GI)-1) * GVG
gtot_h  = GHDR + GPV + inner_h + GPV
gtot_w  = GBW + 2 * GPH

CAPTION_H_R = 70
avail_h = (RY1 - CAPTION_H_R) - (RY0 + 100)
gy_gov0 = RY0 + 100 + (avail_h - gtot_h) // 2
gy_gov1 = gy_gov0 + gtot_h
gx_gov0 = R_CX - gtot_w // 2
gx_gov1 = R_CX + gtot_w // 2

rrect(draw, [gx_gov0, gy_gov0, gx_gov1, gy_gov1], r=24,
      fill=GOV_BG, outline=GOV_BOR, lw=5)

ctext(draw, R_CX, gy_gov0 + 14,
      "one governance plane — one credential model", GOV_HDR_FONT, "#065F46")

iy = gy_gov0 + GHDR + GPV
for i, item in enumerate(GI):
    bx0 = R_CX - GBW//2; bx1 = R_CX + GBW//2
    by0 = iy; by1 = iy + GBH
    rrect(draw, [bx0, by0, bx1, by1], r=16, fill=GRN_FILL, outline=GRN_BORDER, lw=3)
    ctext(draw, R_CX, by0 + (GBH - BOX_TITLE.size)//2, item, BOX_TITLE, GRN_TEXT)
    if i < len(GI) - 1:
        draw.line([(R_CX, by1), (R_CX, by1+GVG)], fill=GRN_BORDER, width=3)
    iy += GBH + GVG

ctext(draw, R_CX, gy_gov1 + 44,
      "one credential model  ·  no data movement  ·  one lineage graph",
      CAPTION_FONT, GRN_CAPTION)

# ─── Save ────────────────────────────────────────────────────────────────────
out = "/Users/sara.dooley/projects/tps-memory-agent/docs/diagrams/governance.png"
img.save(out, "PNG", dpi=(144, 144))
print(f"Saved {out} ({os.path.getsize(out):,} bytes)  {W}x{H}px")
