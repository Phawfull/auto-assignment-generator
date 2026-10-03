import os
from pathlib import Path
import queue
import socket
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from settings import MODEL, SUBJECT, Cancelled
from workflow import process_tutorial


class App:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.running = False
        self.output = None
        root.title("Tutorial to Word")
        root.geometry("730x620")
        root.minsize(650, 550)
        self.values = {key: tk.StringVar(value=value) for key, value in {
            "file": "", "name": "", "registration": "",
            "key": os.environ.get("OPENAI_API_KEY", ""), "model": MODEL,
            "db_host": "127.0.0.1", "db_port": "3306", "db_user": "root", "db_password": "",
        }.items()}
        body = ttk.Frame(root, padding=20)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="Tutorial to Word", font=("Segoe UI", 20, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(body, text="Java answers • actual output screenshots • one Word document").grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 18))
        for row, key, label in [(2, "file", "Word tutorial"), (3, "name", "Full name"), (4, "registration", "Registration no.")]:
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=7, padx=(0, 12))
            ttk.Entry(body, textvariable=self.values[key]).grid(row=row, column=1, sticky="ew", pady=7)
        ttk.Button(body, text="Browse…", command=self.browse).grid(row=2, column=2, padx=(8, 0))
        ttk.Label(body, text=SUBJECT).grid(row=5, column=1, sticky="w", pady=(2, 12))
        controls = ttk.Frame(body)
        controls.grid(row=6, column=0, columnspan=3, sticky="ew")
        ttk.Button(controls, text="AI and MySQL settings", command=self.settings).pack(side="left")
        self.generate = ttk.Button(controls, text="Generate Word document", command=self.start)
        self.generate.pack(side="right")
        self.stop = ttk.Button(controls, text="Stop", command=self.cancel.set, state="disabled")
        self.stop.pack(side="right", padx=8)
        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.grid(row=7, column=0, columnspan=3, sticky="ew", pady=14)
        self.logbox = scrolledtext.ScrolledText(body, height=13, wrap="word", font=("Segoe UI", 10), state="disabled")
        self.logbox.grid(row=8, column=0, columnspan=3, sticky="nsew")
        body.rowconfigure(8, weight=1)
        ttk.Label(body, text="Keep your desktop unlocked while output windows run and are captured.", wraplength=660).grid(row=9, column=0, columnspan=3, sticky="w", pady=(10, 4))
        self.open_button = ttk.Button(body, text="Open output folder", command=self.open_folder, state="disabled")
        self.open_button.grid(row=10, column=0, columnspan=3, sticky="w")
        self.log("Choose your tutorial and enter your details. Add your API key in Settings.")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)

    def log(self, text):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", text + "\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def browse(self):
        path = filedialog.askopenfilename(filetypes=[("Word document", "*.docx")])
        if path:
            self.values["file"].set(path)

    def settings(self):
        window = tk.Toplevel(self.root)
        window.title("AI and MySQL settings")
        window.transient(self.root)
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        fields = [("key", "OpenAI API key"), ("model", "Model"), ("db_host", "MySQL host"),
                  ("db_port", "MySQL port"), ("db_user", "MySQL username"), ("db_password", "MySQL password")]
        for row, (key, label) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=6, padx=(0, 12))
            ttk.Entry(frame, textvariable=self.values[key], width=45,
                      show="*" if key in ("key", "db_password") else "").grid(row=row, column=1, pady=6)
        ttk.Label(frame, text="The tutorial text is sent to OpenAI. API usage is billed to your account.\n"
                  "Keys/passwords stay in memory. Generated programs run on this computer.\n"
                  "MySQL needs permission to create a separate tutorial database.\n"
                  "Demonstration databases are retained; their names are saved with the output.",
                  wraplength=520).grid(row=6, column=0, columnspan=2, sticky="w", pady=12)
        ttk.Button(frame, text="Done", command=window.destroy).grid(row=7, column=1, sticky="e")

    def start(self):
        if self.running:
            return
        settings = {key: value.get() for key, value in self.values.items()}
        for key in ("file", "name", "registration", "key", "model", "db_host", "db_port", "db_user"):
            settings[key] = settings[key].strip()
        if not all(settings[key] for key in ("file", "name", "registration", "key", "model")):
            messagebox.showerror("Missing information", "Choose a tutorial, enter your name and registration number, and add your API key in Settings.")
            return
        if not Path(settings["file"]).is_file():
            messagebox.showerror("File not found", "Choose an existing Word tutorial.")
            return
        self.running = True
        self.cancel.clear()
        self.generate.configure(state="disabled")
        self.stop.configure(state="normal")
        self.progress.start()
        self.log("Starting…")
        threading.Thread(target=self.worker, args=(settings,), daemon=True).start()

    def worker(self, settings):
        try:
            path, failed = process_tutorial(settings, self.cancel,
                lambda text: self.events.put(("log", text)),
                lambda path: self.events.put(("folder", path)))
            self.events.put(("done", (path, failed)))
        except Cancelled as exc:
            self.events.put(("stopped", str(exc)))
        except Exception as exc:
            text = str(exc)
            if isinstance(exc, (ConnectionRefusedError, socket.timeout, TimeoutError)):
                text = "MySQL is not reachable. Start your MySQL server and check its host and port in Settings."
            for secret in (settings["key"], settings["db_password"]):
                if secret:
                    text = text.replace(secret, "[redacted]")
            self.events.put(("error", text))

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self.log(value)
                elif kind == "folder":
                    self.output = value
                    self.open_button.configure(state="normal")
                else:
                    self.running = False
                    self.generate.configure(state="normal")
                    self.stop.configure(state="disabled")
                    self.progress.stop()
                    if kind == "done":
                        path, failed = value
                        self.log("Saved: " + str(path))
                        if failed:
                            messagebox.showwarning("Partial document saved", f"{failed} question(s) could not be verified. The document is labelled INCOMPLETE. Details are in the output folder.")
                        else:
                            messagebox.showinfo("Document ready", "All questions compiled and ran with the generated demo checks. Review the document before using it.\n\n" + str(path))
                    elif kind == "error":
                        self.log(value)
                        messagebox.showerror("Could not finish", value)
                    else:
                        self.log(value)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def open_folder(self):
        if self.output:
            os.startfile(self.output)

    def close(self):
        if self.running:
            self.cancel.set()
            self.log("Stopping… The window will stay open until the current request returns.")
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
