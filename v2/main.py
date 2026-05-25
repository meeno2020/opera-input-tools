"""
Opera Input Tools v2
"""
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import yaml

from button_locator    import ButtonLocatorWidget
from data_loader       import DataLoader
from workflow_config   import WorkflowConfig
from workflow_executor import WorkflowExecutor
from v5_executor       import V5WorkflowExecutor
from ocr_engine        import get_all_displays


class App:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Opera Input Tools")
        self.root.geometry("1000x760")

        self.data_loader     = DataLoader()
        self.wf_config       = WorkflowConfig()
        self.executor:    WorkflowExecutor    | None = None
        self.v5_executor: V5WorkflowExecutor  | None = None
        self._rules: dict = {}

        self._build()
        self._auto_load()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self._tab_annotation(nb)
        self._tab_data(nb)
        self._tab_workflow(nb)
        self._tab_execution(nb)
        self._tab_v5(nb)

    # ═════════════════════════════════════════════════════════════════════════
    # Tab 1 – Button Annotation
    # ═════════════════════════════════════════════════════════════════════════

    def _tab_annotation(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Button Annotation")

        self.locator = ButtonLocatorWidget(f, on_rules_changed=self._rules_changed)

        bar = ttk.Frame(f)
        bar.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(bar, text="Save Button Config",
                   command=self._save_buttons).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Load Button Config",
                   command=self._load_buttons).pack(side=tk.LEFT, padx=4)

    def _rules_changed(self, rules: dict):
        self._rules = rules
        self._sync_button_list()

    def _sync_button_list(self):
        if hasattr(self, '_btn_listbox'):
            self._btn_listbox.delete(0, tk.END)
            for name in sorted(self._rules):
                self._btn_listbox.insert(tk.END, name)

    def _save_buttons(self):
        fp = filedialog.asksaveasfilename(
            title="Save Button Config",
            defaultextension=".yaml",
            filetypes=[("YAML", "*.yaml"), ("All", "*.*")],
        )
        if not fp:
            return
        try:
            with open(fp, 'w', encoding='utf-8') as f:
                yaml.dump({'buttons': self._rules}, f,
                          allow_unicode=True, default_flow_style=False)
            messagebox.showinfo("Saved", "Button config saved.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _load_buttons(self):
        fp = filedialog.askopenfilename(
            title="Load Button Config",
            filetypes=[("YAML", "*.yaml *.yml"), ("All", "*.*")],
        )
        if not fp:
            return
        try:
            with open(fp, encoding='utf-8') as f:
                data = yaml.safe_load(f)
            rules = data.get('buttons', data) or {}
            self._rules = rules
            self.locator.load_rules(rules)
            self._sync_button_list()
            messagebox.showinfo("Loaded", f"Loaded {len(rules)} button rule(s).")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ═════════════════════════════════════════════════════════════════════════
    # Tab 2 – Data File
    # ═════════════════════════════════════════════════════════════════════════

    def _tab_data(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Data File")

        top = ttk.Frame(f)
        top.pack(fill=tk.X, padx=10, pady=8)
        ttk.Button(top, text="Open File...",
                   command=self._open_file).pack(side=tk.LEFT, padx=4)
        self._filepath_var = tk.StringVar(value="No file loaded")
        ttk.Label(top, textvariable=self._filepath_var).pack(side=tk.LEFT, padx=6)

        ttk.Label(f, text="Preview (first 20 rows):").pack(anchor=tk.W, padx=10)
        pf = ttk.Frame(f)
        pf.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        self._data_tree = ttk.Treeview(pf, show="headings")
        sb = ttk.Scrollbar(pf, orient=tk.VERTICAL, command=self._data_tree.yview)
        self._data_tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._data_tree.pack(fill=tk.BOTH, expand=True)

        ttk.Label(f, text="Columns:").pack(anchor=tk.W, padx=10, pady=(4, 0))
        self._cols_var = tk.StringVar()
        ttk.Label(f, textvariable=self._cols_var,
                  wraplength=860).pack(anchor=tk.W, padx=10, pady=4)

    def _open_file(self):
        fp = filedialog.askopenfilename(
            title="Open Data File",
            filetypes=[("Excel / CSV", "*.xlsx *.xls *.csv"), ("All", "*.*")],
        )
        if not fp:
            return
        if self.data_loader.load_file(fp):
            self._filepath_var.set(fp)
            self._refresh_data_preview()
            self._refresh_field_list()
            total = self.data_loader.get_row_count()
            self._start_row_spin.config(to=total)
            if self._start_row_var.get() > total:
                self._start_row_var.set(1)
            if hasattr(self, '_v5_start_spin'):
                self._v5_start_spin.config(to=total)
                if self._v5_start_var.get() > total:
                    self._v5_start_var.set(1)
            messagebox.showinfo("Loaded", f"Loaded {total} row(s).")
        else:
            messagebox.showerror("Error", "Failed to load file.")

    def _refresh_data_preview(self):
        for item in self._data_tree.get_children():
            self._data_tree.delete(item)
        self._data_tree['columns'] = ()
        if not self.data_loader.is_loaded():
            return
        cols = self.data_loader.get_columns()
        self._data_tree['columns'] = cols
        for c in cols:
            self._data_tree.heading(c, text=c)
            self._data_tree.column(c, width=100)
        for _, row in self.data_loader.preview_data(20).iterrows():
            self._data_tree.insert('', tk.END, values=[str(row[c]) for c in cols])

    def _refresh_field_list(self):
        if hasattr(self, '_field_listbox'):
            self._field_listbox.delete(0, tk.END)
            for col in self.data_loader.get_columns():
                self._field_listbox.insert(tk.END, col)
        self._cols_var.set('  |  '.join(self.data_loader.get_columns()))

    # ═════════════════════════════════════════════════════════════════════════
    # Tab 3 – Workflow
    # ═════════════════════════════════════════════════════════════════════════

    def _tab_workflow(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Workflow")

        # Left panel
        left = ttk.LabelFrame(f, text="Available", padding=8)
        left.pack(side=tk.LEFT, fill=tk.BOTH, padx=4, pady=4)

        ttk.Label(left, text="Buttons:").pack(anchor=tk.W)
        self._btn_listbox = tk.Listbox(left, height=4)
        self._btn_listbox.pack(fill=tk.X, pady=2)
        self._btn_listbox.bind('<Double-Button-1>', lambda e: self._add_btn_step())

        ttk.Label(left, text="Fields:").pack(anchor=tk.W, pady=(6, 0))
        self._field_listbox = tk.Listbox(left, height=4)
        self._field_listbox.pack(fill=tk.X, pady=2)
        self._field_listbox.bind('<Double-Button-1>', lambda e: self._add_field_step())

        ttk.Label(left, text="Step type:").pack(anchor=tk.W, pady=(8, 0))
        self._step_type = tk.StringVar(value='click_type')
        for val, lbl in [('click_type',  'Click + Type'),
                          ('tab_type',    'Tab + Type'),
                          ('select_type', 'Dropdown Select'),
                          ('click_only',  'Click Only')]:
            ttk.Radiobutton(left, text=lbl,
                            variable=self._step_type, value=val).pack(anchor=tk.W)

        ttk.Button(left, text="Add Selected",
                   command=self._add_selected).pack(pady=6)

        df = ttk.Frame(left)
        df.pack(fill=tk.X, pady=2)
        ttk.Label(df, text="Delay (s):").pack(side=tk.LEFT)
        self._delay_var = tk.StringVar(value="1")
        ttk.Entry(df, textvariable=self._delay_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(df, text="Add Delay",
                   command=self._add_delay).pack(side=tk.LEFT)

        # Right panel
        right = ttk.LabelFrame(f, text="Steps", padding=8)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        sf = ttk.Frame(right)
        sf.pack(fill=tk.BOTH, expand=True)
        self._wf_listbox = tk.Listbox(sf, height=18)
        wsb = ttk.Scrollbar(sf, orient=tk.VERTICAL, command=self._wf_listbox.yview)
        self._wf_listbox.configure(yscrollcommand=wsb.set)
        wsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._wf_listbox.pack(fill=tk.BOTH, expand=True)
        self._wf_listbox.bind('<Button-1>',        self._drag_start)
        self._wf_listbox.bind('<B1-Motion>',        self._drag_motion)
        self._wf_listbox.bind('<ButtonRelease-1>',  self._drag_end)
        self._drag_idx = None

        bf = ttk.Frame(right)
        bf.pack(fill=tk.X, pady=4)
        for txt, cmd in [("Delete",    self._del_step),
                          ("Move Up",   self._move_up),
                          ("Move Down", self._move_down),
                          ("Clear",     self._clear_wf)]:
            ttk.Button(bf, text=txt, command=cmd).pack(side=tk.LEFT, padx=3)

        sf2 = ttk.Frame(right)
        sf2.pack(fill=tk.X)
        ttk.Button(sf2, text="Save Workflow",
                   command=self._save_wf).pack(side=tk.LEFT, padx=3)
        ttk.Button(sf2, text="Load Workflow",
                   command=self._load_wf).pack(side=tk.LEFT, padx=3)

    # ── Workflow operations ────────────────────────────────────────────────────

    def _add_btn_step(self):
        sel = self._btn_listbox.curselection()
        if not sel:
            return
        name  = self._btn_listbox.get(sel[0])
        stype = self._step_type.get()
        self.wf_config.add_step({'type': stype, 'target': name})
        self._refresh_wf_list()

    def _add_field_step(self):
        sel = self._field_listbox.curselection()
        if not sel:
            return
        col   = self._field_listbox.get(sel[0])
        stype = self._step_type.get()
        self.wf_config.add_step({'type': stype, 'excel_col': col})
        self._refresh_wf_list()

    def _add_selected(self):
        if self._btn_listbox.curselection():
            self._add_btn_step()
        elif self._field_listbox.curselection():
            self._add_field_step()

    def _add_delay(self):
        try:
            self.wf_config.add_step({'type': 'delay',
                                     'seconds': float(self._delay_var.get())})
            self._refresh_wf_list()
        except ValueError:
            messagebox.showerror("Error", "Enter a valid number.")

    def _del_step(self):
        sel = self._wf_listbox.curselection()
        if sel:
            self.wf_config.remove_step(sel[0])
            self._refresh_wf_list()

    def _move_up(self):
        sel = self._wf_listbox.curselection()
        if sel and sel[0] > 0:
            self.wf_config.move_step(sel[0], sel[0] - 1)
            self._refresh_wf_list()
            self._wf_listbox.selection_set(sel[0] - 1)

    def _move_down(self):
        sel = self._wf_listbox.curselection()
        if sel and sel[0] < self.wf_config.get_step_count() - 1:
            self.wf_config.move_step(sel[0], sel[0] + 1)
            self._refresh_wf_list()
            self._wf_listbox.selection_set(sel[0] + 1)

    def _clear_wf(self):
        if messagebox.askyesno("Confirm", "Clear all workflow steps?"):
            self.wf_config.clear_steps()
            self._refresh_wf_list()

    def _refresh_wf_list(self):
        self._wf_listbox.delete(0, tk.END)
        labels = {'click_type': 'Click+Type', 'tab_type': 'Tab+Type',
                  'select_type': 'Select', 'click_only': 'Click',
                  'delay': 'Delay'}
        for step in self.wf_config.get_steps():
            t      = step.get('type', '')
            lbl    = labels.get(t, t)
            target = step.get('target', '')
            col    = step.get('excel_col', '')
            sec    = step.get('seconds', '')
            if t == 'delay':
                self._wf_listbox.insert(tk.END, f"[{lbl}] {sec}s")
            elif target and col:
                self._wf_listbox.insert(tk.END, f"[{lbl}] {target} <- {col}")
            elif target:
                self._wf_listbox.insert(tk.END, f"[{lbl}] {target}")
            elif col:
                self._wf_listbox.insert(tk.END, f"[{lbl}] <- {col}")
            else:
                self._wf_listbox.insert(tk.END, f"[{lbl}]")

    def _save_wf(self):
        fp = filedialog.asksaveasfilename(
            title="Save Workflow",
            defaultextension=".yaml",
            filetypes=[("YAML", "*.yaml"), ("All", "*.*")],
        )
        if fp:
            self.wf_config.set_buttons(self._rules)
            if self.wf_config.save(fp):
                messagebox.showinfo("Saved", "Workflow saved.")
            else:
                messagebox.showerror("Error", "Save failed.")

    def _load_wf(self):
        fp = filedialog.askopenfilename(
            title="Load Workflow",
            filetypes=[("YAML", "*.yaml *.yml"), ("All", "*.*")],
        )
        if fp:
            if self.wf_config.load(fp):
                self._rules = self.wf_config.get_buttons()
                self.locator.load_rules(self._rules)
                self._sync_button_list()
                self._refresh_wf_list()
                messagebox.showinfo(
                    "Loaded",
                    f"Loaded {self.wf_config.get_step_count()} step(s), "
                    f"{len(self._rules)} button rule(s).",
                )
            else:
                messagebox.showerror("Error", "Load failed.")

    # ── Drag & drop ───────────────────────────────────────────────────────────

    def _drag_start(self, e):
        i = self._wf_listbox.nearest(e.y)
        self._drag_idx = i if i >= 0 else None

    def _drag_motion(self, e): pass

    def _drag_end(self, e):
        if self._drag_idx is None:
            return
        i = self._wf_listbox.nearest(e.y)
        if i >= 0 and i != self._drag_idx:
            self.wf_config.move_step(self._drag_idx, i)
            self._refresh_wf_list()
            self._wf_listbox.selection_set(i)
        self._drag_idx = None

    # ═════════════════════════════════════════════════════════════════════════
    # Tab 4 – Execution
    # ═════════════════════════════════════════════════════════════════════════

    def _tab_execution(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Execution")

        sf = ttk.LabelFrame(f, text="Settings", padding=8)
        sf.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(sf, text="Target display:").grid(row=0, column=0,
                                                    sticky=tk.W, padx=4, pady=4)
        self._display_var = tk.IntVar(value=2)
        col = 1
        for d in get_all_displays():
            ttk.Radiobutton(sf, text=f"Display {d['index']}",
                            variable=self._display_var,
                            value=d['index']).grid(row=0, column=col,
                                                   sticky=tk.W, padx=4)
            col += 1

        ttk.Label(sf, text="Start row:").grid(row=1, column=0,
                                               sticky=tk.W, padx=4, pady=4)
        self._start_row_var = tk.IntVar(value=1)
        self._start_row_spin = ttk.Spinbox(sf, from_=1, to=10000,
                                            textvariable=self._start_row_var, width=8)
        self._start_row_spin.grid(row=1, column=1, sticky=tk.W, padx=4)
        sf.columnconfigure(col, weight=1)

        bf = ttk.Frame(f)
        bf.pack(pady=12)
        self._start_btn   = ttk.Button(bf, text="Start",   command=self._exec_start, width=14)
        self._stop_btn    = ttk.Button(bf, text="Stop",    command=self._exec_stop,  width=14, state=tk.DISABLED)
        self._restart_btn = ttk.Button(bf, text="Restart", command=self._exec_restart, width=14, state=tk.DISABLED)
        self._start_btn.pack(side=tk.LEFT, padx=6)
        self._stop_btn.pack(side=tk.LEFT, padx=6)
        self._restart_btn.pack(side=tk.LEFT, padx=6)

        stf = ttk.LabelFrame(f, text="Status", padding=8)
        stf.pack(fill=tk.X, padx=10, pady=4)
        self._exec_status = tk.StringVar(value="Ready")
        ttk.Label(stf, textvariable=self._exec_status,
                  font=("Arial", 11)).pack()
        self._exec_prog = tk.DoubleVar()
        ttk.Progressbar(stf, variable=self._exec_prog,
                        maximum=100).pack(fill=tk.X, pady=6)
        self._exec_prog_txt = tk.StringVar(value="0 / 0")
        ttk.Label(stf, textvariable=self._exec_prog_txt).pack()

        lf = ttk.LabelFrame(f, text="Log", padding=8)
        lf.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        lsb = ttk.Scrollbar(lf)
        lsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._exec_log = tk.Text(lf, height=14, yscrollcommand=lsb.set)
        self._exec_log.pack(fill=tk.BOTH, expand=True)
        lsb.config(command=self._exec_log.yview)

    def _exec_start(self):
        if not self._rules:
            messagebox.showwarning("Warning",
                                   "No button rules. Annotate buttons first.")
            return
        if not self.data_loader.is_loaded():
            messagebox.showwarning("Warning", "Load a data file first.")
            return
        if self.wf_config.get_step_count() == 0:
            messagebox.showwarning("Warning", "Configure workflow steps first.")
            return
        total = self.data_loader.get_row_count()
        start = self._start_row_var.get()
        if not (1 <= start <= total):
            messagebox.showwarning("Warning", f"Start row must be 1–{total}.")
            return

        self.executor = WorkflowExecutor(
            button_rules  = self._rules,
            data_loader   = self.data_loader,
            steps         = self.wf_config.get_steps(),
            display_index = self._display_var.get(),
            callback      = self._exec_progress,
        )
        self._start_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self._restart_btn.config(state=tk.DISABLED)
        self._exec_status.set("Starting...")
        self._exec_log.delete(1.0, tk.END)

        def go():
            import time
            for i in range(3, 0, -1):
                self._exec_status.set(f"Starting in {i}s — switch to target window")
                self._exec_progress(0, 0, f"[{i}] starting soon...")
                time.sleep(1)
            if not self.executor.start(start - 1):
                self._exec_reset()

        threading.Thread(target=go, daemon=True).start()

    def _exec_stop(self):
        if self.executor:
            self.executor.stop()
        self._exec_reset(stopped=True)

    def _exec_restart(self):
        if self.executor and self.executor.is_executing():
            self.executor.stop()
            import time; time.sleep(0.2)
        self._exec_prog.set(0)
        self._exec_prog_txt.set("0 / 0")
        self._exec_log.delete(1.0, tk.END)
        self._exec_start()

    def _exec_reset(self, stopped=False):
        self._start_btn.config(state=tk.NORMAL)
        self._stop_btn.config(state=tk.DISABLED)
        self._restart_btn.config(state=tk.NORMAL)
        self._exec_status.set("Stopped" if stopped else "Ready")

    def _exec_progress(self, current: int, total: int, msg: str):
        if total > 0:
            self._exec_prog.set(current / total * 100)
            self._exec_prog_txt.set(f"{current} / {total}")
        self._exec_log.insert(tk.END, msg + "\n")
        self._exec_log.see(tk.END)
        if current >= total > 0:
            self._exec_reset()
            self._exec_status.set("Completed")

    # ═════════════════════════════════════════════════════════════════════════
    # Tab 5 – V5 Simple Input
    # ═════════════════════════════════════════════════════════════════════════

    def _tab_v5(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="V5 Simple Input")

        sf = ttk.LabelFrame(f, text="Settings", padding=8)
        sf.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(sf, text="Delay per field (s):").grid(row=0, column=0,
                                                         sticky=tk.W, padx=4, pady=4)
        self._v5_delay = tk.DoubleVar(value=1.0)
        ttk.Spinbox(sf, from_=0.1, to=10.0, increment=0.1,
                    textvariable=self._v5_delay, width=8).grid(row=0, column=1,
                                                                sticky=tk.W, padx=4)
        ttk.Label(sf, text="(wait after typing, before Enter)").grid(
            row=0, column=2, sticky=tk.W, padx=4)

        ttk.Label(sf, text="Start row:").grid(row=1, column=0,
                                               sticky=tk.W, padx=4, pady=4)
        self._v5_start_var = tk.IntVar(value=1)
        self._v5_start_spin = ttk.Spinbox(sf, from_=1, to=10000,
                                           textvariable=self._v5_start_var, width=8)
        self._v5_start_spin.grid(row=1, column=1, sticky=tk.W, padx=4)

        self._v5_sound = tk.BooleanVar(value=True)
        ttk.Checkbutton(sf, text="Play sound after each row",
                        variable=self._v5_sound).grid(row=2, column=0,
                                                       columnspan=2, sticky=tk.W,
                                                       padx=4, pady=4)
        sf.columnconfigure(2, weight=1)

        bf = ttk.Frame(f)
        bf.pack(pady=12)
        self._v5_start_btn = ttk.Button(bf, text="Start",
                                         command=self._v5_start, width=14)
        self._v5_stop_btn  = ttk.Button(bf, text="Stop",
                                         command=self._v5_stop,  width=14,
                                         state=tk.DISABLED)
        self._v5_start_btn.pack(side=tk.LEFT, padx=6)
        self._v5_stop_btn.pack(side=tk.LEFT, padx=6)

        stf = ttk.LabelFrame(f, text="Status", padding=8)
        stf.pack(fill=tk.X, padx=10, pady=4)
        self._v5_status = tk.StringVar(value="Ready")
        ttk.Label(stf, textvariable=self._v5_status, font=("Arial", 11)).pack()
        self._v5_prog = tk.DoubleVar()
        ttk.Progressbar(stf, variable=self._v5_prog,
                        maximum=100).pack(fill=tk.X, pady=6)
        self._v5_prog_txt = tk.StringVar(value="0 / 0")
        ttk.Label(stf, textvariable=self._v5_prog_txt).pack()

        lf = ttk.LabelFrame(f, text="Log", padding=8)
        lf.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        lsb = ttk.Scrollbar(lf)
        lsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._v5_log = tk.Text(lf, height=14, yscrollcommand=lsb.set)
        self._v5_log.pack(fill=tk.BOTH, expand=True)
        lsb.config(command=self._v5_log.yview)

    def _v5_start(self):
        if not self.data_loader.is_loaded():
            messagebox.showwarning("Warning", "Load a data file first.")
            return
        total = self.data_loader.get_row_count()
        start = self._v5_start_var.get()
        if not (1 <= start <= total):
            messagebox.showwarning("Warning", f"Start row must be 1–{total}.")
            return

        self.v5_executor = V5WorkflowExecutor(
            self.data_loader,
            callback      = self._v5_progress,
            delay_seconds = self._v5_delay.get(),
            play_sound    = self._v5_sound.get(),
        )
        self._v5_start_btn.config(state=tk.DISABLED)
        self._v5_stop_btn.config(state=tk.NORMAL)
        self._v5_status.set("Starting...")
        self._v5_log.delete(1.0, tk.END)

        def go():
            import time
            for i in range(3, 0, -1):
                self._v5_status.set(f"Starting in {i}s")
                self._v5_progress(0, 0, f"[{i}] starting soon...")
                time.sleep(1)
            if not self.v5_executor.start(start - 1):
                self._v5_start_btn.config(state=tk.NORMAL)
                self._v5_stop_btn.config(state=tk.DISABLED)
                self._v5_status.set("Ready")

        threading.Thread(target=go, daemon=True).start()

    def _v5_stop(self):
        if self.v5_executor:
            self.v5_executor.stop()
        self._v5_start_btn.config(state=tk.NORMAL)
        self._v5_stop_btn.config(state=tk.DISABLED)
        self._v5_status.set("Stopped")

    def _v5_progress(self, current: int, total: int, msg: str):
        if total > 0:
            self._v5_prog.set(current / total * 100)
            self._v5_prog_txt.set(f"{current} / {total}")
        self._v5_log.insert(tk.END, msg + "\n")
        self._v5_log.see(tk.END)
        if current >= total > 0:
            self._v5_start_btn.config(state=tk.NORMAL)
            self._v5_stop_btn.config(state=tk.DISABLED)
            self._v5_status.set("Completed")

    # ═════════════════════════════════════════════════════════════════════════
    # Auto-load saved workflow on startup
    # ═════════════════════════════════════════════════════════════════════════

    def _auto_load(self):
        for name in ('workflow.yaml', 'workflow.yml'):
            if os.path.exists(name):
                if self.wf_config.load(name):
                    self._rules = self.wf_config.get_buttons()
                    self.locator.load_rules(self._rules)
                    self._sync_button_list()
                    self._refresh_wf_list()
                break

    # ═════════════════════════════════════════════════════════════════════════
    # Close
    # ═════════════════════════════════════════════════════════════════════════

    def on_closing(self):
        if self.executor and self.executor.is_executing():
            self.executor.stop()
        if self.v5_executor and self.v5_executor.is_executing():
            self.v5_executor.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    app  = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
