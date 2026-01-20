import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from main import Account, process_account

COLUMNS = [
    "UID add", "MAIL LK IG", "USER", "PASS IG",
    "2FA", "PHOI GOC", "PASS MAIL", "MAIL KHOI PHUC", "NOTE",
]

class AutomationGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GMX Ultra Fast Checker (IMAP)")
        self.geometry("1200x700")

        self.file_path_var = tk.StringVar()
        self.threads_var = tk.IntVar(value=10) # Mặc định 10 luồng
        self.headless_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.StringVar(value="0/0")
        self.success_var = tk.StringVar(value="0")

        self.task_queue = queue.Queue()
        self.update_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.workers = []
        self.running = False
        self.total_count = 0
        self.done_count = 0
        self.success_count = 0

        self._build_ui()
        self.after(200, self._process_updates)

    def _shutdown_workers(self):
        if not self.workers: return
        self.stop_event.set()
        for _ in self.workers:
            try: self.task_queue.put(None)
            except: pass
        for t in self.workers:
            try: t.join(timeout=0.2)
            except: pass
        self.workers = []

    def _build_ui(self):
        self._build_file_frame()
        self._build_config_frame()
        self._build_table()
        self._build_control_frame()

    def _build_file_frame(self):
        frame = ttk.LabelFrame(self, text="Input")
        frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(frame, text="Input file").grid(row=0, column=0, padx=5, pady=5)
        ttk.Entry(frame, textvariable=self.file_path_var, width=70).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(frame, text="Browse", command=self.browse_file).grid(row=0, column=2, padx=5, pady=5)
        ttk.Button(frame, text="Load Data", command=self.load_file).grid(row=0, column=3, padx=5, pady=5)
        ttk.Button(frame, text="Paste Data", command=self.open_paste_dialog).grid(row=0, column=4, padx=5, pady=5)
        frame.columnconfigure(1, weight=1)

    def _build_config_frame(self):
        frame = ttk.LabelFrame(self, text="Config")
        frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(frame, text="Threads").grid(row=0, column=0, padx=5, pady=5)
        ttk.Spinbox(frame, from_=1, to=200, textvariable=self.threads_var, width=5).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(frame, text="Delete Selected", command=self.delete_selected).grid(row=0, column=3, padx=10, pady=5)
        ttk.Button(frame, text="Clear Results", command=self.clear_results).grid(row=0, column=4, padx=5, pady=5)

    def _build_table(self):
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.tree = ttk.Treeview(frame, columns=COLUMNS, show="headings")
        for col in COLUMNS:
            self.tree.heading(col, text=col)
            width = 120 if col != "NOTE" else 250
            self.tree.column(col, width=width, minwidth=80, anchor=tk.W)
        
        # Cấu hình màu sắc (Tags)
        # Success: Chữ xanh đậm, nền xanh nhạt
        self.tree.tag_configure("success", foreground="#1b7f1b", background="#e6f4ea")
        # Error: Chữ đỏ, nền đỏ nhạt
        self.tree.tag_configure("error", foreground="#c62828", background="#fdecea")
        # Running: Chữ xanh dương, nền xanh dương nhạt
        self.tree.tag_configure("running", foreground="#0000FF", background="#e6f0ff")
        
        ys = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        xs = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)

    def _build_control_frame(self):
        frame = ttk.LabelFrame(self, text="Control")
        frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(frame, text="START CHECK", command=self.start).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(frame, text="STOP", command=self.stop).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(frame, text="Progress:").grid(row=0, column=2, padx=10)
        ttk.Label(frame, textvariable=self.progress_var).grid(row=0, column=3, padx=5)
        ttk.Label(frame, text="Success:").grid(row=0, column=4, padx=10)
        ttk.Label(frame, textvariable=self.success_var).grid(row=0, column=5, padx=5)
        ttk.Label(frame, text="Status:").grid(row=0, column=6, padx=10)
        ttk.Label(frame, textvariable=self.status_var).grid(row=0, column=7, padx=5)
        
        ttk.Button(frame, text="Exp Success", command=self.export_success).grid(row=0, column=8, padx=5)
        ttk.Button(frame, text="Exp All", command=self.export_all).grid(row=0, column=9, padx=5)
        ttk.Button(frame, text="Exp Fail", command=self.export_fail).grid(row=0, column=10, padx=5)

    def browse_file(self):
        path = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if path: self.file_path_var.set(path); self.load_file()

    def load_file(self):
        path = self.file_path_var.get().strip()
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f: self._load_rows(self._parse_lines(f.read()))
        except Exception as e: messagebox.showerror("Error", str(e))

    def open_paste_dialog(self):
        dialog = tk.Toplevel(self); dialog.title("Paste Data"); dialog.geometry("800x400")
        btn_frame = ttk.Frame(dialog); btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        text_frame = ttk.Frame(dialog); text_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        text = tk.Text(text_frame); text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text.yview).pack(side=tk.RIGHT, fill=tk.Y)
        text.focus_set()

        def on_submit():
            self._append_rows(self._parse_lines(text.get("1.0", tk.END)))
            dialog.destroy()
        ttk.Button(btn_frame, text="Submit Data", command=on_submit).pack(side=tk.RIGHT, padx=20, pady=10)

    def _parse_lines(self, content):
        lines = [l for l in content.splitlines() if l.strip()]
        if not lines: return []
        expected = len(COLUMNS)
        start = 1 if "uid" in lines[0].lower() and "mail" in lines[0].lower() else 0
        rows = []
        for line in lines[start:]:
            p = [x.strip() for x in line.split("\t")]
            if len(p) == 1: p = line.split()
            if len(p) < expected: p.extend([""]*(expected-len(p)))
            rows.append(p[:expected])
        return rows

    def _load_rows(self, rows):
        self.delete_all()
        for r in rows:
            if not r[-1]: r[-1] = "Pending"
            self.tree.insert("", tk.END, values=r, tags=self._get_tag(r[-1]))
        self._reset_stats()

    def _append_rows(self, rows):
        for r in rows:
            if not r[-1]: r[-1] = "Pending"
            self.tree.insert("", tk.END, values=r, tags=self._get_tag(r[-1]))

    def delete_selected(self):
        for i in self.tree.selection(): self.tree.delete(i)
        self._reset_stats()
    def delete_all(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        self._reset_stats()
    def clear_results(self):
        for i in self.tree.get_children():
            v = list(self.tree.item(i, "values")); v[-1] = "Pending"
            self.tree.item(i, values=v, tags=())

    def _reset_stats(self):
        self.total_count = 0; self.done_count = 0; self.success_count = 0
        self.progress_var.set("0/0"); self.success_var.set("0")

    def _get_tag(self, note):
        n = str(note).lower()
        if "success" in n: return ("success",)
        if "error" in n or "fail" in n: return ("error",)
        if "running" in n or "checking" in n: return ("running",)
        return ()

    def start(self):
        if self.running:
            return
        self._shutdown_workers()
        items = self.tree.get_children()
        tasks = []
        sel = self.tree.selection()
        targets = sel if sel else items

        for i in targets:
            v = list(self.tree.item(i, "values"))
            # Kiểm tra đủ thông tin mail/pass
            if not v[5] or not v[6]:
                v[-1] = "Error: Missing mail/pass"
                self.tree.item(i, values=v, tags=("error",))
                continue
            # Reset trạng thái để luôn kiểm tra lại, kể cả Success
            v[-1] = "Queued"
            self.tree.item(i, values=v, tags=())
            tasks.append((i, v))

        if not tasks:
            messagebox.showinfo("Info", "No valid rows.")
            return

        self.total_count = len(tasks)
        self.done_count = 0
        self.success_count = 0
        self.progress_var.set(f"0/{self.total_count}")
        self.stop_event.clear()
        self.task_queue = queue.Queue()
        for t in tasks:
            self.task_queue.put(t)

        self.workers = []
        for _ in range(max(1, self.threads_var.get())):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            self.workers.append(t)
        self.running = True
        self.status_var.set("Running (IMAP)")

    def stop(self):
        if not self.running: return
        self.stop_event.set()
        while not self.task_queue.empty():
            try: self.task_queue.get_nowait(); self.task_queue.task_done()
            except: break
        self.status_var.set("Stopping...")

    def _worker(self):
        while True:
            try: task = self.task_queue.get(timeout=0.5)
            except: 
                if self.stop_event.is_set(): break
                continue
            if task is None: self.task_queue.task_done(); break
            
            iid, v = task
            if self.stop_event.is_set(): self.task_queue.task_done(); continue

            self.update_queue.put(("status", iid, "Checking..."))
            acc = Account(uid=v[0], mail_login=v[5], ig_user=v[2], mail_pass=v[6])
            
            res = process_account(acc, headless=True) 
            
            # --- XỬ LÝ KẾT QUẢ TỪ MAIN ---
            ok = False
            found_user = None
            
            # Nếu kết quả bắt đầu bằng "success"
            if str(res).startswith("success"):
                ok = True
                # Tách username nếu có định dạng "success|USER=abc"
                if "|USER=" in str(res):
                    parts = str(res).split("|USER=")
                    if len(parts) > 1:
                        found_user = parts[1].strip()
            
            # Gửi thêm found_user vào queue
            self.update_queue.put(("done", iid, ok, res, found_user))
            self.task_queue.task_done()
        self.update_queue.put(("worker_done",))

    def _process_updates(self):
        try:
            while True:
                msg = self.update_queue.get_nowait()
                if msg[0] == "status":
                    self.tree.item(msg[1], values=list(self.tree.item(msg[1], "values")[:-1]) + [msg[2]], tags=("running",))
                
                elif msg[0] == "done":
                    # Unpack: iid, ok, res_raw, found_user
                    iid, ok, res_raw, found_user = msg[1], msg[2], msg[3], msg[4]
                    
                    v = list(self.tree.item(iid, "values"))
                    
                    if ok:
                        v[-1] = "Success"
                        # Cập nhật cột USER (index 2) nếu tìm thấy user
                        if found_user:
                            v[2] = found_user
                        # Cập nhật PASS IG (index 3) = PASS MAIL (index 6)
                        v[3] = v[6]
                        tag = "success" # Tag này đã được config màu xanh lá
                        self.success_count += 1
                    else:
                        v[-1] = res_raw
                        tag = "error" # Tag này màu đỏ
                    
                    self.tree.item(iid, values=v, tags=(tag,))
                    
                    self.done_count += 1
                    self.progress_var.set(f"{self.done_count}/{self.total_count}")
                    self.success_var.set(str(self.success_count))
                    
                elif msg[0] == "worker_done": pass
        except: pass

        if self.running and self.done_count >= self.total_count:
            self.running = False; self._shutdown_workers(); self.status_var.set("Done")
        self.after(200, self._process_updates)

    def export_success(self): self._export(lambda n: "success" in str(n).lower())
    def export_all(self): self._export(lambda n: True)
    def export_fail(self): self._export(lambda n: "fail" in str(n).lower() or "error" in str(n).lower())
    def _export(self, cond):
        rows = [self.tree.item(i, "values") for i in self.tree.get_children() if cond(self.tree.item(i, "values")[-1])]
        if not rows: messagebox.showinfo("Info", "No rows."); return
        path = filedialog.asksaveasfilename(defaultextension=".txt")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\t".join(COLUMNS)+"\n")
                for r in rows: f.write("\t".join(map(str, r))+"\n")
            messagebox.showinfo("OK", "Saved.")

if __name__ == "__main__":
    app = AutomationGUI()
    app.mainloop()