"""
Button annotation widget (Plan 2).
Displays a live screenshot; the user drags to define a search region, then
clicks within the region to auto-detect the nearest label and generate a rule.
Multiple displays are supported — rules accumulate across display captures.
Supports mouse-wheel zoom and zoom buttons for easier annotation.
"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

from ocr_engine import (
    get_all_displays, capture_display,
    ocr_words, find_label_above, find_label_left,
)

ANNOTATION_TYPES = {
    'input':    'Input field',
    'dropdown': 'Dropdown',
    'button':   'Button (click only)',
}

_DRAG_THRESHOLD = 6
_ZOOM_STEP      = 1.25   # multiply/divide per zoom click or scroll
_ZOOM_MIN       = 0.1
_ZOOM_MAX       = 8.0


class AnnotationSession:
    """One screenshot + accumulated rules (may span multiple display captures)."""

    def __init__(self, display_index: int):
        self.display_index = display_index
        self.image: Image.Image | None = None
        self.words: list[dict] = []
        self.rules: dict[str, dict] = {}

    def capture(self):
        self.image = capture_display(self.display_index)
        self.words = ocr_words(self.image)

    def annotate_at(self, px: int, py: int, ann_type: str,
                    region: tuple[int, int, int, int] | None = None) -> dict | None:
        """
        Annotate at screenshot pixel (px, py).
        region=(x, y, w, h) in image pixels — constrains OCR to that area.
        Returns a rule dict or None if no label detected.
        """
        if region:
            search_words = ocr_words(self.image, region=region)
        else:
            search_words = self.words

        label_w = find_label_above(search_words, px, py, search_px=160)
        if not label_w:
            label_w = find_label_left(search_words, px, py, search_px=350)
        if not label_w:
            return None

        label_text = label_w['text']

        if ann_type == 'button':
            rule = {
                'method':   'ocr_right_of',
                'anchor':   label_text,
                'offset_x': max(10, int(px - (label_w['x'] + label_w['w']))),
                'ann_type': ann_type,
                'display':  self.display_index,
            }
        else:
            rule = {
                'method':   'ocr_label_below',
                'label':    label_text,
                'min_y':    max(0, label_w['y'] - 200),
                'offset_y': max(10, int(py - (label_w['y'] + label_w['h']))),
                'ann_type': ann_type,
                'display':  self.display_index,
            }

        if region:
            rule['region'] = list(region)

        return rule

    def add_rule(self, name: str, rule: dict):
        self.rules[name] = rule

    def get_rules(self) -> dict:
        return dict(self.rules)


class ButtonLocatorWidget:
    """
    Embeddable tkinter widget for screenshot-based button annotation.

    Interaction:
      1. Pick display → "Capture & Annotate"
      2. Drag on canvas → draws a blue region rectangle
      3. Enter name, choose type → click inside the region → rule saved
      4. Switch display and capture again; previous rules are preserved
      5. Mouse wheel (or +/− buttons) to zoom in/out for precise annotation
    """

    def __init__(self, parent: tk.Widget, on_rules_changed=None):
        self.parent = parent
        self.on_rules_changed = on_rules_changed
        self.session: AnnotationSession | None = None
        self._pil_image: Image.Image | None = None   # full-res capture
        self._tk_image = None
        self._base_scale = 1.0   # scale to fit canvas at 100% zoom
        self._zoom       = 1.0   # user zoom multiplier
        self._scale      = 1.0   # _base_scale * _zoom (pixels → canvas coords)
        self._ann_type = tk.StringVar(value='input')
        self._name_var = tk.StringVar()
        self._zoom_var = tk.StringVar(value='100%')

        # Region state
        self._drag_start: tuple[float, float] | None = None
        self._drag_moved = False
        self._rect_id: int | None = None
        self._region_canvas: tuple[float, float, float, float] | None = None
        self._region_img: tuple[int, int, int, int] | None = None

        # Stored markers for redraw on zoom (list of (img_px, img_py, name, region_img))
        self._marker_list: list[tuple[int, int, str, tuple | None]] = []

        self._build()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        frame = self.parent

        # ── Toolbar row 1: display + capture + zoom ───────────────────────────
        tb1 = ttk.Frame(frame)
        tb1.pack(fill=tk.X, padx=6, pady=(4, 0))

        self._display_var = tk.IntVar(value=1)
        ttk.Label(tb1, text="Display:").pack(side=tk.LEFT)
        for d in get_all_displays():
            ttk.Radiobutton(tb1, text=f"Display {d['index']}",
                            variable=self._display_var,
                            value=d['index']).pack(side=tk.LEFT, padx=2)

        ttk.Button(tb1, text="Capture & Annotate",
                   command=self._capture).pack(side=tk.LEFT, padx=10)

        ttk.Separator(tb1, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(tb1, text="Zoom:").pack(side=tk.LEFT)
        ttk.Button(tb1, text="−", width=2,
                   command=self._zoom_out).pack(side=tk.LEFT, padx=1)
        ttk.Label(tb1, textvariable=self._zoom_var, width=5,
                  anchor='center').pack(side=tk.LEFT)
        ttk.Button(tb1, text="+", width=2,
                   command=self._zoom_in).pack(side=tk.LEFT, padx=1)
        ttk.Button(tb1, text="Fit", width=4,
                   command=self._zoom_fit).pack(side=tk.LEFT, padx=4)

        # ── Toolbar row 2: type + name + region ──────────────────────────────
        tb2 = ttk.Frame(frame)
        tb2.pack(fill=tk.X, padx=6, pady=(2, 0))

        ttk.Label(tb2, text="Type:").pack(side=tk.LEFT)
        for key, lbl in ANNOTATION_TYPES.items():
            ttk.Radiobutton(tb2, text=lbl, variable=self._ann_type,
                            value=key).pack(side=tk.LEFT, padx=2)

        ttk.Separator(tb2, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(tb2, text="Name:").pack(side=tk.LEFT)
        ttk.Entry(tb2, textvariable=self._name_var, width=16).pack(side=tk.LEFT)

        ttk.Separator(tb2, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Button(tb2, text="Clear Region",
                   command=self._clear_region).pack(side=tk.LEFT)

        self._hint = tk.StringVar(value='Click "Capture & Annotate" to start.')
        ttk.Label(frame, textvariable=self._hint,
                  foreground='gray').pack(fill=tk.X, padx=8, pady=1)

        # ── Canvas ────────────────────────────────────────────────────────────
        cf = ttk.Frame(frame)
        cf.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)

        self.canvas = tk.Canvas(cf, bg='#1e1e1e', cursor='crosshair')
        hs = ttk.Scrollbar(cf, orient=tk.HORIZONTAL, command=self.canvas.xview)
        vs = ttk.Scrollbar(cf, orient=tk.VERTICAL,   command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hs.set, yscrollcommand=vs.set)
        hs.pack(side=tk.BOTTOM, fill=tk.X)
        vs.pack(side=tk.RIGHT,  fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind('<Button-1>',        self._on_press)
        self.canvas.bind('<B1-Motion>',       self._on_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)
        self.canvas.bind('<MouseWheel>',      self._on_mousewheel)

        # ── Annotated list ────────────────────────────────────────────────────
        lf = ttk.LabelFrame(frame, text="Annotated Controls", padding=4)
        lf.pack(fill=tk.X, padx=6, pady=4)

        cols = ('Name', 'Disp', 'Type', 'Method', 'Label / Anchor', 'Region')
        self.tree = ttk.Treeview(lf, columns=cols, show='headings', height=5)
        widths = {'Name': 110, 'Disp': 50, 'Type': 100,
                  'Method': 130, 'Label / Anchor': 130, 'Region': 130}
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=widths.get(c, 110))
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self.tree.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=sb.set)

        br = ttk.Frame(frame)
        br.pack(fill=tk.X, padx=6, pady=2)
        ttk.Button(br, text="Delete", command=self._delete).pack(side=tk.LEFT, padx=4)
        ttk.Button(br, text="Rename", command=self._rename).pack(side=tk.LEFT, padx=4)

    # ── Zoom ──────────────────────────────────────────────────────────────────

    def _on_mousewheel(self, event):
        if self._pil_image is None:
            return
        if event.delta > 0:
            self._zoom_in()
        else:
            self._zoom_out()

    def _zoom_in(self):
        self._set_zoom(min(self._zoom * _ZOOM_STEP, _ZOOM_MAX))

    def _zoom_out(self):
        self._set_zoom(max(self._zoom / _ZOOM_STEP, _ZOOM_MIN))

    def _zoom_fit(self):
        self._set_zoom(1.0)

    def _set_zoom(self, new_zoom: float):
        if self._pil_image is None:
            return
        self._zoom  = new_zoom
        self._scale = self._base_scale * self._zoom
        self._zoom_var.set(f'{int(self._scale * 100)}%')
        self._apply_zoom()

    def _apply_zoom(self):
        """Resize displayed image and redraw all markers at new scale."""
        img = self._pil_image
        dw  = max(1, int(img.width  * self._scale))
        dh  = max(1, int(img.height * self._scale))
        self._tk_image = ImageTk.PhotoImage(img.resize((dw, dh), Image.LANCZOS))
        self.canvas.delete('all')
        self.canvas.config(scrollregion=(0, 0, dw, dh))
        self.canvas.create_image(0, 0, anchor='nw', image=self._tk_image)
        self._redraw_markers()

    def _redraw_markers(self):
        """Redraw all annotation markers at current zoom scale."""
        self.canvas.delete('annotation')
        for img_px, img_py, name, region_img in self._marker_list:
            cx = img_px * self._scale
            cy = img_py * self._scale
            if region_img:
                rx, ry, rw, rh = region_img
                self.canvas.create_rectangle(
                    rx * self._scale, ry * self._scale,
                    (rx + rw) * self._scale, (ry + rh) * self._scale,
                    outline='#44ff44', width=1, dash=(4, 3), tags='annotation')
            self._draw_marker(cx, cy, name)

    # ── Capture ───────────────────────────────────────────────────────────────

    def _capture(self):
        self._hint.set("Capturing screenshot and running OCR — please wait...")
        self.parent.update()
        old_rules = self.session.get_rules() if self.session else {}
        display_idx = self._display_var.get()

        def _worker():
            session = AnnotationSession(display_idx)
            session.rules = old_rules
            session.capture()
            self.parent.after(0, lambda: self._on_capture_done(session))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_capture_done(self, session: 'AnnotationSession'):
        self.session   = session
        self._pil_image = session.image
        self._marker_list.clear()
        self._zoom = 1.0

        img = self._pil_image
        cw  = self.canvas.winfo_width()  or 900
        ch  = self.canvas.winfo_height() or 500
        self._base_scale = min(cw / img.width, ch / img.height, 1.0)
        self._scale      = self._base_scale * self._zoom
        self._zoom_var.set(f'{int(self._scale * 100)}%')

        self._clear_region()
        self._apply_zoom()
        self._refresh_tree()
        self._hint.set(
            f"Display {session.display_index}  {img.width}×{img.height} px  "
            f"(zoom: scroll wheel or +/−)  —  "
            "Drag to draw a search region, then click on the target control."
        )

    def _redraw_canvas(self):
        """Called only when redisplaying existing capture (e.g. display switch)."""
        if self._pil_image is None:
            return
        img = self._pil_image
        cw  = self.canvas.winfo_width()  or 900
        ch  = self.canvas.winfo_height() or 500
        self._base_scale = min(cw / img.width, ch / img.height, 1.0)
        self._scale      = self._base_scale * self._zoom
        self._zoom_var.set(f'{int(self._scale * 100)}%')
        self._apply_zoom()

    # ── Drag / click handling ─────────────────────────────────────────────────

    def _on_press(self, event):
        self._drag_start = (self.canvas.canvasx(event.x),
                            self.canvas.canvasy(event.y))
        self._drag_moved = False

    def _on_drag(self, event):
        if not self._drag_start:
            return
        x1, y1 = self._drag_start
        x2 = self.canvas.canvasx(event.x)
        y2 = self.canvas.canvasy(event.y)
        if abs(x2 - x1) > _DRAG_THRESHOLD or abs(y2 - y1) > _DRAG_THRESHOLD:
            self._drag_moved = True
            if self._rect_id is None:
                self._rect_id = self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    outline='#00aaff', width=2, dash=(8, 4), tags='region_live')
            else:
                self.canvas.coords(self._rect_id, x1, y1, x2, y2)

    def _on_release(self, event):
        x2 = self.canvas.canvasx(event.x)
        y2 = self.canvas.canvasy(event.y)

        if self._drag_moved and self._drag_start:
            x1, y1 = self._drag_start
            rx = min(x1, x2);  ry = min(y1, y2)
            rw = abs(x2 - x1); rh = abs(y2 - y1)
            self._region_canvas = (rx, ry, rx + rw, ry + rh)
            s = self._scale
            self._region_img = (int(rx / s), int(ry / s),
                                 int(rw / s), int(rh / s))
            self._hint.set(
                f"Region set  {int(rw/s)}×{int(rh/s)} px  —  "
                "Enter a name, choose type, then click on the target inside the region."
            )
        else:
            cy = self.canvas.canvasy(event.y)
            self._do_annotate(x2, cy)

        self._drag_start = None
        self._drag_moved = False

    def _do_annotate(self, cx: float, cy: float):
        if self.session is None:
            messagebox.showinfo("Info", 'Click "Capture & Annotate" first.')
            return
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Warning", "Enter a name before clicking.")
            return

        px = int(cx / self._scale)
        py = int(cy / self._scale)

        rule = self.session.annotate_at(px, py, self._ann_type.get(),
                                        region=self._region_img)
        if rule is None:
            messagebox.showwarning(
                "Not detected",
                "No label text found near the click point.\n"
                "Make sure a visible text label is near the control,\n"
                "or draw a region that includes the label."
            )
            return

        self.session.add_rule(name, rule)
        self._marker_list.append((px, py, name, self._region_img))
        self._refresh_tree()
        self._redraw_markers()
        self._name_var.set('')

        anchor = rule.get('label') or rule.get('anchor', '')
        region_str = f"  region:{self._region_img}" if self._region_img else ""
        self._hint.set(
            f"Saved [{name}] → {ANNOTATION_TYPES.get(rule['ann_type'], '')}  "
            f"label='{anchor}'{region_str}"
        )
        self._clear_region()

        if self.on_rules_changed:
            self.on_rules_changed(self.session.get_rules())

    def _draw_marker(self, cx: float, cy: float, name: str):
        r = 6
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                fill='#ff4444', outline='white', width=2,
                                tags='annotation')
        self.canvas.create_text(cx + 10, cy - 10, text=name, fill='#ffff00',
                                font=('Arial', 10, 'bold'), anchor='w',
                                tags='annotation')

    def _clear_region(self):
        if self._rect_id is not None:
            self.canvas.delete(self._rect_id)
            self._rect_id = None
        self._region_canvas = None
        self._region_img    = None
        self._drag_start    = None
        self._drag_moved    = False

    # ── List operations ───────────────────────────────────────────────────────

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        if not self.session:
            return
        for name, rule in self.session.rules.items():
            ann = ANNOTATION_TYPES.get(rule.get('ann_type', ''), rule.get('ann_type', ''))
            region = rule.get('region')
            region_str = f"{region[0]},{region[1]} {region[2]}×{region[3]}" if region else "—"
            self.tree.insert('', tk.END, iid=name,
                             values=(name,
                                     rule.get('display', '?'),
                                     ann,
                                     rule.get('method', ''),
                                     rule.get('label') or rule.get('anchor', ''),
                                     region_str))

    def _delete(self):
        for iid in self.tree.selection():
            if self.session:
                self.session.rules.pop(iid, None)
                self._marker_list = [(px, py, n, r) for px, py, n, r
                                     in self._marker_list if n != iid]
        self._refresh_tree()
        self._redraw_markers()
        if self.on_rules_changed and self.session:
            self.on_rules_changed(self.session.get_rules())

    def _rename(self):
        sel = self.tree.selection()
        if not sel or not self.session:
            return
        old = sel[0]
        dlg = tk.Toplevel(self.parent)
        dlg.title("Rename")
        dlg.resizable(False, False)
        ttk.Label(dlg, text="New name:").pack(padx=10, pady=8)
        var = tk.StringVar(value=old)
        e = ttk.Entry(dlg, textvariable=var, width=24)
        e.pack(padx=10)
        e.select_range(0, tk.END)
        e.focus()

        def confirm():
            new = var.get().strip()
            if new and new != old:
                rule = self.session.rules.pop(old)
                self.session.rules[new] = rule
                self._marker_list = [(px, py, new if n == old else n, r)
                                     for px, py, n, r in self._marker_list]
                self._refresh_tree()
                self._redraw_markers()
                if self.on_rules_changed:
                    self.on_rules_changed(self.session.get_rules())
            dlg.destroy()

        ttk.Button(dlg, text="OK", command=confirm).pack(pady=8)
        dlg.bind('<Return>', lambda e: confirm())

    # ── External API ──────────────────────────────────────────────────────────

    def get_rules(self) -> dict:
        return self.session.get_rules() if self.session else {}

    def load_rules(self, rules: dict):
        """Restore annotated rules from a saved config (no re-capture needed)."""
        if self.session is None:
            self.session = AnnotationSession(self._display_var.get())
        self.session.rules = dict(rules)
        self._marker_list.clear()
        self._refresh_tree()
