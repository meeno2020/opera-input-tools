"""
Button annotation widget (Plan 2).
Displays a live screenshot in a canvas; the user clicks on a target control
and OCR auto-detects the nearest label to generate a detection rule.
"""
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


class AnnotationSession:
    """Holds the screenshot, OCR word list, and annotated rules for one session."""

    def __init__(self, display_index: int):
        self.display_index = display_index
        self.image: Image.Image | None = None
        self.words: list[dict] = []
        self.rules: dict[str, dict] = {}

    def capture(self):
        self.image = capture_display(self.display_index)
        self.words = ocr_words(self.image)

    def annotate_at(self, px: int, py: int, ann_type: str) -> dict | None:
        """
        Annotate at screenshot pixel (px, py).
        Returns a rule dict, or None if no label was detected nearby.
        """
        label_w = find_label_above(self.words, px, py, search_px=160)
        if not label_w:
            label_w = find_label_left(self.words, px, py, search_px=350)
        if not label_w:
            return None

        label_text = label_w['text']

        if ann_type == 'button':
            rule = {
                'method':   'ocr_right_of',
                'anchor':   label_text,
                'offset_x': max(10, int(px - (label_w['x'] + label_w['w']))),
                'ann_type': ann_type,
            }
        else:
            rule = {
                'method':   'ocr_label_below',
                'label':    label_text,
                'min_y':    max(0, label_w['y'] - 200),
                'offset_y': max(10, int(py - (label_w['y'] + label_w['h']))),
                'ann_type': ann_type,
            }
        return rule

    def add_rule(self, name: str, rule: dict):
        self.rules[name] = rule

    def get_rules(self) -> dict:
        return dict(self.rules)


class ButtonLocatorWidget:
    """
    Embeddable tkinter widget for screenshot-based button annotation.
    The parent receives updated rules via the on_rules_changed callback.
    """

    def __init__(self, parent: tk.Widget, on_rules_changed=None):
        self.parent = parent
        self.on_rules_changed = on_rules_changed
        self.session: AnnotationSession | None = None
        self._tk_image = None
        self._scale = 1.0
        self._ann_type = tk.StringVar(value='input')
        self._name_var = tk.StringVar()
        self._build()

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build(self):
        frame = self.parent

        # Toolbar
        tb = ttk.Frame(frame)
        tb.pack(fill=tk.X, padx=6, pady=4)

        self._display_var = tk.IntVar(value=2)
        ttk.Label(tb, text="Display:").pack(side=tk.LEFT)
        for d in get_all_displays():
            ttk.Radiobutton(tb, text=f"Display {d['index']}",
                            variable=self._display_var,
                            value=d['index']).pack(side=tk.LEFT, padx=2)

        ttk.Button(tb, text="Capture & Annotate",
                   command=self._capture).pack(side=tk.LEFT, padx=10)
        ttk.Separator(tb, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        ttk.Label(tb, text="Type:").pack(side=tk.LEFT)
        for key, lbl in ANNOTATION_TYPES.items():
            ttk.Radiobutton(tb, text=lbl, variable=self._ann_type,
                            value=key).pack(side=tk.LEFT, padx=2)

        ttk.Label(tb, text="  Name:").pack(side=tk.LEFT)
        ttk.Entry(tb, textvariable=self._name_var, width=16).pack(side=tk.LEFT)

        self._hint = tk.StringVar(value='Click "Capture & Annotate" to start.')
        ttk.Label(tb, textvariable=self._hint,
                  foreground='gray').pack(side=tk.LEFT, padx=8)

        # Canvas
        cf = ttk.Frame(frame)
        cf.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)

        self.canvas = tk.Canvas(cf, bg='#1e1e1e', cursor='crosshair')
        hs = ttk.Scrollbar(cf, orient=tk.HORIZONTAL, command=self.canvas.xview)
        vs = ttk.Scrollbar(cf, orient=tk.VERTICAL,   command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hs.set, yscrollcommand=vs.set)
        hs.pack(side=tk.BOTTOM, fill=tk.X)
        vs.pack(side=tk.RIGHT,  fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.bind('<Button-1>', self._on_click)

        # Annotated list
        lf = ttk.LabelFrame(frame, text="Annotated Controls", padding=4)
        lf.pack(fill=tk.X, padx=6, pady=4)

        cols = ('Name', 'Type', 'Method', 'Label / Anchor')
        self.tree = ttk.Treeview(lf, columns=cols, show='headings', height=5)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=140 if c == 'Method' else 110)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self.tree.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=sb.set)

        br = ttk.Frame(frame)
        br.pack(fill=tk.X, padx=6, pady=2)
        ttk.Button(br, text="Delete",  command=self._delete).pack(side=tk.LEFT, padx=4)
        ttk.Button(br, text="Rename",  command=self._rename).pack(side=tk.LEFT, padx=4)

    # ── Capture ───────────────────────────────────────────────────────────────

    def _capture(self):
        self._hint.set("Capturing...")
        self.parent.update()

        self.session = AnnotationSession(self._display_var.get())
        self.session.capture()

        img = self.session.image
        cw = self.canvas.winfo_width()  or 900
        ch = self.canvas.winfo_height() or 500
        self._scale = min(cw / img.width, ch / img.height, 1.0)
        dw = int(img.width  * self._scale)
        dh = int(img.height * self._scale)

        self._tk_image = ImageTk.PhotoImage(img.resize((dw, dh), Image.LANCZOS))
        self.canvas.delete('all')
        self.canvas.config(scrollregion=(0, 0, dw, dh))
        self.canvas.create_image(0, 0, anchor='nw', image=self._tk_image)
        self._hint.set(
            f"Screenshot {img.width}x{img.height}. "
            "Enter a name, choose type, then click on the target control."
        )

    # ── Click annotation ──────────────────────────────────────────────────────

    def _on_click(self, event):
        if self.session is None:
            messagebox.showinfo("Info", 'Click "Capture & Annotate" first.')
            return
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Warning", "Please enter a name before clicking.")
            return

        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        px = int(cx / self._scale)
        py = int(cy / self._scale)

        rule = self.session.annotate_at(px, py, self._ann_type.get())
        if rule is None:
            messagebox.showwarning(
                "Not detected",
                "No label text found near the click point.\n"
                "Ensure a visible text label is near the control."
            )
            return

        self.session.add_rule(name, rule)
        self._refresh_tree()
        self._draw_marker(cx, cy, name)
        self._name_var.set('')

        anchor = rule.get('label') or rule.get('anchor', '')
        self._hint.set(
            f"Annotated [{name}] -> {ANNOTATION_TYPES.get(rule['ann_type'], '')},"
            f" detected label: '{anchor}'"
        )
        if self.on_rules_changed:
            self.on_rules_changed(self.session.get_rules())

    def _draw_marker(self, cx, cy, name):
        r = 6
        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                fill='#ff4444', outline='white', width=2)
        self.canvas.create_text(cx+10, cy-10, text=name, fill='#ffff00',
                                font=('Arial', 10, 'bold'), anchor='w')

    # ── List operations ───────────────────────────────────────────────────────

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        if not self.session:
            return
        for name, rule in self.session.rules.items():
            ann = ANNOTATION_TYPES.get(rule.get('ann_type', ''), rule.get('ann_type', ''))
            self.tree.insert('', tk.END, iid=name,
                             values=(name, ann, rule.get('method', ''),
                                     rule.get('label') or rule.get('anchor', '')))

    def _delete(self):
        for iid in self.tree.selection():
            if self.session:
                self.session.rules.pop(iid, None)
        self._refresh_tree()
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
                self._refresh_tree()
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
        self._refresh_tree()
