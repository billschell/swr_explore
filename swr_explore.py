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
    Toolbar 💡 icon      – toggle dark and light colour themes (right of Save)
    Toolbar Impedance▼▲  – show or hide the impedance panel
    Toolbar Min SWR      – open per-band minimum SWR comparison table
    Toolbar Smith Chart  – open a Smith Chart for the visible frequency range
"""

from __future__ import annotations

import dataclasses
import math
import os
import signal
import sys

import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
from matplotlib.widgets import Button

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

SWR_CAP   = 50
IMP_CAP   = 2000
# Minimum visible frequency span (MHz).  Keeps major X ticks at ≥ 0.001 MHz.
MIN_XSPAN = 0.005

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

# ── Lightbulb toolbar icon ─────────────────────────────────────────────────────
# 16×16 pixel masks: '1' = foreground colour, '0' = background colour.
# Lit  = solid filled globe (theme is dark → click to go light).
# Unlit = outline-only globe (theme is light → click to go dark).
_BULB_LIT = [
    "0000011111000000",
    "0000111111100000",
    "0001111111110000",
    "0011111111111000",
    "0011111111111000",
    "0011111111111000",
    "0001111111110000",
    "0000111111100000",
    "0000111111100000",
    "0000011111000000",
    "0000011111000000",
    "0000011111000000",
    "0000001110000000",
    "0000000000000000",
    "0000000000000000",
    "0000000000000000",
]
_BULB_UNLIT = [
    "0000011111000000",
    "0000100000100000",
    "0001000000010000",
    "0010000000001000",
    "0010000000001000",
    "0010000000001000",
    "0001000000010000",
    "0000100000100000",
    "0000111111100000",
    "0000011111000000",
    "0000011111000000",
    "0000011111000000",
    "0000001110000000",
    "0000000000000000",
    "0000000000000000",
    "0000000000000000",
]


def _make_bulb_photo(lit: bool, fg: str, bg: str) -> object:
    """Return a 16×16 tk.PhotoImage lightbulb icon.

    Args:
        lit: True for a solid filled bulb (dark theme active); False for outline only.
        fg:  Foreground colour string (the bulb drawing colour).
        bg:  Background colour string (the button face colour).
    """
    import tkinter as tk
    mask = _BULB_LIT if lit else _BULB_UNLIT
    img  = tk.PhotoImage(width=16, height=16)
    rows = ['{' + ' '.join(fg if ch == '1' else bg for ch in row) + '}'
            for row in mask]
    img.put(' '.join(rows))
    return img


# ── Tooltip helper ────────────────────────────────────────────────────────────

class Tooltip:
    """Lightweight hover tooltip for a Tk widget.

    Displays a small label below the widget on mouse-enter and destroys it on
    mouse-leave.  Call ``update_text()`` to change the message at any time.
    """

    def __init__(self, widget, text: str) -> None:
        self._widget = widget
        self._text   = text
        self._tip    = None
        widget.bind('<Enter>', self._show)
        widget.bind('<Leave>', self._hide)

    def update_text(self, text: str) -> None:
        self._text = text

    def _show(self, event=None) -> None:
        if self._tip is not None:
            return
        import tkinter as tk
        w   = self._widget
        x   = w.winfo_rootx() + w.winfo_width() // 2
        y   = w.winfo_rooty() + w.winfo_height() + 4
        tip = tk.Toplevel(w)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f'+{x}+{y}')
        tk.Label(
            tip, text=self._text, justify='left',
            bg='#ffffe0', fg='#333333',
            relief='solid', bd=1,
            font=('TkDefaultFont', 9), padx=6, pady=3,
        ).pack()
        self._tip = tip

    def _hide(self, event=None) -> None:
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


# ── Data container ────────────────────────────────────────────────────────────

@dataclasses.dataclass
class S1PDataset:
    """Parsed contents of one .s1p Touchstone file.

    Attributes:
        label: Short display name derived from the filename.
        freqs: Frequency array in MHz.
        swrs:  SWR array, clipped to SWR_CAP.
        rs:    Resistance (real part of Z) in ohms, clipped to ±IMP_CAP.
        xs:    Reactance (imaginary part of Z) in ohms, clipped to ±IMP_CAP.
    """
    label: str
    freqs: np.ndarray
    swrs:  np.ndarray
    rs:    np.ndarray
    xs:    np.ndarray


# ── Pure module-level functions ───────────────────────────────────────────────

def parse_s1p(path: str) -> S1PDataset:
    """Parse a Touchstone .s1p file and return an S1PDataset.

    Supports RI, MA, and DB formats.  The reference impedance is read from
    the ``#`` header line; any value other than 50 Ω is handled correctly.

    Raises:
        OSError: If the file cannot be opened.
    """
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
    return S1PDataset(
        label=os.path.basename(path),
        freqs=np.array(freqs),
        swrs=np.array(swrs),
        rs=np.array(R_vals),
        xs=np.array(X_vals),
    )


def find_band_minima(
    freqs: np.ndarray, swrs: np.ndarray
) -> list[tuple[str, float, float]]:
    """Return the minimum SWR point within each ham band.

    Returns:
        List of ``(band_name, frequency_MHz, swr)`` tuples, one per band
        that has at least one data point.
    """
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


def band_of(fx: float) -> str:
    """Return a bracketed band name for *fx* MHz, or an empty string."""
    for name, flo, fhi in BANDS:
        if flo <= fx <= fhi:
            return f"  [{name}]"
    return ""


def _format_tip(ds: S1PDataset, idx: int) -> str:
    """Format the hover/pin tooltip text for dataset *ds* at sample *idx*."""
    fx      = float(ds.freqs[idx])
    sy      = float(ds.swrs[idx])
    Rv      = float(ds.rs[idx])
    Xv      = float(ds.xs[idx])
    swr_s   = f">{SWR_CAP}" if sy >= SWR_CAP else f"{sy:.2f}"
    sign    = '+' if Xv >= 0 else ''
    clipped = "  (clipped)" if abs(Rv) >= IMP_CAP or abs(Xv) >= IMP_CAP else ""
    return (f"{fx:.4f} MHz{band_of(fx)}\n"
            f"SWR {swr_s}\n"
            f"Z = {Rv:.1f}{sign}{Xv:.1f}j Ω{clipped}")


# ── ThemeManager ──────────────────────────────────────────────────────────────

class ThemeManager:
    """Owns the active colour theme and applies it to all registered artists.

    Usage:
        1. Call ``register_*()`` once during figure setup to hand over artist
           references.
        2. Call ``apply(name)`` at any time to repaint everything atomically.
    """

    def __init__(self, initial: str = 'light') -> None:
        self._current: str = initial
        self._fig = None
        self._ax_swr = None
        self._ax_imp = None
        self._band_patches: list = []
        self._ref_lines: list    = []
        self._zero_line          = None
        self._band_labels: list  = []
        self._legs: list         = []
        self._title_text         = None
        self._dot_artists: list  = []
        self._btn_data: list     = []
        self._tk_toggle          = None   # special: also gets label text updated
        self._tk_buttons: list   = []     # all themed toolbar buttons
        self._hover_ann          = None

    # ── Registration ──────────────────────────────────────────────────────────

    def register_axes(self, fig: Figure, ax_swr: Axes, ax_imp: Axes) -> None:
        """Register the figure and both axes."""
        self._fig    = fig
        self._ax_swr = ax_swr
        self._ax_imp = ax_imp

    def register_band_patches(self, patches: list) -> None:
        """Register band background spans as ``(swr_span, imp_span)`` pairs."""
        self._band_patches = patches

    def register_ref_lines(self, lines: list) -> None:
        """Register the SWR reference lines [3:1, 2:1, 1.5:1]."""
        self._ref_lines = lines

    def register_zero_line(self, line) -> None:
        """Register the impedance zero-reference line."""
        self._zero_line = line

    def register_band_labels(self, labels: list) -> None:
        """Register band-name text artists."""
        self._band_labels = labels

    def register_legends(self, legs: list) -> None:
        """Register legend objects [leg_swr, leg_imp]."""
        self._legs = legs

    def register_title(self, text_artist) -> None:
        """Register the figure title text artist."""
        self._title_text = text_artist

    def register_dot_artists(self, dots: list) -> None:
        """Register the band-minima marker artists."""
        self._dot_artists = dots

    def register_band_buttons(self, btn_data: list) -> None:
        """Register band button styling dicts."""
        self._btn_data = btn_data

    def register_tk_buttons(self, toggle_btn, *extra_btns) -> None:
        """Register Tkinter toolbar buttons for theming.

        *toggle_btn* is also updated with the theme label text on each apply.
        Pass any number of additional buttons as extra positional arguments.
        """
        self._tk_toggle  = toggle_btn
        self._tk_buttons = [b for b in (toggle_btn, *extra_btns) if b is not None]

    def register_hover_ann(self, ann) -> None:
        """Register the hover annotation artist."""
        self._hover_ann = ann

    # ── Runtime ───────────────────────────────────────────────────────────────

    @property
    def current(self) -> str:
        """Name of the currently active theme (``'light'`` or ``'dark'``)."""
        return self._current

    @property
    def theme(self) -> dict:
        """The active theme token dictionary."""
        return THEMES[self._current]

    def toggle(self) -> None:
        """Switch between light and dark themes."""
        self.apply('dark' if self._current == 'light' else 'light')

    def apply(self, name: str) -> None:
        """Apply theme *name* to every registered artist and redraw."""
        T  = THEMES[name]
        bc = _BAND_COLORS[name]

        self._fig.patch.set_facecolor(T['bg_fig'])

        for ax in (self._ax_swr, self._ax_imp):
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

        for i, (sp_swr, sp_imp) in enumerate(self._band_patches):
            sp_swr.set_facecolor(bc[i])
            sp_swr.set_alpha(T['band_alpha'])
            sp_imp.set_facecolor(bc[i])
            sp_imp.set_alpha(T['band_alpha'])

        for line, color in zip(self._ref_lines, T['ref_colors']):
            line.set_color(color)

        if self._zero_line is not None:
            self._zero_line.set_color(T['zero_color'])
            self._zero_line.set_alpha(T['zero_alpha'])

        for txt in self._band_labels:
            txt.set_color(T['band_label'])

        if self._title_text is not None:
            self._title_text.set_color(T['title_color'])

        for leg in self._legs:
            leg.get_frame().set_facecolor(T['leg_face'])
            leg.get_frame().set_edgecolor(T['leg_edge'])
            for txt in leg.get_texts():
                txt.set_color(T['fg'])

        for bd in self._btn_data:
            bd['shadow'].set_facecolor(T['btn_shadow'])
            bd['highlight'].set_facecolor(T['btn_highlight'])
            bd['face'].set_facecolor(T['btn_base'])
            bd['btn'].color      = T['btn_base']
            bd['btn'].hovercolor = T['btn_hover']
            bd['btn'].label.set_color(
                T['mswr_fg'] if bd['is_mswr'] else T['btn_fg']
            )

        for tk_btn in self._tk_buttons:
            tk_btn.configure(
                bg=T['btn_base'], fg=T['btn_fg'],
                activebackground=T['btn_hover'],
                activeforeground=T['btn_fg'],
            )
        if self._tk_toggle is not None:
            img = _make_bulb_photo(name == 'dark', T['btn_fg'], T['btn_base'])
            self._tk_toggle._bulb_img = img   # prevent garbage collection
            self._tk_toggle.configure(image=img)

        if self._hover_ann is not None:
            self._hover_ann.get_bbox_patch().set_facecolor(T['hover_fc'])
            self._hover_ann.get_bbox_patch().set_edgecolor(T['hover_ec'])
            self._hover_ann.set_color(T['hover_fg'])

        for dot in self._dot_artists:
            dot.set_markeredgecolor(T['marker_edge'])

        self._current = name
        self._fig.canvas.draw_idle()


# ── AnnotationManager ─────────────────────────────────────────────────────────

class AnnotationManager:
    """Manages the hover tooltip and pinned tooltips on the SWR plot.

    Hover tooltip:  tracks the mouse; shows frequency, SWR, and impedance.
                    Only activates when the cursor is within _HOVER_THRESHOLD
                    (fraction of the visible axis range) of a data trace.
    Pinned tooltip: left-click near a trace to lock one in place; click the
                    same spot again to remove it.  Right-click resets zoom.
    """

    # Fraction of the visible axis range within which the cursor must be to
    # a data trace before the tooltip activates.
    _HOVER_THRESHOLD = 0.04

    def __init__(
        self,
        ax_swr: Axes,
        ax_imp: Axes,
        datasets: list[S1PDataset],
        theme: ThemeManager,
        view_lo: float,
        view_hi: float,
    ) -> None:
        self._ax_swr   = ax_swr
        self._ax_imp   = ax_imp
        self._datasets = datasets
        self._theme    = theme
        self._view_lo  = view_lo
        self._view_hi  = view_hi
        self._pinned: list = []
        self._hover_ann    = self._create_hover_ann()
        theme.register_hover_ann(self._hover_ann)

    def _create_hover_ann(self):
        T = self._theme.theme
        return self._ax_swr.annotate(
            "", xy=(0, 0), xytext=(14, 14), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.45", fc=T['hover_fc'],
                      ec=T['hover_ec'], alpha=0.93, lw=1),
            arrowprops=dict(arrowstyle="->", color=T['hover_arrow'], lw=0.9),
            fontsize=9, zorder=12, visible=False, color=T['hover_fg'],
        )

    def _nearest_trace(self, event) -> tuple[S1PDataset | None, int, float]:
        """Find the dataset and sample index closest to the cursor.

        Snaps to the nearest sample in X for each dataset, then measures the
        Y-distance normalised by the visible Y range.  Using Y-only distance
        keeps the threshold scale-independent at any zoom level — an X-based
        component would grow large when zoomed in because the data spacing
        becomes a significant fraction of the tiny visible X span.

        When hovering in the impedance plot the closer of R or X is used.

        Returns:
            ``(ds, idx, dist)`` — the nearest dataset, its sample index, and
            the normalised Y distance.  Returns ``(None, 0, inf)`` on failure.
        """
        in_swr = (event.inaxes is self._ax_swr)
        ylo, yhi = event.inaxes.get_ylim()
        yspan    = max(yhi - ylo, 1e-9)

        best_ds, best_idx, best_dist = None, 0, float('inf')
        for ds in self._datasets:
            idx = int(np.argmin(np.abs(ds.freqs - event.xdata)))
            if in_swr:
                fy = float(ds.swrs[idx])
            else:
                ry = float(ds.rs[idx])
                xy = float(ds.xs[idx])
                # Use whichever curve (R or X) is closer to the cursor in Y
                fy = ry if abs(ry - event.ydata) < abs(xy - event.ydata) else xy
            dy = abs(fy - event.ydata) / yspan
            if dy < best_dist:
                best_dist, best_ds, best_idx = dy, ds, idx
        return best_ds, best_idx, best_dist

    def _show_hover(self, ds: S1PDataset, idx: int) -> None:
        fx = float(ds.freqs[idx])
        sy = float(ds.swrs[idx])
        self._hover_ann.xy = (fx, sy)
        self._hover_ann.set_text(_format_tip(ds, idx))
        lo, hi = self._ax_swr.get_xlim()
        xfrac  = (fx - lo) / max(hi - lo, 1e-6)
        self._hover_ann.set_position((-120, 14) if xfrac > 0.82 else (14, 14))
        self._hover_ann.set_visible(True)
        self._ax_swr.figure.canvas.draw_idle()

    def _active_axes(self) -> tuple:
        """Return the axes that are currently visible and should receive events."""
        return tuple(ax for ax in (self._ax_swr, self._ax_imp) if ax.get_visible())

    def on_move(self, event) -> None:
        """Show or hide the hover tooltip as the mouse moves."""
        if event.inaxes not in self._active_axes():
            self._hover_ann.set_visible(False)
            self._ax_swr.figure.canvas.draw_idle()
            return
        ds, idx, dist = self._nearest_trace(event)
        if ds is None or dist > self._HOVER_THRESHOLD:
            self._hover_ann.set_visible(False)
            self._ax_swr.figure.canvas.draw_idle()
            return
        self._show_hover(ds, idx)

    def on_leave(self, event) -> None:
        """Hide the hover tooltip when the mouse leaves the axes."""
        self._hover_ann.set_visible(False)
        self._ax_swr.figure.canvas.draw_idle()

    def on_click(self, event) -> None:
        """Pin or unpin a tooltip (left click); reset zoom (right click)."""
        if event.inaxes not in self._active_axes():
            return
        T = self._theme.theme
        if event.button == 1:
            ds, idx, dist = self._nearest_trace(event)
            if ds is None or dist > self._HOVER_THRESHOLD:
                return
            fx = float(ds.freqs[idx])
            # Toggle off if clicking near an existing pin
            for pa in list(self._pinned):
                if abs(pa.xy[0] - fx) < 0.05:
                    pa.remove()
                    self._pinned.remove(pa)
                    self._ax_swr.figure.canvas.draw_idle()
                    return
            lo, hi = self._ax_swr.get_xlim()
            xfrac  = (fx - lo) / max(hi - lo, 1e-6)
            offset = (-130, 20) if xfrac > 0.82 else (14, 20)
            pa = self._ax_swr.annotate(
                _format_tip(ds, idx),
                xy=(fx, float(ds.swrs[idx])),
                xytext=offset, textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.45", fc=T['pin_fc'],
                          ec=T['pin_ec'], alpha=0.97, lw=1.2),
                arrowprops=dict(arrowstyle="->", color=T['pin_arrow'], lw=1),
                fontsize=8.5, zorder=13, color=T['pin_fg'],
            )
            self._pinned.append(pa)
            self._ax_swr.figure.canvas.draw_idle()
        elif event.button == 3:
            self._ax_swr.set_xlim(self._view_lo, self._view_hi)
            self._ax_swr.set_ylim(1.0, SWR_CAP + 1)
            self._ax_imp.set_ylim(-IMP_CAP, IMP_CAP)
            self._ax_swr.figure.canvas.draw_idle()

    def on_scroll(self, event) -> None:
        """Zoom the frequency axis in or out with the scroll wheel."""
        if event.inaxes not in self._active_axes():
            return
        factor = 0.80 if event.button == 'up' else 1.0 / 0.80
        lo, hi = self._ax_swr.get_xlim()
        xd     = event.xdata
        new_lo = xd - (xd - lo) * factor
        new_hi = xd + (hi - xd) * factor
        if new_hi - new_lo < MIN_XSPAN:
            return   # already at minimum zoom; ignore further scroll-in
        self._ax_swr.set_xlim(new_lo, new_hi)
        self._ax_swr.figure.canvas.draw_idle()

    def clear_pins(self) -> None:
        """Remove all pinned tooltips and hide the hover tooltip."""
        for pa in list(self._pinned):
            pa.remove()
        self._pinned.clear()
        self._hover_ann.set_visible(False)
        self._ax_swr.figure.canvas.draw_idle()


# ── BandButtonRow ─────────────────────────────────────────────────────────────

class BandButtonRow:
    """Creates and manages the row of per-band zoom buttons along the top.

    Buttons are laid out dynamically based on which bands appear in the loaded
    datasets.  Clicking a button zooms both axes to that band and auto-scales
    the Y axes to fit the visible data.

    Call ``build()`` once after the figure and axes exist.
    """

    def __init__(
        self,
        fig: Figure,
        ax_swr: Axes,
        ax_imp: Axes,
        datasets: list[S1PDataset],
        active_bands: list,
        theme: ThemeManager,
        view_lo: float,
        view_hi: float,
    ) -> None:
        self._fig         = fig
        self._ax_swr      = ax_swr
        self._ax_imp      = ax_imp
        self._datasets    = datasets
        self._active_bands = active_bands
        self._theme       = theme
        self._view_lo     = view_lo
        self._view_hi     = view_hi
        self._btn_refs: list = []   # keep Button objects alive (prevents GC)
        self._btn_data: list = []   # styling dicts handed to ThemeManager

    def build(self) -> None:
        """Create all button axes, Button widgets, and 3D patch styling."""
        T = self._theme.theme

        btn_labels = ["All"] + [b[0] for b in self._active_bands]
        btn_ranges = (
            [(self._view_lo, self._view_hi)]
            + [
                (
                    max(b[1] - min((b[2] - b[1]) * 2, 0.5), self._view_lo),
                    min(b[2] + min((b[2] - b[1]) * 2, 0.5), self._view_hi),
                )
                for b in self._active_bands
            ]
        )

        n     = len(btn_labels)
        bh    = 0.030
        by    = 0.955
        gap   = 0.004
        bw    = (0.94 - (n - 1) * gap) / n
        bw    = max(0.035, min(bw, 0.091))
        total = n * bw + (n - 1) * gap
        bx0   = (1.0 - total) / 2.0

        for j, (lbl, (rlo, rhi)) in enumerate(zip(btn_labels, btn_ranges)):
            ax_b = self._fig.add_axes([bx0 + j * (bw + gap), by, bw, bh])
            b    = Button(ax_b, lbl, color=T['btn_base'],
                          hovercolor=T['btn_hover'])
            b.label.set_fontsize(9)
            b.label.set_color(T['btn_fg'])
            sh, hl, fc = self._make_btn_patches(ax_b)
            self._btn_data.append(
                {'btn': b, 'shadow': sh, 'highlight': hl,
                 'face': fc, 'is_mswr': False}
            )
            b.on_clicked(self._zoom_callback(rlo, rhi))
            self._btn_refs.append(b)

        self._theme.register_band_buttons(self._btn_data)

    def _make_btn_patches(self, ax_b: Axes) -> tuple:
        """Add shadow/highlight/face FancyBboxPatches; return their refs.

        Three overlapping rounded rectangles give the button a raised 3-D
        appearance.  The face patch replaces ``ax_b.patch`` so that
        matplotlib's Button hover mechanism (which calls
        ``ax.set_facecolor()``) continues to work correctly.
        """
        T = self._theme.theme
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

    def _fit_ylims(self, xlo: float, xhi: float) -> None:
        """Auto-scale both Y axes to the data visible in [xlo, xhi]."""
        swr_vals, r_vals, x_vals = [], [], []
        for ds in self._datasets:
            mask = (ds.freqs >= xlo) & (ds.freqs <= xhi)
            if mask.any():
                swr_vals.extend(ds.swrs[mask].tolist())
                r_vals.extend(ds.rs[mask].tolist())
                x_vals.extend(ds.xs[mask].tolist())
        if swr_vals:
            self._ax_swr.set_ylim(1.0, max(max(swr_vals) * 1.12, 3.0))
        if r_vals or x_vals:
            imin = min(r_vals + x_vals)
            imax = max(r_vals + x_vals)
            pad  = max((imax - imin) * 0.10, 50.0)
            self._ax_imp.set_ylim(max(imin - pad, -IMP_CAP),
                                  min(imax + pad,  IMP_CAP))

    def _zoom_callback(self, lo: float, hi: float):
        """Return a callback that zooms both axes to [lo, hi]."""
        def cb(event):
            self._ax_swr.set_xlim(lo, hi)
            self._fit_ylims(lo, hi)
            self._fig.canvas.draw_idle()
        return cb


# ── MinSWRPopup ───────────────────────────────────────────────────────────────

class MinSWRPopup:
    """Displays a Tkinter popup table comparing the minimum SWR per band.

    Calling ``show()`` a second time closes the previous window and opens a
    fresh one so the table always reflects the current theme.
    """

    def __init__(
        self,
        datasets: list[S1PDataset],
        active_bands: list,
        theme: ThemeManager,
    ) -> None:
        self._datasets     = datasets
        self._active_bands = active_bands
        self._theme        = theme
        self._win          = None

    def show(self) -> None:
        """Open (or reopen) the Min SWR comparison popup."""
        import tkinter as tk
        from tkinter import font as tkfont

        try:
            if self._win and self._win.winfo_exists():
                self._win.destroy()
        except Exception:
            pass

        T       = self._theme.theme
        is_dark = (self._theme.current == 'dark')
        labels  = [ds.label for ds in self._datasets]

        per_band: dict = {b[0]: {} for b in self._active_bands}
        for ds in self._datasets:
            for bname, freq, swr in find_band_minima(ds.freqs, ds.swrs):
                if bname in per_band:
                    per_band[bname][ds.label] = (freq, swr)

        n_cols  = len(labels)
        top     = tk.Toplevel()
        self._win = top
        top.title("Minimum SWR by band")
        top.resizable(False, False)

        bg_win  = '#2d2d2d' if is_dark else '#f5f5f5'
        bg_hdr  = '#2a3f6f' if is_dark else '#b0bcee'
        fg_hdr  = '#c8d8f8' if is_dark else '#222222'
        bg_band = '#3a3a3a' if is_dark else '#e0e0e0'
        bg_cell = '#2d2d2d' if is_dark else 'white'
        bg_best = '#1a3a1a' if is_dark else '#b8f0b8'
        bg_none = '#252525' if is_dark else '#eeeeee'
        fg_none = '#555555' if is_dark else '#888888'
        fg_star = '#5ba3f5' if is_dark else '#0055cc'

        top.configure(bg=bg_win)
        PAD       = 6
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

        for i, (bname, *_) in enumerate(self._active_bands):
            tk.Label(top, text=bname, font=hdr_font, bg=bg_band, fg=T['fg'],
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
                    bg  = bg_best if is_best else bg_cell
                    frm = _cf(top, bg)
                    frm.grid(row=i + 1, column=j + 1, sticky='nsew')
                    line1 = tk.Frame(frm, bg=bg)
                    line1.pack(anchor='w', padx=PAD, pady=(PAD, 0))
                    tk.Label(line1, text=swr_str, font=cell_font,
                             bg=bg, fg=T['fg']).pack(side='left')
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
                     font=tkfont.Font(size=9), fg=fg_star, bg=bg_win,
                     pady=4).grid(row=len(self._active_bands) + 1, column=0,
                                  columnspan=n_cols + 1)

        for col in range(n_cols + 1):
            top.columnconfigure(col, weight=1)

        top.update_idletasks()
        # Ensure the window is wide enough to show the full title bar text.
        # "Minimum SWR by band" needs ~300 px including OS window controls.
        min_w = max(top.winfo_reqwidth(), 300)
        top.geometry(f"{min_w}x{top.winfo_reqheight()}")
        top.lift()
        top.focus_force()


# ── SmithChartPopup ───────────────────────────────────────────────────────────

class SmithChartPopup:
    """Smith Chart for a specific frequency range.

    Each call to ``show()`` opens an independent window.  Multiple windows
    can be active simultaneously, each capturing the zoom level at the moment
    the button was clicked.
    """

    # Normalised resistance values to draw as grid circles
    _R_CIRCLES = [0.2, 0.5, 1.0, 2.0, 5.0]
    # Normalised reactance magnitudes to draw as grid arcs (±)
    _X_ARCS    = [0.2, 0.5, 1.0, 2.0, 5.0]
    _N_PTS     = 1000   # parametric points per circle / arc

    def __init__(
        self,
        datasets: list[S1PDataset],
        theme: ThemeManager,
        freq_lo: float,
        freq_hi: float,
    ) -> None:
        self._datasets = datasets
        self._theme    = theme
        self._freq_lo  = freq_lo
        self._freq_hi  = freq_hi

    def show(self) -> None:
        """Open a new Smith Chart window."""
        import tkinter as tk
        from matplotlib.backends.backend_tkagg import (
            FigureCanvasTkAgg, NavigationToolbar2Tk,
        )

        T  = self._theme.theme
        lo = self._freq_lo
        hi = self._freq_hi

        top = tk.Toplevel()
        top.title(f"Smith Chart \u2014 {lo:.4f}\u2013{hi:.4f} MHz")
        top.configure(bg=T['bg_fig'])

        # Use Figure directly (not plt.figure) so it is independent of the
        # main pyplot state and does not interfere with the main window.
        fig = Figure(figsize=(7, 7.5), facecolor=T['bg_fig'])
        ax  = fig.add_axes([0.04, 0.06, 0.92, 0.90], aspect='equal')
        ax.set_facecolor(T['bg_axes'])
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_xlim(-1.15, 1.15)
        ax.set_ylim(-1.15, 1.15)

        self._draw_grid(ax, T)
        traces = self._plot_traces(ax, T)

        # Frequency-range legend below the chart
        fig.text(
            0.5, 0.015,
            f"\u25cf  {lo:.4f} MHz     \u25a0  {hi:.4f} MHz",
            ha='center', fontsize=9, fontweight='bold', color=T['fg_muted'],
        )

        canvas = FigureCanvasTkAgg(fig, master=top)
        canvas.draw()

        # Default save filename: file basenames + frequency range
        _save_stem = (
            "_".join(os.path.splitext(ds.label)[0] for ds in self._datasets)
            + f"_smith_{lo:.4f}-{hi:.4f}MHz".replace('.', '_')
        )
        _cv = canvas
        canvas.get_default_filename = (
            lambda: _save_stem + '.' + _cv.get_default_filetype()
        )

        toolbar = NavigationToolbar2Tk(canvas, top, pack_toolbar=False)
        toolbar.update()
        # Raw Γ-coordinate readout is meaningless to users; the hover tooltip
        # provides the useful information instead.
        toolbar.set_message = lambda msg: None
        for name in ('Back', 'Forward'):
            if hasattr(toolbar, '_buttons') and name in toolbar._buttons:
                toolbar._buttons[name].pack_forget()
        toolbar.configure(bg=T['btn_base'])
        toolbar.pack(side='bottom', fill='x')

        canvas.get_tk_widget().pack(fill='both', expand=True)
        self._setup_hover(ax, canvas, T, traces)

        top.lift()
        top.focus_force()

    # ── Grid drawing ──────────────────────────────────────────────────────────

    @staticmethod
    def _arc_pts(
        cx: float, cy: float, r: float, n: int = 1000
    ) -> tuple[np.ndarray, np.ndarray]:
        """Parametric circle clipped to the unit disk; outside points → NaN."""
        theta   = np.linspace(0, 2 * np.pi, n)
        px      = cx + r * np.cos(theta)
        py      = cy + r * np.sin(theta)
        outside = px ** 2 + py ** 2 > 1.0 + 1e-6
        px[outside] = np.nan
        py[outside] = np.nan
        return px, py

    def _draw_grid(self, ax, T) -> None:
        """Draw constant-R circles, constant-X arcs, real axis, and labels."""
        gc = T['grid_mj']
        lc = T['band_label']
        n  = self._N_PTS
        t  = np.linspace(0, 2 * np.pi, n)

        # Outer boundary (R = 0, unit circle)
        ax.plot(np.cos(t), np.sin(t), color=T['fg'], lw=1.2, zorder=3)

        # Real axis (X = 0 reference line)
        ax.plot([-1.0, 1.0], [0.0, 0.0],
                color=gc, lw=0.7, alpha=0.8, zorder=2)

        # Constant-R circles
        for rv in self._R_CIRCLES:
            cx = rv / (rv + 1)
            r  = 1.0 / (rv + 1)
            px, py = self._arc_pts(cx, 0.0, r, n)
            ax.plot(px, py, color=gc, lw=0.6, alpha=0.75, zorder=2)
            # Label at the left intersection with the real axis
            lx    = cx - r   # = (rv − 1) / (rv + 1)
            label = str(int(rv)) if rv == int(rv) else str(rv)
            ax.text(lx, 0.045, label, fontsize=8, fontweight='bold', color=lc,
                    ha='center', va='bottom', zorder=4)

        # Constant-X arcs (both positive and negative).
        # Label position uses the analytical second intersection of each arc
        # with the unit circle:  xi = (X²−1)/(X²+1),  yi = 2X/(X²+1).
        # This spreads labels evenly around the rim instead of piling them up
        # near Γ = 1 where all arcs also converge.
        for xv in self._X_ARCS:
            for sign in (+1, -1):
                x  = sign * xv
                r  = 1.0 / xv          # radius = 1 / |x|
                cy = 1.0 / x           # centre y
                px, py = self._arc_pts(1.0, cy, r, n)
                ax.plot(px, py, color=gc, lw=0.6, alpha=0.75, zorder=2)

                # Analytical rim intersection (not Γ=1), pushed 10% outside.
                xi = (xv ** 2 - 1) / (xv ** 2 + 1)
                yi = sign * 2 * xv    / (xv ** 2 + 1)
                lx = xi * 1.10
                ly = yi * 1.10
                iv   = int(xv) if xv == int(xv) else xv
                text = f"j{iv}" if sign > 0 else f"\u2212j{iv}"
                ax.text(lx, ly, text, fontsize=8, fontweight='bold', color=lc,
                        ha='center', va='center', zorder=4)

        # Short-circuit (Γ = −1) and open-circuit (Γ = +1) labels
        ax.text(-1.0, 0.06, "0",  fontsize=8, fontweight='bold', color=lc,
                ha='center', va='bottom', zorder=4)
        ax.text( 1.0, 0.06, "∞",  fontsize=8, fontweight='bold', color=lc,
                ha='center', va='bottom', zorder=4)
        ax.plot(0.0, 0.0, 'o', color=gc, ms=3, zorder=4)  # centre dot

    # ── Data traces ───────────────────────────────────────────────────────────

    def _plot_traces(self, ax, T) -> list[dict]:
        """Convert R+jX → Γ, plot one curve per dataset, return trace records.

        Each record in the returned list contains the Γ coordinates and the
        corresponding frequency/SWR/impedance arrays needed for hover hit-testing.
        """
        Z0 = 50.0
        traces = []
        for i, ds in enumerate(self._datasets):
            color = COLORS[i % len(COLORS)]
            mask  = (ds.freqs >= self._freq_lo) & (ds.freqs <= self._freq_hi)
            if not mask.any():
                continue

            z     = (ds.rs[mask] + 1j * ds.xs[mask]) / Z0
            # Guard against z = −1 (open singularity; unphysical but possible
            # when impedance data is clipped or corrupted).
            denom = z + 1.0
            safe  = np.abs(denom) > 1e-9
            gamma = np.where(safe, (z - 1.0) / np.where(safe, denom, 1.0),
                             np.nan + 0j)
            gx    = gamma.real.astype(float)
            gy    = gamma.imag.astype(float)

            ax.plot(gx, gy, color=color, lw=1.8, zorder=5, label=ds.label)
            # Circle at start (lowest frequency in range)
            ax.plot(gx[0], gy[0], 'o', color=color, ms=6, zorder=6,
                    markeredgecolor=T['marker_edge'], markeredgewidth=0.8)
            # Square at end (highest frequency in range)
            ax.plot(gx[-1], gy[-1], 's', color=color, ms=6, zorder=6,
                    markeredgecolor=T['marker_edge'], markeredgewidth=0.8)

            traces.append(dict(
                gx=gx, gy=gy,
                freqs=ds.freqs[mask], swrs=ds.swrs[mask],
                rs=ds.rs[mask],       xs=ds.xs[mask],
                color=color,
            ))

        handles, labels = ax.get_legend_handles_labels()
        if handles:
            leg = ax.legend(handles, labels, loc='lower right', fontsize=9,
                            prop={'weight': 'bold'})
            leg.get_frame().set_facecolor(T['leg_face'])
            leg.get_frame().set_edgecolor(T['leg_edge'])
            for txt in leg.get_texts():
                txt.set_color(T['fg'])

        return traces

    # ── Hover tooltip ──────────────────────────────────────────────────────────

    @staticmethod
    def _setup_hover(ax, canvas, T: dict, traces: list[dict]) -> None:
        """Wire up a hover tooltip on the Smith Chart axes.

        Finds the nearest Γ point across all traces (Euclidean distance in
        Γ-space) and shows frequency, SWR, and impedance.  The annotation
        border takes the colour of the nearest trace so the user can tell
        which dataset is being reported.
        """
        _THRESHOLD = 0.05   # Γ-space snap radius (chart spans ±1.15)

        ann = ax.annotate(
            "", xy=(0, 0), xytext=(14, 14), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.45", fc=T['hover_fc'],
                      ec=T['hover_ec'], alpha=0.93, lw=1.2),
            arrowprops=dict(arrowstyle="->", color=T['hover_arrow'], lw=0.9),
            fontsize=9, zorder=12, visible=False, color=T['hover_fg'],
        )

        def _on_move(event) -> None:
            if event.inaxes is not ax or event.xdata is None:
                if ann.get_visible():
                    ann.set_visible(False)
                    canvas.draw_idle()
                return

            mx, my = event.xdata, event.ydata
            best_dist, best_tr, best_idx = float('inf'), None, 0

            for tr in traces:
                dx   = tr['gx'] - mx
                dy   = tr['gy'] - my
                dist = np.hypot(dx, dy)
                if not np.isfinite(dist).any():
                    continue
                idx = int(np.nanargmin(dist))
                if dist[idx] < best_dist:
                    best_dist = dist[idx]
                    best_tr   = tr
                    best_idx  = idx

            if best_tr is None or best_dist > _THRESHOLD:
                if ann.get_visible():
                    ann.set_visible(False)
                    canvas.draw_idle()
                return

            fx    = float(best_tr['freqs'][best_idx])
            sy    = float(best_tr['swrs'][best_idx])
            rv    = float(best_tr['rs'][best_idx])
            xv    = float(best_tr['xs'][best_idx])
            swr_s = f">{SWR_CAP}" if sy >= SWR_CAP else f"{sy:.2f}"
            sign  = '+' if xv >= 0 else ''
            clip  = "  (clipped)" if abs(rv) >= IMP_CAP or abs(xv) >= IMP_CAP else ""
            text  = (f"{fx:.4f} MHz{band_of(fx)}\n"
                     f"SWR {swr_s}\n"
                     f"Z = {rv:.1f}{sign}{xv:.1f}j \u03a9{clip}")

            gxi = float(best_tr['gx'][best_idx])
            gyi = float(best_tr['gy'][best_idx])
            # Flip to the left when near the right half of the chart
            offset = (-130, 14) if gxi > 0.3 else (14, 14)
            ann.xy = (gxi, gyi)
            ann.set_text(text)
            ann.set_position(offset)
            ann.get_bbox_patch().set_edgecolor(best_tr['color'])
            ann.set_visible(True)
            canvas.draw_idle()

        def _on_leave(event) -> None:
            if ann.get_visible():
                ann.set_visible(False)
                canvas.draw_idle()

        canvas.mpl_connect('motion_notify_event', _on_move)
        canvas.mpl_connect('axes_leave_event',    _on_leave)


# ── SWRApp ────────────────────────────────────────────────────────────────────

class SWRApp:
    """Main application controller.

    Constructs all subsystems, wires them together, and starts the Tk event
    loop.  All mutable state is owned by the appropriate subsystem; ``SWRApp``
    itself is the coordinator.

    Usage::

        datasets = [parse_s1p(p) for p in paths]
        SWRApp(datasets).run()
    """

    # ── Adaptive tick-spacing look-up tables (class constants) ────────────────

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
    _SWR_YTICKS = [
        (30.0, 10.0, 2.0), (15.0, 5.0,  1.0), ( 8.0, 2.0,  0.5),
        ( 4.0,  1.0, 0.25),( 2.0, 0.5,  0.1), ( 1.0, 0.25, 0.05),
        ( 0.0,  0.1, 0.02),
    ]
    _IMP_YTICKS = [
        (1500.0, 500.0, 100.0), ( 800.0, 250.0, 50.0), ( 400.0, 100.0, 25.0),
        ( 200.0,  50.0,  10.0), ( 100.0,  25.0,  5.0), (  50.0,  10.0,  2.0),
        (  20.0,   5.0,   1.0), (   0.0,   2.0,  0.5),
    ]

    def __init__(self, datasets: list[S1PDataset]) -> None:
        self._datasets = datasets
        self._theme    = ThemeManager('light')

        self._fdata_lo = max(min(ds.freqs[0]  for ds in datasets), 0.1)
        self._fdata_hi =     max(ds.freqs[-1] for ds in datasets)

        self._active_bands = [
            (n, lo, hi) for n, lo, hi in BANDS
            if any(
                np.any((ds.freqs >= lo) & (ds.freqs <= hi))
                for ds in datasets
            )
        ]

        self._fig: Figure           = None
        self._ax_swr: Axes          = None
        self._ax_imp: Axes          = None
        self._annotations: AnnotationManager = None
        self._band_row: BandButtonRow        = None
        self._popup: MinSWRPopup             = None
        self._clamping_xlim: bool            = False  # recursion guard for xlim clamp
        self._imp_visible: bool              = True
        self._tk_imp_btn                     = None
        self._tk_imp_tip: Tooltip | None     = None

        self._create_figure()
        self._plot_data()
        self._setup_axes()
        self._build_band_buttons()
        self._setup_annotations()
        self._patch_toolbar()
        self._theme.apply('light')

    def run(self) -> None:
        """Enter the matplotlib/Tk event loop."""
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        plt.show()

    # ── Private setup steps ───────────────────────────────────────────────────

    def _create_figure(self) -> None:
        """Create the matplotlib figure and the two shared-axis axes."""
        matplotlib.rcParams['savefig.directory'] = os.getcwd()
        win_title  = "SWR Chart: " + "  ".join(ds.label for ds in self._datasets)
        self._fig  = plt.figure(win_title, figsize=(15, 9))
        self._fig.patch.set_facecolor(self._theme.theme['bg_fig'])
        # Override the save-dialog default filename to use clean basenames (no extension).
        # canvas.get_default_filename() uses the window title in modern matplotlib, so we
        # replace it on the instance to return the desired name instead.
        _save_stem = "_".join(os.path.splitext(ds.label)[0] for ds in self._datasets)
        _canvas    = self._fig.canvas
        self._fig.canvas.get_default_filename = (
            lambda: _save_stem + '.' + _canvas.get_default_filetype()
        )

        self._try_set_icon()

        self._ax_swr = self._fig.add_axes([0.07, 0.50, 0.91, 0.40])
        self._ax_imp = self._fig.add_axes(
            [0.07, 0.08, 0.91, 0.37], sharex=self._ax_swr
        )
        self._theme.register_axes(self._fig, self._ax_swr, self._ax_imp)

    def _try_set_icon(self) -> None:
        """Attempt to set the window icon; silently ignore any failure."""
        try:
            from PIL import ImageTk, Image as PILImage
            from Xlib import display as Xdisplay
            icon_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'resources', 'icon.png',
            )
            win = self._fig.canvas.manager.window
            xid = win.winfo_id()
            d   = Xdisplay.Display()
            xw  = d.create_resource_object('window', xid)
            xw.set_wm_class('swr_chart', 'swr_chart')
            d.flush()
            d.close()
            def _apply():
                try:
                    img = ImageTk.PhotoImage(PILImage.open(icon_path))
                    win.iconphoto(True, img)
                    win._icon_img = img   # prevent garbage collection
                except Exception:
                    pass
            win.after(200, _apply)
        except Exception:
            pass

    def _plot_data(self) -> None:
        """Draw band shading, reference lines, data curves, and minima markers."""
        T0 = self._theme.theme

        # Band shading
        band_patches = []
        for i, (_, flo, fhi) in enumerate(BANDS):
            c      = _BAND_COLORS['light'][i]
            sp_swr = self._ax_swr.axvspan(flo, fhi, alpha=T0['band_alpha'],
                                          color=c, zorder=1)
            sp_imp = self._ax_imp.axvspan(flo, fhi, alpha=T0['band_alpha'],
                                          color=c, zorder=1)
            band_patches.append((sp_swr, sp_imp))
        self._theme.register_band_patches(band_patches)

        # Reference lines
        ref_specs = [
            (3.0, 'green',     '--', 'SWR 3:1'),
            (2.0, 'orange',    ':',  'SWR 2:1'),
            (1.5, 'royalblue', '--', 'SWR 1.5:1'),
        ]
        ref_lines = []
        for swr_val, col, ls, lbl in ref_specs:
            ln = self._ax_swr.axhline(swr_val, color=col, ls=ls, lw=1,
                                      alpha=0.75, zorder=2, label=lbl)
            ref_lines.append(ln)
        self._theme.register_ref_lines(ref_lines)

        zero_line = self._ax_imp.axhline(0, color='black', lw=0.6,
                                         alpha=0.4, zorder=2)
        self._theme.register_zero_line(zero_line)

        # Data curves and band-minima markers
        dot_artists = []
        for i, ds in enumerate(self._datasets):
            color = COLORS[i % len(COLORS)]
            self._ax_swr.plot(ds.freqs, ds.swrs, color=color, lw=2.0,
                              zorder=3, label=ds.label)
            for _, fx, sy in find_band_minima(ds.freqs, ds.swrs):
                dot, = self._ax_swr.plot(
                    fx, sy, 'o', color=color, ms=5, zorder=5,
                    markeredgecolor='white', markeredgewidth=0.5,
                )
                dot_artists.append(dot)
                self._ax_swr.text(
                    fx, sy - 1.0, f"{sy:.1f}",
                    ha='center', va='top', fontsize=7,
                    color=color, zorder=5, fontweight='bold',
                )
            self._ax_imp.plot(ds.freqs, ds.rs, color=color, lw=2.0,
                              zorder=3, label=f"{ds.label} — R")
            self._ax_imp.plot(ds.freqs, ds.xs, color=color, lw=2.0,
                              ls='--', alpha=0.75, zorder=3,
                              label=f"{ds.label} — X")
        self._theme.register_dot_artists(dot_artists)

    def _setup_axes(self) -> None:
        """Set axis limits, labels, grids, tick locators, and band labels."""
        T0 = self._theme.theme

        self._ax_swr.set_xlim(self._fdata_lo, self._fdata_hi)
        self._ax_swr.set_ylim(1.0, SWR_CAP + 1)
        self._ax_imp.set_ylim(-IMP_CAP, IMP_CAP)

        for ax in (self._ax_swr, self._ax_imp):
            ax.set_facecolor(T0['bg_axes'])
            for sp in ax.spines.values():
                sp.set_edgecolor(T0['spine'])
            ax.tick_params(colors=T0['fg'], which='both')
            ax.yaxis.label.set_color(T0['fg'])
            ax.xaxis.label.set_color(T0['fg'])
            ax.xaxis.set_major_locator(ticker.MultipleLocator(1.0))
            ax.xaxis.set_minor_locator(ticker.MultipleLocator(0.5))
            ax.tick_params(axis='x', which='minor', length=4)
            ax.grid(True, which='major', color=T0['grid_mj'],
                    alpha=T0['grid_mj_a'], zorder=0)
            ax.grid(True, which='minor', color=T0['grid_mn'],
                    alpha=T0['grid_mn_a'], ls=':', zorder=0)

        self._ax_swr.yaxis.set_major_locator(ticker.MultipleLocator(5))
        self._ax_swr.yaxis.set_minor_locator(ticker.MultipleLocator(1))
        self._ax_imp.yaxis.set_major_locator(ticker.MultipleLocator(500))
        self._ax_imp.yaxis.set_minor_locator(ticker.MultipleLocator(100))

        self._ax_swr.tick_params(axis='x', labelsize=8, rotation=45)
        self._ax_imp.tick_params(axis='x', labelsize=8, rotation=45)
        self._ax_swr.tick_params(axis='y', labelsize=8)
        self._ax_imp.tick_params(axis='y', labelsize=8)

        self._ax_swr.set_ylabel('SWR (50 Ω)', fontsize=10)
        self._ax_imp.set_ylabel(f'Impedance (Ω, clipped ±{IMP_CAP})', fontsize=10)
        self._ax_imp.set_xlabel('Frequency (MHz)', fontsize=10)

        # Always show full frequency values (e.g. 14.008, not .008 + offset).
        _xfmt = ticker.ScalarFormatter(useOffset=False)
        _xfmt.set_scientific(False)
        for ax in (self._ax_swr, self._ax_imp):
            ax.xaxis.set_major_formatter(_xfmt)

        # Adaptive tick callbacks
        self._ax_swr.callbacks.connect('xlim_changed', self._update_xticks)
        self._ax_swr.callbacks.connect('ylim_changed', self._update_swr_yticks)
        self._ax_imp.callbacks.connect('ylim_changed', self._update_imp_yticks)

        # Band labels
        view_lo, view_hi = self._fdata_lo, self._fdata_hi
        band_labels = []
        for name, flo, fhi in BANDS:
            if fhi < view_lo or flo > view_hi:
                continue
            mid  = (flo + fhi) / 2
            frac = (mid - view_lo) / max(view_hi - view_lo, 1e-6)
            lx   = max(flo, view_lo) if frac < 0.04 else mid
            ha   = 'left'            if frac < 0.04 else 'center'
            txt  = self._ax_swr.text(
                lx, SWR_CAP * 0.94, name,
                ha=ha, va='top', fontsize=8,
                fontweight='bold', color=T0['band_label'], zorder=4,
            )
            band_labels.append(txt)
        self._theme.register_band_labels(band_labels)

        # Title
        title = self._fig.text(
            0.5, 0.924,
            "  vs  ".join(ds.label for ds in self._datasets),
            ha='center', va='bottom', fontsize=11, fontweight='bold',
            color=T0['title_color'],
        )
        self._theme.register_title(title)

        # Legends
        swr_handles, swr_labels = self._ax_swr.get_legend_handles_labels()
        leg_swr = self._ax_swr.legend(swr_handles, swr_labels,
                                      loc='upper right', fontsize=8)
        leg_swr.get_frame().set_facecolor(T0['leg_face'])
        leg_swr.get_frame().set_edgecolor(T0['leg_edge'])
        for txt in leg_swr.get_texts():
            txt.set_color(T0['fg'])

        imp_handles = [
            Line2D([0], [0], color='gray', lw=2, ls='-',
                   label='R (resistance)'),
            Line2D([0], [0], color='gray', lw=2, ls='--',
                   label='X (reactance)'),
        ] + [
            Line2D([0], [0], color=COLORS[i % len(COLORS)], lw=2,
                   label=ds.label)
            for i, ds in enumerate(self._datasets)
        ]
        leg_imp = self._ax_imp.legend(handles=imp_handles,
                                      loc='upper right', fontsize=8)
        leg_imp.get_frame().set_facecolor(T0['leg_face'])
        leg_imp.get_frame().set_edgecolor(T0['leg_edge'])
        for txt in leg_imp.get_texts():
            txt.set_color(T0['fg'])

        self._theme.register_legends([leg_swr, leg_imp])

    def _build_band_buttons(self) -> None:
        """Instantiate BandButtonRow and MinSWRPopup."""
        self._band_row = BandButtonRow(
            self._fig, self._ax_swr, self._ax_imp,
            self._datasets, self._active_bands, self._theme,
            self._fdata_lo, self._fdata_hi,
        )
        self._band_row.build()
        self._popup = MinSWRPopup(
            self._datasets, self._active_bands, self._theme
        )

    def _setup_annotations(self) -> None:
        """Create the AnnotationManager and connect canvas events."""
        self._annotations = AnnotationManager(
            self._ax_swr, self._ax_imp, self._datasets, self._theme,
            self._fdata_lo, self._fdata_hi,
        )
        c = self._fig.canvas.mpl_connect
        c('motion_notify_event', self._annotations.on_move)
        c('axes_leave_event',    self._annotations.on_leave)
        c('button_press_event',  self._annotations.on_click)
        c('scroll_event',        self._annotations.on_scroll)

    def _patch_toolbar(self) -> None:
        """Remove Back/Forward buttons; add Dark/Light and Min SWR buttons."""
        import tkinter as tk
        toolbar = self._fig.canvas.toolbar
        T0      = self._theme.theme

        if hasattr(toolbar, '_buttons') and 'Home' in toolbar._buttons:
            def _home_and_clear():
                toolbar.home()
                self._annotations.clear_pins()
            toolbar._buttons['Home'].configure(command=_home_and_clear)

        for name in ('Back', 'Forward'):
            if hasattr(toolbar, '_buttons') and name in toolbar._buttons:
                toolbar._buttons[name].pack_forget()

        sep0 = tk.Frame(toolbar, width=2, bd=1, relief='sunken')
        sep0.pack(side='left', fill='y', padx=6, pady=3)

        # Theme toggle: icon button placed directly after the Save button.
        # ThemeManager.apply() will set the correct image on the first theme pass.
        _bulb_init = _make_bulb_photo(False, T0['btn_fg'], T0['btn_base'])
        tk_toggle = tk.Button(
            toolbar,
            image=_bulb_init,
            command=self._theme.toggle,
            relief='raised', bd=2,
            bg=T0['btn_base'],
            activebackground=T0['btn_hover'],
            padx=4, pady=4,
        )
        tk_toggle._bulb_img = _bulb_init   # prevent garbage collection
        tk_toggle.pack(side='left', padx=2, pady=3)
        Tooltip(tk_toggle, 'Toggle dark / light theme')

        sep1 = tk.Frame(toolbar, width=2, bd=1, relief='sunken')
        sep1.pack(side='left', fill='y', padx=6, pady=3)

        tk_imp_btn = tk.Button(
            toolbar, text='Impedance \u25bc',
            command=self._toggle_impedance,
            relief='raised', bd=2,
            bg=T0['btn_base'], fg=T0['btn_fg'],
            activebackground=T0['btn_hover'], activeforeground=T0['btn_fg'],
            font=('TkDefaultFont', 9, 'bold'), padx=10, pady=1,
        )
        tk_imp_btn.pack(side='left', padx=2, pady=3)
        self._tk_imp_btn = tk_imp_btn
        self._tk_imp_tip = Tooltip(tk_imp_btn, 'Hide the impedance panel (SWR plot expands)')

        sep2 = tk.Frame(toolbar, width=2, bd=1, relief='sunken')
        sep2.pack(side='left', fill='y', padx=6, pady=3)

        tk_mswr = tk.Button(
            toolbar, text='Minimum SWR by band',
            command=self._popup.show,
            relief='raised', bd=2,
            bg=T0['btn_base'], fg=T0['btn_fg'],
            activebackground=T0['btn_hover'], activeforeground=T0['btn_fg'],
            font=('TkDefaultFont', 9, 'bold'), padx=10, pady=1,
        )
        tk_mswr.pack(side='left', padx=2, pady=3)
        Tooltip(tk_mswr, 'Compare best SWR in each band across all loaded files')

        sep3 = tk.Frame(toolbar, width=2, bd=1, relief='sunken')
        sep3.pack(side='left', fill='y', padx=6, pady=3)

        tk_smith = tk.Button(
            toolbar, text='Smith Chart',
            command=self._open_smith_chart,
            relief='raised', bd=2,
            bg=T0['btn_base'], fg=T0['btn_fg'],
            activebackground=T0['btn_hover'], activeforeground=T0['btn_fg'],
            font=('TkDefaultFont', 9, 'bold'), padx=10, pady=1,
        )
        tk_smith.pack(side='left', padx=2, pady=3)
        Tooltip(tk_smith, 'Open a Smith Chart for the current frequency range')

        self._theme.register_tk_buttons(tk_toggle, tk_imp_btn, tk_mswr, tk_smith)

    def _open_smith_chart(self) -> None:
        """Open a new Smith Chart popup for the current visible frequency range."""
        lo, hi = self._ax_swr.get_xlim()
        SmithChartPopup(self._datasets, self._theme, lo, hi).show()

    def _toggle_impedance(self) -> None:
        """Show or hide the impedance panel, expanding the SWR plot to fill."""
        self._imp_visible = not self._imp_visible
        if self._imp_visible:
            self._ax_swr.set_position([0.07, 0.50, 0.91, 0.40])
            self._ax_imp.set_visible(True)
            self._ax_swr.set_xlabel('')
            self._ax_imp.set_xlabel('Frequency (MHz)', fontsize=10)
            self._tk_imp_btn.configure(text='Impedance \u25bc')
            self._tk_imp_tip.update_text('Hide the impedance panel (SWR plot expands)')
        else:
            self._ax_swr.set_position([0.07, 0.08, 0.91, 0.82])
            self._ax_imp.set_visible(False)
            self._ax_imp.set_xlabel('')
            self._ax_swr.set_xlabel('Frequency (MHz)', fontsize=10)
            self._tk_imp_btn.configure(text='Impedance \u25b2')
            self._tk_imp_tip.update_text('Show the impedance panel')
        self._fig.canvas.draw_idle()

    # ── Adaptive tick callbacks ────────────────────────────────────────────────

    @staticmethod
    def _pick_step(span: float, table: list) -> tuple[float, float]:
        """Select major/minor tick spacing from *table* for the given *span*."""
        maj, mn = table[-1][1], table[-1][2]
        for max_span, m, n in table:
            if span > max_span:
                maj, mn = m, n
                break
        return maj, mn

    def _update_xticks(self, *_) -> None:
        if self._clamping_xlim:
            return
        lo, hi = self._ax_swr.get_xlim()
        if hi - lo < MIN_XSPAN:
            # Toolbar zoom went past the minimum; clamp and re-centre.
            self._clamping_xlim = True
            mid = (lo + hi) / 2
            self._ax_swr.set_xlim(mid - MIN_XSPAN / 2, mid + MIN_XSPAN / 2)
            self._clamping_xlim = False
            return   # xlim_changed fires again with the clamped span
        major, minor = self._pick_step(hi - lo, self._TICK_STEPS)
        for ax in (self._ax_swr, self._ax_imp):
            ax.xaxis.set_major_locator(ticker.MultipleLocator(major))
            ax.xaxis.set_minor_locator(ticker.MultipleLocator(minor))
        self._fig.canvas.draw_idle()

    def _update_swr_yticks(self, *_) -> None:
        lo, hi = self._ax_swr.get_ylim()
        maj, mn = self._pick_step(hi - lo, self._SWR_YTICKS)
        self._ax_swr.yaxis.set_major_locator(ticker.MultipleLocator(maj))
        self._ax_swr.yaxis.set_minor_locator(ticker.MultipleLocator(mn))

    def _update_imp_yticks(self, *_) -> None:
        lo, hi = self._ax_imp.get_ylim()
        maj, mn = self._pick_step(hi - lo, self._IMP_YTICKS)
        self._ax_imp.yaxis.set_major_locator(ticker.MultipleLocator(maj))
        self._ax_imp.yaxis.set_minor_locator(ticker.MultipleLocator(mn))


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    if not args or '--help' in args:
        print(__doc__)
        sys.exit(0 if '--help' in args else 1)

    datasets: list[S1PDataset] = []
    for path in args:
        if not os.path.exists(path):
            print(f"Warning: {path} not found – skipped")
            continue
        ds = parse_s1p(path)
        if len(ds.freqs) == 0:
            print(f"Warning: no data in {path} – skipped")
            continue
        datasets.append(ds)

    if not datasets:
        print("No valid files loaded.")
        sys.exit(1)

    SWRApp(datasets).run()


if __name__ == '__main__':
    main()
