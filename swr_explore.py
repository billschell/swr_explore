#!/usr/bin/env python3
"""
swr_explore.py  –  NanoVNA .s1p SWR & Impedance Analyzer

Author: Bill Schell w/Claude

Usage:
    python3 swr_explore.py [--help] file1.s1p [file2.s1p ...]

Arguments:
    file1.s1p [file2.s1p ...]
        One or more Touchstone .s1p files exported from a NanoVNA.
        Multiple files are overlaid on the same plots for comparison.
        File names are used as labels, so short descriptive names work best.

    --help
        Show this message and exit.

Supported .s1p formats:
    RI  (default)  Real + imaginary parts of S11
    MA             Magnitude + angle in degrees
    DB             dB magnitude + angle in degrees

Controls:
    Mouse hover          – show frequency, SWR, and impedance tooltip
    Left click           – pin tooltip at that frequency (click again to remove)
    Right click          – reset zoom and Y scales
    Scroll wheel         – zoom in/out on the frequency axis
    Band buttons (top)   – zoom to that ham band; Y axes auto-scale
    Toolbar ⌂ Home       – reset zoom and clear all pinned tooltips
    Toolbar 💾 Save      – save figure to the current directory
    Toolbar Dark/Light   – toggle dark and light colour themes
    Toolbar Min SWR      – open per-band minimum SWR comparison table
"""

import sys
import os
import math
import signal
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.widgets import Button
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch

# ── Band data (freq only; colours live in _BAND_COLORS) ──────────────────────
BANDS = [
    ("2200m",   0.1357,    0.1378),
    ("630m",    0.472,     0.479),
    ("160m",    1.800,     2.000),
    ("80m",     3.500,     4.000),
    ("60m",     5.330,     5.410),
    ("40m",     7.000,     7.300),
    ("30m",    10.100,    10.150),
    ("20m",    14.000,    14.350),
    ("17m",    18.068,    18.168),
    ("15m",    21.000,    21.450),
    ("12m",    24.890,    24.990),
    ("10m",    28.000,    29.700),
    ("6m",     50.000,    54.000),
    ("4m",     70.000,    70.500),
    ("2m",    144.000,   148.000),
    ("1.25m", 222.000,   225.000),
    ("70cm",  420.000,   450.000),
    ("33cm",  902.000,   928.000),
    ("23cm", 1240.000,  1300.000),
]

_BAND_COLORS = {
    'light': [
        "#f3e5f5","#e1f5fe","#fce4d6","#fff0cc","#e8f5e9",
        "#fff3cd","#d4edda","#cce5ff","#f8d7da","#e2d9f3",
        "#fde2d8","#d1ecf1","#fff9c4","#f0f4c3","#e8eaf6",
        "#fce4ec","#e0f2f1","#fff3e0","#f1f8e9",
    ],
    'dark': [
        "#3d1a5c","#0d3a5c","#5c2a0d","#4a3500","#0d3a1a",
        "#4a3800","#0d3a22","#0d2a4a","#4a0d1a","#251040",
        "#4a1a0d","#0d2e3a","#4a3d00","#2a3800","#0d1e4a",
        "#4a0d2a","#002a2a","#4a2200","#0d2a00",
    ],
}

SWR_CAP = 50
IMP_CAP = 2000

# Medium-saturation data colours that read clearly on both light and dark.
COLORS = ['#e53935', '#1e88e5', '#43a047', '#fb8c00',
          '#8e24aa', '#6d4c41', '#e91e63']

THEMES = {
    'light': dict(
        bg_fig='#f5f5f5',    bg_axes='#ffffff',
        fg='#333333',         fg_muted='#666666',
        spine='#cccccc',
        grid_mj='#cccccc',   grid_mj_a=0.8,
        grid_mn='#e8e8e8',   grid_mn_a=0.8,
        band_alpha=0.40,
        zero_color='black',  zero_alpha=0.40,
        ref_colors=('green', 'orange', 'royalblue'),
        band_label='#444444',
        leg_face='#f5f5f5',  leg_edge='#cccccc',
        title_color='#222222',
        hover_fc='lightyellow', hover_ec='#aaaaaa',
        hover_fg='#333333',     hover_arrow='#666666',
        pin_fc='#e6f2ff',    pin_ec='#4a90d9',
        pin_fg='#333333',    pin_arrow='#4a90d9',
        btn_base='#e8e8e8',  btn_hover='#b8d0ee',
        btn_shadow='#999999', btn_highlight='#ffffff',
        btn_fg='#333333',    mswr_fg='#1a56a0',
        toggle_label='Dark',
        marker_edge='white',
    ),
    'dark': dict(
        bg_fig='#1e1e1e',    bg_axes='#252526',
        fg='#cccccc',         fg_muted='#888888',
        spine='#4a4a4a',
        grid_mj='#3a3a3a',   grid_mj_a=0.9,
        grid_mn='#2e2e2e',   grid_mn_a=0.9,
        band_alpha=0.55,
        zero_color='#888888', zero_alpha=0.50,
        ref_colors=('#66bb6a', '#ffa726', '#64b5f6'),
        band_label='#888888',
        leg_face='#2a2a2a',  leg_edge='#4a4a4a',
        title_color='#cccccc',
        hover_fc='#2a2a2a',  hover_ec='#666666',
        hover_fg='#cccccc',  hover_arrow='#888888',
        pin_fc='#1a2a3a',    pin_ec='#4a90d9',
        pin_fg='#cccccc',    pin_arrow='#4a90d9',
        btn_base='#3c3c3c',  btn_hover='#1e4070',
        btn_shadow='#060606', btn_highlight='#686868',
        btn_fg='#cccccc',    mswr_fg='#5ba3f5',
        toggle_label='Light',
        marker_edge='#1e1e1e',
    ),
}


# ── S1P parser ────────────────────────────────────────────────────────────────
def parse_s1p(path):
    freqs, swrs, R_vals, X_vals = [], [], [], []
    fmt = "RI"
    z0  = 50.0
    with open(path) as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith('!'):
                continue
            if s.startswith('#'):
                parts = s.upper().split()
                if   'MA' in parts: fmt = "MA"
                elif 'DB' in parts: fmt = "DB"
                else:               fmt = "RI"
                if 'R' in parts:
                    try:
                        z0 = float(parts[parts.index('R') + 1])
                    except (IndexError, ValueError):
                        pass
                continue
            parts = s.split()
            if len(parts) < 3:
                continue
            freq_hz = float(parts[0])
            a, b    = float(parts[1]), float(parts[2])
            if fmt == "RI":
                re, im = a, b
            elif fmt == "MA":
                re = a * math.cos(math.radians(b))
                im = a * math.sin(math.radians(b))
            else:
                mag = 10 ** (a / 20.0)
                re  = mag * math.cos(math.radians(b))
                im  = mag * math.sin(math.radians(b))
            mag = math.sqrt(re**2 + im**2)
            swr = (1 + mag) / (1 - mag) if mag < 1.0 else 999.0
            denom = (1 - re)**2 + im**2
            if denom > 1e-12:
                Zr = z0 * (1 - re**2 - im**2) / denom
                Zi = z0 * (2 * im)             / denom
            else:
                Zr, Zi = 1e6, 0.0
            freqs.append(freq_hz / 1e6)
            swrs.append(min(swr, SWR_CAP))
            R_vals.append(float(np.clip(Zr, -IMP_CAP, IMP_CAP)))
            X_vals.append(float(np.clip(Zi, -IMP_CAP, IMP_CAP)))
    return (np.array(freqs), np.array(swrs),
            np.array(R_vals), np.array(X_vals))


def find_band_minima(freqs, swrs):
    results = []
    for name, flo, fhi in BANDS:
        mask = (freqs >= flo) & (freqs <= fhi)
        if not mask.any():
            continue
        sub_idx = np.where(mask)[0]
        best    = int(np.argmin(swrs[sub_idx]))
        gi      = sub_idx[best]
        results.append((name, float(freqs[gi]), float(swrs[gi])))
    return results


def band_of(fx):
    for name, flo, fhi in BANDS:
        if flo <= fx <= fhi:
            return f"  [{name}]"
    return ""


def tip_text(ds, idx):
    fx  = float(ds['freqs'][idx])
    sy  = float(ds['swrs'][idx])
    Rv  = float(ds['R'][idx])
    Xv  = float(ds['X'][idx])
    swr_s   = f">{SWR_CAP}" if sy >= SWR_CAP else f"{sy:.2f}"
    sign    = '+' if Xv >= 0 else ''
    clipped = "  (clipped)" if abs(Rv) >= IMP_CAP or abs(Xv) >= IMP_CAP else ""
    return (f"{fx:.4f} MHz{band_of(fx)}\n"
            f"SWR {swr_s}\n"
            f"Z = {Rv:.1f}{sign}{Xv:.1f}j Ω{clipped}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    args = sys.argv[1:]
    if not args or '--help' in args:
        print(__doc__)
        sys.exit(0 if '--help' in args else 1)

    datasets = []
    for path in args:
        if not os.path.exists(path):
            print(f"Warning: {path} not found – skipped")
            continue
        freqs, swrs, R, X = parse_s1p(path)
        if len(freqs) == 0:
            print(f"Warning: no data in {path} – skipped")
            continue
        datasets.append(dict(label=os.path.basename(path),
                             freqs=freqs, swrs=swrs, R=R, X=X))
    if not datasets:
        print("No valid files loaded.")
        sys.exit(1)

    # ── Theme state ───────────────────────────────────────────────────────────
    _theme = {'current': 'light'}

    # Artists we need to re-theme on toggle
    _A = dict(
        band_patches=[],   # [(swr_span, imp_span), …] per BAND entry
        ref_lines=[],      # [3:1, 2:1, 1.5:1]
        zero_line=None,
        band_labels=[],    # Text objects
        legs=[],           # [leg_swr, leg_imp]
        title_text=None,
        btn_data=[],       # [{'btn','shadow','highlight','face','is_mswr'}, …]
        tk_toggle=None,    # Tkinter Button in the toolbar
        tk_mswr=None,      # Tkinter Min SWR button in the toolbar
        dot_artists=[],    # Line2D markers for band minima
    )

    # ── Figure ────────────────────────────────────────────────────────────────
    matplotlib.rcParams['savefig.directory'] = os.getcwd()
    win_title = "SWR Chart: " + "  ".join(ds['label'] for ds in datasets)
    fig = plt.figure(win_title, figsize=(15, 9))
    fig.patch.set_facecolor(THEMES['light']['bg_fig'])

    try:
        from PIL import ImageTk, Image as PILImage
        from Xlib import display as Xdisplay
        _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'resources', 'icon.png')
        _win = fig.canvas.manager.window
        _xid = _win.winfo_id()
        _d   = Xdisplay.Display()
        _xw  = _d.create_resource_object('window', _xid)
        _xw.set_wm_class('swr_chart', 'swr_chart')
        _d.flush()
        _d.close()
        def _apply_icon():
            try:
                _img = ImageTk.PhotoImage(PILImage.open(_icon_path))
                _win.iconphoto(True, _img)
                _win._icon_img = _img
            except Exception:
                pass
        _win.after(200, _apply_icon)
    except Exception:
        pass

    ax_swr = fig.add_axes([0.07, 0.50, 0.91, 0.40])
    ax_imp = fig.add_axes([0.07, 0.08, 0.91, 0.37], sharex=ax_swr)

    # ── Band shading ──────────────────────────────────────────────────────────
    T0 = THEMES['light']
    for i, (_, flo, fhi) in enumerate(BANDS):
        c = _BAND_COLORS['light'][i]
        sp_swr = ax_swr.axvspan(flo, fhi, alpha=T0['band_alpha'], color=c, zorder=1)
        sp_imp = ax_imp.axvspan(flo, fhi, alpha=T0['band_alpha'], color=c, zorder=1)
        _A['band_patches'].append((sp_swr, sp_imp))

    # ── Reference lines ───────────────────────────────────────────────────────
    _ref_specs = [
        (3.0, 'green',     '--', 'SWR 3:1'),
        (2.0, 'orange',    ':',  'SWR 2:1'),
        (1.5, 'royalblue', '--', 'SWR 1.5:1'),
    ]
    for swr_val, col, ls, lbl in _ref_specs:
        ln = ax_swr.axhline(swr_val, color=col, ls=ls, lw=1,
                            alpha=0.75, zorder=2, label=lbl)
        _A['ref_lines'].append(ln)
    _A['zero_line'] = ax_imp.axhline(0, color='black', lw=0.6,
                                     alpha=0.4, zorder=2)

    # ── Data curves ───────────────────────────────────────────────────────────
    for i, ds in enumerate(datasets):
        color = COLORS[i % len(COLORS)]
        ax_swr.plot(ds['freqs'], ds['swrs'], color=color, lw=2.0,
                    zorder=3, label=ds['label'])
        for _, fx, sy in find_band_minima(ds['freqs'], ds['swrs']):
            dot, = ax_swr.plot(fx, sy, 'o', color=color, ms=5, zorder=5,
                               markeredgecolor='white', markeredgewidth=0.5)
            _A['dot_artists'].append(dot)
            ax_swr.text(fx, sy - 1.0, f"{sy:.1f}",
                        ha='center', va='top', fontsize=7,
                        color=color, zorder=5, fontweight='bold')
        ax_imp.plot(ds['freqs'], ds['R'], color=color, lw=2.0,
                    zorder=3, label=f"{ds['label']} — R")
        ax_imp.plot(ds['freqs'], ds['X'], color=color, lw=2.0,
                    ls='--', alpha=0.75, zorder=3, label=f"{ds['label']} — X")

    # ── Axes limits & initial tick setup ──────────────────────────────────────
    fdata_lo = max(min(ds['freqs'][0]  for ds in datasets), 0.1)
    fdata_hi =     max(ds['freqs'][-1] for ds in datasets)
    view_lo  = fdata_lo
    view_hi  = fdata_hi

    ax_swr.set_xlim(view_lo, view_hi)
    ax_swr.set_ylim(1.0, SWR_CAP + 1)
    ax_imp.set_ylim(-IMP_CAP, IMP_CAP)

    for ax in (ax_swr, ax_imp):
        ax.set_facecolor(T0['bg_axes'])
        for sp in ax.spines.values():
            sp.set_edgecolor(T0['spine'])
        ax.tick_params(colors=T0['fg'], which='both')
        ax.yaxis.label.set_color(T0['fg'])
        ax.xaxis.label.set_color(T0['fg'])
        ax.xaxis.set_major_locator(ticker.MultipleLocator(1.0))
        ax.xaxis.set_minor_locator(ticker.MultipleLocator(0.5))
        ax.tick_params(axis='x', which='minor', length=4)
        ax.grid(True, which='major', color=T0['grid_mj'], alpha=T0['grid_mj_a'], zorder=0)
        ax.grid(True, which='minor', color=T0['grid_mn'], alpha=T0['grid_mn_a'], ls=':', zorder=0)

    ax_swr.yaxis.set_major_locator(ticker.MultipleLocator(5))
    ax_swr.yaxis.set_minor_locator(ticker.MultipleLocator(1))
    ax_imp.yaxis.set_major_locator(ticker.MultipleLocator(500))
    ax_imp.yaxis.set_minor_locator(ticker.MultipleLocator(100))

    ax_swr.tick_params(axis='x', labelsize=8, rotation=45)
    ax_imp.tick_params(axis='x', labelsize=8, rotation=45)
    ax_swr.tick_params(axis='y', labelsize=8)
    ax_imp.tick_params(axis='y', labelsize=8)

    ax_swr.set_ylabel('SWR (50 Ω)', fontsize=10)
    ax_imp.set_ylabel(f'Impedance (Ω, clipped ±{IMP_CAP})', fontsize=10)
    ax_imp.set_xlabel('Frequency (MHz)', fontsize=10)

    # ── Band labels ───────────────────────────────────────────────────────────
    for name, flo, fhi in BANDS:
        if fhi < view_lo or flo > view_hi:
            continue
        mid  = (flo + fhi) / 2
        frac = (mid - view_lo) / max(view_hi - view_lo, 1e-6)
        lx   = max(flo, view_lo) if frac < 0.04 else mid
        ha   = 'left'            if frac < 0.04 else 'center'
        txt  = ax_swr.text(lx, SWR_CAP * 0.94, name,
                           ha=ha, va='top', fontsize=8,
                           fontweight='bold', color=T0['band_label'], zorder=4)
        _A['band_labels'].append(txt)

    # ── Adaptive tick spacing ─────────────────────────────────────────────────
    _TICK_STEPS = [
        (1000.0, 200.000, 50.000), ( 500.0, 100.000, 20.000),
        ( 200.0,  50.000, 10.000), ( 100.0,  20.000,  5.000),
        (  50.0,  10.000,  2.000), (  20.0,   5.000,  1.000),
        (  10.0,   2.000,  0.500), (   5.0,   1.000,  0.250),
        (   2.0,   0.500,  0.100), (   1.0,   0.250,  0.050),
        (   0.5,   0.100,  0.025), (   0.2,   0.050,  0.010),
        (   0.05,  0.020,  0.005), (   0.02,  0.010,  0.002),
        (   0.005, 0.002,  0.0005),(   0.0,   0.001,  0.0002),
    ]

    def _update_xticks(*_):
        lo, hi = ax_swr.get_xlim()
        span   = hi - lo
        major, minor = _TICK_STEPS[-1][1], _TICK_STEPS[-1][2]
        for max_span, maj, mn in _TICK_STEPS:
            if span > max_span:
                major, minor = maj, mn
                break
        for ax in (ax_swr, ax_imp):
            ax.xaxis.set_major_locator(ticker.MultipleLocator(major))
            ax.xaxis.set_minor_locator(ticker.MultipleLocator(minor))
        fig.canvas.draw_idle()

    ax_swr.callbacks.connect('xlim_changed', _update_xticks)

    _SWR_YTICKS = [
        (30.0, 10.0, 2.0), (15.0, 5.0,  1.0),  ( 8.0, 2.0,  0.5),
        ( 4.0,  1.0, 0.25),( 2.0, 0.5,  0.1),  ( 1.0, 0.25, 0.05),
        ( 0.0,  0.1, 0.02),
    ]
    _IMP_YTICKS = [
        (1500.0, 500.0, 100.0), ( 800.0, 250.0, 50.0), ( 400.0, 100.0, 25.0),
        ( 200.0,  50.0,  10.0), ( 100.0,  25.0,  5.0), (  50.0,  10.0,  2.0),
        (  20.0,   5.0,   1.0), (   0.0,   2.0,  0.5),
    ]

    def _pick_step(span, table):
        maj, mn = table[-1][1], table[-1][2]
        for max_span, m, n in table:
            if span > max_span:
                maj, mn = m, n
                break
        return maj, mn

    def _update_swr_yticks(*_):
        lo, hi = ax_swr.get_ylim()
        maj, mn = _pick_step(hi - lo, _SWR_YTICKS)
        ax_swr.yaxis.set_major_locator(ticker.MultipleLocator(maj))
        ax_swr.yaxis.set_minor_locator(ticker.MultipleLocator(mn))

    def _update_imp_yticks(*_):
        lo, hi = ax_imp.get_ylim()
        maj, mn = _pick_step(hi - lo, _IMP_YTICKS)
        ax_imp.yaxis.set_major_locator(ticker.MultipleLocator(maj))
        ax_imp.yaxis.set_minor_locator(ticker.MultipleLocator(mn))

    ax_swr.callbacks.connect('ylim_changed', _update_swr_yticks)
    ax_imp.callbacks.connect('ylim_changed', _update_imp_yticks)

    # ── Active bands / zoom ranges ────────────────────────────────────────────
    active_bands = [(n, lo, hi) for n, lo, hi in BANDS
                    if any(np.any((ds['freqs'] >= lo) & (ds['freqs'] <= hi))
                           for ds in datasets)]

    btn_labels = ["All"] + [b[0] for b in active_bands]
    btn_ranges = [(view_lo, view_hi)] + \
                 [(max(b[1] - min((b[2]-b[1])*2, 0.5), fdata_lo),
                   min(b[2] + min((b[2]-b[1])*2, 0.5), fdata_hi))
                  for b in active_bands]

    n   = len(btn_labels)
    bh  = 0.030
    by  = 0.955
    gap = 0.004
    bw  = (0.94 - (n - 1) * gap) / n
    bw  = max(0.035, min(bw, 0.091))
    total = n * bw + (n - 1) * gap
    bx0   = (1.0 - total) / 2.0

    def _fit_ylims(xlo, xhi):
        swr_vals, r_vals, x_vals = [], [], []
        for ds in datasets:
            mask = (ds['freqs'] >= xlo) & (ds['freqs'] <= xhi)
            if mask.any():
                swr_vals.extend(ds['swrs'][mask].tolist())
                r_vals.extend(ds['R'][mask].tolist())
                x_vals.extend(ds['X'][mask].tolist())
        if swr_vals:
            ax_swr.set_ylim(1.0, max(max(swr_vals) * 1.12, 3.0))
        if r_vals or x_vals:
            imin = min(r_vals + x_vals)
            imax = max(r_vals + x_vals)
            pad  = max((imax - imin) * 0.10, 50.0)
            ax_imp.set_ylim(max(imin - pad, -IMP_CAP),
                            min(imax + pad,  IMP_CAP))

    # ── 3-D button helper ─────────────────────────────────────────────────────
    def _make_btn_patches(ax_b, T):
        """Add shadow / highlight / face FancyBboxPatches; return their refs."""
        ax_b.set_axis_off()
        shadow = FancyBboxPatch(
            (0.08, 0.0), 0.92, 0.86,
            boxstyle="round,pad=0,rounding_size=0.18",
            transform=ax_b.transAxes,
            facecolor=T['btn_shadow'], edgecolor='none',
            linewidth=0, clip_on=False, zorder=0,
        )
        ax_b.add_patch(shadow)
        highlight = FancyBboxPatch(
            (0.0, 0.13), 0.92, 0.86,
            boxstyle="round,pad=0,rounding_size=0.18",
            transform=ax_b.transAxes,
            facecolor=T['btn_highlight'], edgecolor='none',
            linewidth=0, clip_on=False, zorder=1,
        )
        ax_b.add_patch(highlight)
        face_color = ax_b.get_facecolor()
        ax_b.patch.set_visible(False)
        face = FancyBboxPatch(
            (0.03, 0.09), 0.89, 0.85,
            boxstyle="round,pad=0,rounding_size=0.18",
            transform=ax_b.transAxes,
            facecolor=face_color, edgecolor='none',
            linewidth=0, clip_on=False, zorder=2,
        )
        ax_b.patch = face
        ax_b.add_patch(face)
        return shadow, highlight, face

    # ── Band zoom buttons ─────────────────────────────────────────────────────
    _btn_refs = []
    for j, (lbl, (rlo, rhi)) in enumerate(zip(btn_labels, btn_ranges)):
        ax_b = fig.add_axes([bx0 + j * (bw + gap), by, bw, bh])
        b    = Button(ax_b, lbl, color=T0['btn_base'], hovercolor=T0['btn_hover'])
        b.label.set_fontsize(9)
        b.label.set_color(T0['btn_fg'])
        sh, hl, fc = _make_btn_patches(ax_b, T0)
        _A['btn_data'].append({'btn': b, 'shadow': sh,
                               'highlight': hl, 'face': fc, 'is_mswr': False})
        def _make_cb(lo, hi):
            def cb(event):
                ax_swr.set_xlim(lo, hi)
                _fit_ylims(lo, hi)
                fig.canvas.draw_idle()
            return cb
        b.on_clicked(_make_cb(rlo, rhi))
        _btn_refs.append(b)

    # ── Title ─────────────────────────────────────────────────────────────────
    _A['title_text'] = fig.text(
        0.5, 0.924, "  vs  ".join(ds['label'] for ds in datasets),
        ha='center', va='bottom', fontsize=11, fontweight='bold',
        color=T0['title_color'])

    # ── Legends ───────────────────────────────────────────────────────────────
    swr_handles, swr_labels = ax_swr.get_legend_handles_labels()
    leg_swr = ax_swr.legend(swr_handles, swr_labels,
                            loc='upper right', fontsize=8)
    leg_swr.get_frame().set_facecolor(T0['leg_face'])
    leg_swr.get_frame().set_edgecolor(T0['leg_edge'])
    for txt in leg_swr.get_texts():
        txt.set_color(T0['fg'])

    imp_handles = [
        Line2D([0],[0], color='gray', lw=2, ls='-',  label='R (resistance)'),
        Line2D([0],[0], color='gray', lw=2, ls='--', label='X (reactance)'),
    ] + [Line2D([0],[0], color=COLORS[i % len(COLORS)], lw=2,
                label=ds['label']) for i, ds in enumerate(datasets)]
    leg_imp = ax_imp.legend(handles=imp_handles, loc='upper right', fontsize=8)
    leg_imp.get_frame().set_facecolor(T0['leg_face'])
    leg_imp.get_frame().set_edgecolor(T0['leg_edge'])
    for txt in leg_imp.get_texts():
        txt.set_color(T0['fg'])

    _A['legs'] = [leg_swr, leg_imp]

    # ── apply_theme ───────────────────────────────────────────────────────────
    def apply_theme(name):
        T  = THEMES[name]
        bc = _BAND_COLORS[name]

        fig.patch.set_facecolor(T['bg_fig'])

        for ax in (ax_swr, ax_imp):
            ax.set_facecolor(T['bg_axes'])
            for sp in ax.spines.values():
                sp.set_edgecolor(T['spine'])
            ax.tick_params(colors=T['fg'], which='both')
            ax.yaxis.label.set_color(T['fg'])
            ax.xaxis.label.set_color(T['fg'])
            ax.grid(True, which='major',
                    color=T['grid_mj'], alpha=T['grid_mj_a'], zorder=0)
            ax.grid(True, which='minor',
                    color=T['grid_mn'], alpha=T['grid_mn_a'], ls=':', zorder=0)

        for i, (sp_swr, sp_imp) in enumerate(_A['band_patches']):
            sp_swr.set_facecolor(bc[i])
            sp_swr.set_alpha(T['band_alpha'])
            sp_imp.set_facecolor(bc[i])
            sp_imp.set_alpha(T['band_alpha'])

        for line, color in zip(_A['ref_lines'], T['ref_colors']):
            line.set_color(color)

        _A['zero_line'].set_color(T['zero_color'])
        _A['zero_line'].set_alpha(T['zero_alpha'])

        for txt in _A['band_labels']:
            txt.set_color(T['band_label'])

        _A['title_text'].set_color(T['title_color'])

        for leg in _A['legs']:
            leg.get_frame().set_facecolor(T['leg_face'])
            leg.get_frame().set_edgecolor(T['leg_edge'])
            for txt in leg.get_texts():
                txt.set_color(T['fg'])

        for bd in _A['btn_data']:
            bd['shadow'].set_facecolor(T['btn_shadow'])
            bd['highlight'].set_facecolor(T['btn_highlight'])
            bd['face'].set_facecolor(T['btn_base'])
            bd['btn'].color     = T['btn_base']
            bd['btn'].hovercolor = T['btn_hover']
            bd['btn'].label.set_color(T['mswr_fg'] if bd['is_mswr'] else T['btn_fg'])

        for _tk_btn in (_A['tk_toggle'], _A['tk_mswr']):
            if _tk_btn is not None:
                _tk_btn.configure(
                    bg=T['btn_base'],
                    fg=T['btn_fg'],
                    activebackground=T['btn_hover'],
                    activeforeground=T['btn_fg'],
                )
        if _A['tk_toggle'] is not None:
            _A['tk_toggle'].configure(text=T['toggle_label'])

        hover_ann.get_bbox_patch().set_facecolor(T['hover_fc'])
        hover_ann.get_bbox_patch().set_edgecolor(T['hover_ec'])
        hover_ann.set_color(T['hover_fg'])

        for dot in _A['dot_artists']:
            dot.set_markeredgecolor(T['marker_edge'])

        _theme['current'] = name
        fig.canvas.draw_idle()

    def _on_toggle():
        apply_theme('dark' if _theme['current'] == 'light' else 'light')

    # ── Hover annotation ──────────────────────────────────────────────────────
    hover_ann = ax_swr.annotate(
        "", xy=(0, 0), xytext=(14, 14), textcoords="offset points",
        bbox=dict(boxstyle="round,pad=0.45", fc=T0['hover_fc'],
                  ec=T0['hover_ec'], alpha=0.93, lw=1),
        arrowprops=dict(arrowstyle="->", color=T0['hover_arrow'], lw=0.9),
        fontsize=9, zorder=12, visible=False, color=T0['hover_fg']
    )
    pinned = []

    def _show_hover(ds, idx):
        fx = float(ds['freqs'][idx])
        sy = float(ds['swrs'][idx])
        hover_ann.xy = (fx, sy)
        hover_ann.set_text(tip_text(ds, idx))
        xfrac = (fx - ax_swr.get_xlim()[0]) / \
                max(ax_swr.get_xlim()[1] - ax_swr.get_xlim()[0], 1e-6)
        hover_ann.set_position((-120, 14) if xfrac > 0.82 else (14, 14))
        hover_ann.set_visible(True)
        fig.canvas.draw_idle()

    def on_move(event):
        if event.inaxes not in (ax_swr, ax_imp):
            hover_ann.set_visible(False)
            fig.canvas.draw_idle()
            return
        ds  = datasets[0]
        idx = int(np.argmin(np.abs(ds['freqs'] - event.xdata)))
        _show_hover(ds, idx)

    def on_leave(event):
        hover_ann.set_visible(False)
        fig.canvas.draw_idle()

    def on_click(event):
        if event.inaxes not in (ax_swr, ax_imp):
            return
        T = THEMES[_theme['current']]
        if event.button == 1:
            ds  = datasets[0]
            idx = int(np.argmin(np.abs(ds['freqs'] - event.xdata)))
            fx  = float(ds['freqs'][idx])
            for pa in list(pinned):
                if abs(pa.xy[0] - fx) < 0.05:
                    pa.remove()
                    pinned.remove(pa)
                    fig.canvas.draw_idle()
                    return
            xfrac  = (fx - ax_swr.get_xlim()[0]) / \
                     max(ax_swr.get_xlim()[1] - ax_swr.get_xlim()[0], 1e-6)
            offset = (-130, 20) if xfrac > 0.82 else (14, 20)
            pa = ax_swr.annotate(
                tip_text(ds, idx),
                xy=(fx, float(ds['swrs'][idx])),
                xytext=offset, textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.45", fc=T['pin_fc'],
                          ec=T['pin_ec'], alpha=0.97, lw=1.2),
                arrowprops=dict(arrowstyle="->", color=T['pin_arrow'], lw=1),
                fontsize=8.5, zorder=13, color=T['pin_fg']
            )
            pinned.append(pa)
            fig.canvas.draw_idle()
        elif event.button == 3:
            ax_swr.set_xlim(view_lo, view_hi)
            ax_swr.set_ylim(1.0, SWR_CAP + 1)
            ax_imp.set_ylim(-IMP_CAP, IMP_CAP)
            fig.canvas.draw_idle()

    def on_scroll(event):
        if event.inaxes not in (ax_swr, ax_imp):
            return
        factor = 0.80 if event.button == 'up' else 1.0 / 0.80
        lo, hi = ax_swr.get_xlim()
        xd     = event.xdata
        ax_swr.set_xlim(xd - (xd - lo) * factor,
                        xd + (hi - xd) * factor)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect('motion_notify_event', on_move)
    fig.canvas.mpl_connect('axes_leave_event',    on_leave)
    fig.canvas.mpl_connect('button_press_event',  on_click)
    fig.canvas.mpl_connect('scroll_event',        on_scroll)

    # ── Toolbar patches ───────────────────────────────────────────────────────
    def clear_pins():
        for pa in list(pinned):
            pa.remove()
        pinned.clear()
        hover_ann.set_visible(False)
        fig.canvas.draw_idle()

    toolbar = fig.canvas.toolbar
    if hasattr(toolbar, '_buttons') and 'Home' in toolbar._buttons:
        def _home_and_clear():
            toolbar.home()
            clear_pins()
        toolbar._buttons['Home'].configure(command=_home_and_clear)

    for _btn_name in ('Back', 'Forward'):
        if hasattr(toolbar, '_buttons') and _btn_name in toolbar._buttons:
            toolbar._buttons[_btn_name].pack_forget()

    # ── Dark / Light toggle button in the Tk toolbar ──────────────────────────
    import tkinter as tk
    _sep = tk.Frame(toolbar, width=2, bd=1, relief='sunken')
    _sep.pack(side='left', fill='y', padx=6, pady=3)
    _tk_toggle = tk.Button(
        toolbar,
        text=T0['toggle_label'],
        command=_on_toggle,
        relief='raised', bd=2,
        bg=T0['btn_base'], fg=T0['btn_fg'],
        activebackground=T0['btn_hover'], activeforeground=T0['btn_fg'],
        font=('TkDefaultFont', 9, 'bold'),
        padx=10, pady=1,
    )
    _tk_toggle.pack(side='left', padx=2, pady=3)
    _A['tk_toggle'] = _tk_toggle

    _sep2 = tk.Frame(toolbar, width=2, bd=1, relief='sunken')
    _sep2.pack(side='left', fill='y', padx=6, pady=3)
    _tk_mswr = tk.Button(
        toolbar,
        text='Minimum SWR by band',
        command=lambda: show_min_swr_popup(),
        relief='raised', bd=2,
        bg=T0['btn_base'], fg=T0['btn_fg'],
        activebackground=T0['btn_hover'], activeforeground=T0['btn_fg'],
        font=('TkDefaultFont', 9, 'bold'),
        padx=10, pady=1,
    )
    _tk_mswr.pack(side='left', padx=2, pady=3)
    _A['tk_mswr'] = _tk_mswr

    # ── Min SWR popup ─────────────────────────────────────────────────────────
    _popup = {'win': None}

    def show_min_swr_popup():
        import tkinter as tk
        from tkinter import font as tkfont
        T = THEMES[_theme['current']]
        is_dark = (_theme['current'] == 'dark')

        try:
            if _popup['win'] and _popup['win'].winfo_exists():
                _popup['win'].destroy()
        except Exception:
            pass

        labels   = [ds['label'] for ds in datasets]
        per_band = {b[0]: {} for b in active_bands}
        for ds in datasets:
            for bname, freq, swr in find_band_minima(ds['freqs'], ds['swrs']):
                if bname in per_band:
                    per_band[bname][ds['label']] = (freq, swr)

        n_cols = len(labels)
        top    = tk.Toplevel()
        _popup['win'] = top
        top.title("Minimum SWR per Band")
        top.resizable(False, False)

        bg_win  = '#2d2d2d'   if is_dark else '#f5f5f5'
        bg_hdr  = '#2a3f6f'   if is_dark else '#b0bcee'
        fg_hdr  = '#c8d8f8'   if is_dark else '#222222'
        bg_band = '#3a3a3a'   if is_dark else '#e0e0e0'
        bg_cell = '#2d2d2d'   if is_dark else 'white'
        fg_cell = T['fg']
        bg_best = '#1a3a1a'   if is_dark else '#b8f0b8'
        bg_none = '#252525'   if is_dark else '#eeeeee'
        fg_none = '#555555'   if is_dark else '#888888'
        fg_star = '#5ba3f5'   if is_dark else '#0055cc'
        bg_foot = bg_win

        top.configure(bg=bg_win)
        PAD      = 6
        hdr_font  = tkfont.Font(family='TkDefaultFont', size=9, weight='bold')
        cell_font = tkfont.Font(family='TkDefaultFont', size=9)

        def _cf(parent, bg):
            return tk.Frame(parent, bg=bg, relief='ridge', bd=1)

        tk.Label(top, text="Band", font=hdr_font, bg=bg_hdr, fg=fg_hdr,
                 relief='ridge', bd=1, padx=PAD, pady=PAD
                 ).grid(row=0, column=0, sticky='nsew')
        for j, lbl in enumerate(labels):
            tk.Label(top, text=lbl, font=hdr_font, bg=bg_hdr, fg=fg_hdr,
                     relief='ridge', bd=1, padx=PAD, pady=PAD
                     ).grid(row=0, column=j + 1, sticky='nsew')

        for i, (bname, *_) in enumerate(active_bands):
            tk.Label(top, text=bname, font=hdr_font, bg=bg_band, fg=fg_cell,
                     relief='ridge', bd=1, padx=PAD, pady=PAD
                     ).grid(row=i + 1, column=0, sticky='nsew')

            best_swr = float('inf')
            for lbl in labels:
                if lbl in per_band[bname]:
                    _, swr = per_band[bname][lbl]
                    if swr < best_swr:
                        best_swr = swr

            for j, lbl in enumerate(labels):
                if lbl in per_band[bname]:
                    freq, swr = per_band[bname][lbl]
                    swr_str = f">{SWR_CAP}" if swr >= SWR_CAP else f"{swr:.2f}"
                    is_best = (n_cols > 1 and abs(swr - best_swr) < 1e-6)
                    bg = bg_best if is_best else bg_cell
                    frm = _cf(top, bg)
                    frm.grid(row=i + 1, column=j + 1, sticky='nsew')
                    line1 = tk.Frame(frm, bg=bg)
                    line1.pack(anchor='w', padx=PAD, pady=(PAD, 0))
                    tk.Label(line1, text=swr_str, font=cell_font,
                             bg=bg, fg=fg_cell).pack(side='left')
                    if is_best:
                        sf = tkfont.Font(family='TkDefaultFont', size=14)
                        tk.Label(line1, text=" ★", font=sf,
                                 bg=bg, fg=fg_star).pack(side='left')
                    tk.Label(frm, text=f"{freq:.4f} MHz", font=cell_font,
                             bg=bg, fg=T['fg_muted'], anchor='w'
                             ).pack(anchor='w', padx=PAD, pady=(0, PAD))
                else:
                    frm = _cf(top, bg_none)
                    frm.grid(row=i + 1, column=j + 1, sticky='nsew')
                    tk.Label(frm, text="—", font=cell_font,
                             bg=bg_none, fg=fg_none).pack(padx=PAD, pady=PAD)

        if n_cols > 1:
            tk.Label(top, text="★  = lowest SWR in band",
                     font=tkfont.Font(size=9), fg=fg_star, bg=bg_foot,
                     pady=4).grid(row=len(active_bands) + 1, column=0,
                                  columnspan=n_cols + 1)

        top.update_idletasks()
        top.lift()
        top.focus_force()

    # Apply initial theme to ensure consistency
    apply_theme('light')

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    plt.show()


if __name__ == "__main__":
    main()
