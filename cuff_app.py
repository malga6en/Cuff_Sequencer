import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import csv
import queue
from datetime import datetime
from pathlib import Path

import serial
import serial.tools.list_ports

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from PIL import Image, ImageTk


BAR_MAX = 0.5
V_AT_BAR_MAX = 4.35 #3.4
BAUDRATE = 115200
BAR_TO_MMHG = 750.061683


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


def list_serial_ports():
    return [p.device for p in serial.tools.list_ports.comports()]


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def sanitize_filename_part(text):
    text = text.strip()
    if not text:
        return "test"
    out = []
    for ch in text:
        if ch.isalnum() or ch in ("-", "_"):
            out.append(ch)
        elif ch == " ":
            out.append("_")
    result = "".join(out)
    return result if result else "test"


def bar_to_voltage(bar_value):
    bar_value = clamp(bar_value, 0.0, BAR_MAX)
    return (bar_value / BAR_MAX) * V_AT_BAR_MAX


def bar_to_mmhg(bar_value):
    return bar_value * BAR_TO_MMHG


def mmhg_to_bar(mmhg_value):
    return mmhg_value / BAR_TO_MMHG


class CuffApp:
    def __init__(self, root):
        self.root = root
        root.title("Manschetten Sequencer")
        root.geometry("1300x750")

        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "Bold.TLabel",
            font=("Arial", 10, "bold")
        )

        style.configure(
            "Bold.TLabelframe.Label",
            font=("Arial", 10, "bold")
        )

        style.configure(
            "Start.TButton",
            background="#28a745",
            foreground="white",
            font=("Arial", 10, "bold")
        )

        style.configure(
            "Stop.TButton",
            background="#dc3545",
            foreground="white",
            font=("Arial", 10, "bold")
        )

        self.ser = None
        self.worker = None
        self.stop_event = threading.Event()
        self.msg_queue = queue.Queue()
        self.rx_buffer = ""

        self.rows = []
        self.rows_lock = threading.Lock()

        self.use_bar = tk.BooleanVar(value=False)   # True = bar, False = mmHg
        self.last_pressure_bar = 0.0

        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # =========================================================
        # Scrollbarer Hauptbereich
        # =========================================================

        container = ttk.Frame(root)
        container.grid(row=0, column=0, sticky="nsew")

        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        canvas = tk.Canvas(
            container,
            highlightthickness=0
        )

        scrollbar = ttk.Scrollbar(
            container,
            orient="vertical",
            command=canvas.yview
        )

        canvas.configure(
            yscrollcommand=scrollbar.set
        )

        canvas.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        scrollbar.grid(
            row=0,
            column=1,
            sticky="ns"
        )

        # Hauptframe
        main = ttk.Frame(
            canvas,
            padding=10
        )

        self.canvas_window = canvas.create_window(
            (0, 0),
            window=main,
            anchor="nw"
        )

        self.canvas = canvas
        self.main = main


        # Scrollbereich automatisch aktualisieren
        def update_scrollregion(event=None):
            canvas.configure(
                scrollregion=canvas.bbox("all")
            )

        main.bind(
            "<Configure>",
            update_scrollregion
        )


        # Breite an Fenster anpassen
        def resize_canvas(event):
            canvas.itemconfigure(
                self.canvas_window,
                width=event.width
            )

        canvas.bind(
            "<Configure>",
            resize_canvas
        )


        # Mausrad
        def mousewheel(event):
            canvas.yview_scroll(
                int(-1 * (event.delta / 120)),
                "units"
            )

        canvas.bind_all(
            "<MouseWheel>",
            mousewheel
        )
        main.columnconfigure(4, weight=1)
        main.rowconfigure(5, weight=1)

        # Top bar -------------------------------------------------
        topbar = ttk.Frame(main)
        topbar.grid(column=0, row=0, columnspan=6, sticky="ew", pady=(0, 8))

        ttk.Label(topbar, text="Port:", style="Bold.TLabel").pack(side="left", padx=(0, 4))

        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(
            topbar,
            textvariable=self.port_var,
            values=list_serial_ports(),
            width=12
        )
        self.port_cb.pack(side="left", padx=(0, 4))

        ttk.Button(topbar, text="Refresh", command=self.refresh_ports).pack(side="left", padx=(0, 4))
        ttk.Button(topbar, text="Open port", command=self.open_port).pack(side="left", padx=(0, 4))
        ttk.Button(topbar, text="Close port", command=self.close_port).pack(side="left", padx=(0, 8))

        ttk.Button(topbar, text="Anleitung", command=self.open_help_window).pack(side="right", padx=(12, 0))

        ttk.Checkbutton(
            topbar,
            text="bar",
            variable=self.use_bar,
            command=self.toggle_unit
        ).pack(side="right", padx=(4, 8))
        
        ttk.Label(topbar, text="Einheit", style="Bold.TLabel").pack(side="right", padx=(8, 4))
        

        

        # Pattern blocks ------------------------------------------
        self.patterns = []

        pattern_defaults = [
            ("Protokoll A", True,  300.0, 0.0, 15,  15,  2),
            ("Protokoll B", False, 0.0,   0.0, 0,   120, 1),
            ("Protokoll C", False, 300.0, 0.0, 300, 180, 1),
            ("Protokoll D", False, 300.0, 0.0, 5,   5,   5),
            ("Protokoll E", False, 300.0, 0.0, 10,  10,  5),
            ("Protokoll F", False, 300.0, 0.0, 15,  15,  8),
        ]

        for idx, (name, enabled, p_in, p_out, t_in, t_out, reps) in enumerate(pattern_defaults):

            protocol_column = idx % 3
            protocol_row = 1 + (idx // 3)

            # ---------------------------------------------------------
            # Checkbox + Protokollname als Titel
            # ---------------------------------------------------------
            enabled_var = tk.BooleanVar(value=enabled)

            title_frame = ttk.Frame(main)

            ttk.Checkbutton(
                title_frame,
                variable=enabled_var
            ).pack(side="left")

            ttk.Label(
                title_frame,
                text=name,
                style="Bold.TLabel"
            ).pack(side="left", padx=(2, 0))

            # ---------------------------------------------------------
            # Protokoll-Frame
            # ---------------------------------------------------------
            frame = ttk.LabelFrame(
                main,
                labelwidget=title_frame,
                padding=10
            )

            frame.grid(
                column=protocol_column,
                row=protocol_row,
                padx=8,
                pady=8,
                sticky="n"
            )

            # ---------------------------------------------------------
            # Inflate
            # ---------------------------------------------------------
            ttk.Label(
                frame,
                text="Inflate:"
            ).grid(
                column=0,
                row=0,
                sticky="w",
                pady=(5, 0)
            )

            # Druck
            inflate_var = tk.DoubleVar(value=p_in)

            ttk.Entry(
                frame,
                textvariable=inflate_var,
                width=7
            ).grid(
                column=1,
                row=0,
                padx=(5, 2),
                pady=(5, 0)
            )

            inflate_unit_label = ttk.Label(
                frame,
                text="[mmHg]"
            )

            inflate_unit_label.grid(
                column=2,
                row=0,
                sticky="w",
                pady=(5, 0)
            )

            # Zeit
            t_inflate_var = tk.DoubleVar(value=t_in)

            ttk.Entry(
                frame,
                textvariable=t_inflate_var,
                width=6
            ).grid(
                column=3,
                row=0,
                padx=(12, 2),
                pady=(5, 0)
            )

            ttk.Label(
                frame,
                text="[s]"
            ).grid(
                column=4,
                row=0,
                sticky="w",
                pady=(5, 0)
            )

            # ---------------------------------------------------------
            # Deflate
            # ---------------------------------------------------------
            ttk.Label(
                frame,
                text="Deflate:"
            ).grid(
                column=0,
                row=1,
                sticky="w"
            )

            # Druck
            deflate_var = tk.DoubleVar(value=p_out)

            ttk.Entry(
                frame,
                textvariable=deflate_var,
                width=7
            ).grid(
                column=1,
                row=1,
                padx=(5, 2)
            )

            deflate_unit_label = ttk.Label(
                frame,
                text="[mmHg]"
            )

            deflate_unit_label.grid(
                column=2,
                row=1,
                sticky="w"
            )

            # Zeit
            t_deflate_var = tk.DoubleVar(value=t_out)

            ttk.Entry(
                frame,
                textvariable=t_deflate_var,
                width=6
            ).grid(
                column=3,
                row=1,
                padx=(12, 2)
            )

            ttk.Label(
                frame,
                text="[s]"
            ).grid(
                column=4,
                row=1,
                sticky="w"
            )

            # ---------------------------------------------------------
            # Repetitions
            # ---------------------------------------------------------
            ttk.Label(
                frame,
                text="Reps:"
            ).grid(
                column=0,
                row=2,
                sticky="w",
                pady=(8, 0)
            )

            reps_var = tk.IntVar(value=reps)

            ttk.Entry(
                frame,
                textvariable=reps_var,
                width=7
            ).grid(
                column=1,
                row=2,
                padx=(5, 2),
                pady=(8, 0)
            )

            # ---------------------------------------------------------
            # Daten speichern
            # ---------------------------------------------------------
            self.patterns.append({
                "name": name,
                "enabled": enabled_var,
                "inflate_bar": inflate_var,
                "deflate_bar": deflate_var,
                "inflate_s": t_inflate_var,
                "deflate_s": t_deflate_var,
                "reps": reps_var,
                "inflate_unit_label": inflate_unit_label,
                "deflate_unit_label": deflate_unit_label,
            })


        # Bottom controls -----------------------------------------
        ctrl = ttk.Frame(main)

        ctrl.grid(
            column=3,
            row=2,
            columnspan=2,
            sticky="nw",
            padx=(12, 0),
            pady=(8, 0)
        )

        ttk.Button(ctrl, text="Start", command=self.start,style="Start.TButton").grid(column=0, row=0, padx=(0, 10), pady=(0,10))
        ttk.Button(ctrl, text="Stop", command=self.stop,style="Stop.TButton").grid(column=1, row=0, padx=(0, 10), pady=(0,10))

        ttk.Label(ctrl, text="Filename:",style="Bold.TLabel").grid(column=0, row=1, sticky="w", pady=(0,10))
        self.filename_var = tk.StringVar(value="test")
        ttk.Entry(ctrl, textvariable=self.filename_var, width=16).grid(column=1, row=1, padx=(0,5))
        ttk.Label(ctrl, text=".csv").grid(column=2, row=1, sticky="w")

        self.status_var = tk.StringVar(value="IDLE")

        ttk.Label(ctrl,text="Status:").grid(
            column=0,
            row=2,
            sticky="w",
            padx=(0, 5),
            pady=(0,10)
        )

        ttk.Label(
            ctrl,
            textvariable=self.status_var,
            style="Bold.TLabel"
        ).grid(
            column=1,
            row=2,
            sticky="w",
            padx=(0, 5),
            pady=(0,10)
        )

        self.current_pressure_label = ttk.Label(
            ctrl,
            text="Current pressure [mmHg]:",
            #style="Bold.TLabel"
        ).grid(
            column=0,
            row=3,
            sticky="e",
            padx=(0, 5),
            pady=(0,10)
        )

        self.pressure_var = tk.StringVar(value="0.000 mmHg")

        self.pressure_entry = ttk.Label(
            ctrl,
            textvariable=self.pressure_var,
            style="Bold.TLabel"
        ).grid(
            column=1,
            row=3,
            sticky="w",
            padx=(0, 5),
            pady=(0,10)
        )

        ## Zeit
        self.target_time_var = tk.StringVar(value="--")

        ttk.Label(
            ctrl,
            text="Target time:",
            #style="Bold.TLabel"
        ).grid(
            column=0,
            row=4,
            sticky="e",
            padx=(0, 5),
            pady=(0,0)
        )

        ttk.Label(
            ctrl,
            textvariable=self.target_time_var,
            style="Bold.TLabel"
        ).grid(
            column=1,
            row=4,
            sticky="w",
            padx=(0,0),
            pady=(0,0)
        )

        ttk.Label(
            ctrl,
            text="[s]"
        ).grid(
            column=2,
            row=4,
            sticky="w",
            padx=(0, 5),
            pady=(0,0)
        )

        # Log rechts neben den Pattern-Blöcken
        self.log = tk.Text(main, height=5, width=40)
        self.log.grid(column=3, row=1, rowspan=1, padx=(12, 0), pady=14, sticky="ns")

        # Live plot -----------------------------------------------
        plot_frame = ttk.LabelFrame(main, text="Live Plot", padding=5, style="Bold.TLabelframe")
        plot_frame.grid(column=0, row=5, columnspan=4, pady=(0, 10), sticky="nsew")

        self.live_fig = Figure(figsize=(9, 2.5), dpi=100)
        self.live_ax = self.live_fig.add_subplot(111)
        self.live_ax.set_xlabel("Zeit [s]")
        self.live_ax.set_ylabel("Druck [mmHg]")
        self.live_ax.grid(True)
        self.live_fig.subplots_adjust(bottom=0.20)
        self.live_line, = self.live_ax.plot([], [])

        self.live_canvas = FigureCanvasTkAgg(self.live_fig, master=plot_frame)
        self.live_canvas.draw()
        self.live_canvas.get_tk_widget().pack(fill="both", expand=True)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(50, self.process_queue)

        # Logos rechts --------------------------------------------
        logo_frame = ttk.Frame(main)
        logo_frame.grid(column=4, row=5, rowspan=2, sticky="w", padx=(0, 0),pady=(15, 0))

        def load_logo(path, size):
            img = Image.open(path).convert("RGBA")
            img = img.resize(size, Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)

        self.fhwn_logo = load_logo(resource_path("FHWN.png"), (125, 125))
        self.sport_logo = load_logo(resource_path("Sport.jpeg"), (125, 125))
        self.technik_logo = load_logo(resource_path("Technik.jpeg"), (125, 120))

        ttk.Label(logo_frame, image=self.fhwn_logo).pack(pady=(0, 0))
        ttk.Label(logo_frame, image=self.sport_logo).pack()
        ttk.Label(logo_frame, image=self.technik_logo).pack()

    # ------------------------------------------------------------
    # Hilfsfunktionen Einheit
    # ------------------------------------------------------------
    def current_unit_text(self):
        return "bar" if self.use_bar.get() else "mmHg"


    def display_value_to_bar(self, value):
        if self.use_bar.get():
            return value
        return mmhg_to_bar(value)


    def bar_to_display_value(self, value_bar):
        if self.use_bar.get():
            return value_bar
        return bar_to_mmhg(value_bar)


    def format_pressure_text(self, value_bar):
        display_value = self.bar_to_display_value(value_bar)

        if self.use_bar.get():
            return f"{display_value:.3f} bar"

        return f"{display_value:.1f} mmHg"


    def update_pressure_display(self):
        self.pressure_var.set(
            self.format_pressure_text(self.last_pressure_bar)
        )

    def toggle_unit(self):
        to_bar = self.use_bar.get()

        for p in self.patterns:
            try:
                inflate_val = float(p["inflate_bar"].get())
                deflate_val = float(p["deflate_bar"].get())
            except Exception:
                continue

            if to_bar:
                # mmHg -> bar
                p["inflate_bar"].set(
                    round(mmhg_to_bar(inflate_val), 3)
                )
                p["deflate_bar"].set(
                    round(mmhg_to_bar(deflate_val), 3)
                )

                p["inflate_unit_label"].config(text="[bar]")
                p["deflate_unit_label"].config(text="[bar]")

            else:
                # bar -> mmHg
                p["inflate_bar"].set(
                    round(bar_to_mmhg(inflate_val), 1)
                )
                p["deflate_bar"].set(
                    round(bar_to_mmhg(deflate_val), 1)
                )

                p["inflate_unit_label"].config(text="[mmHg]")
                p["deflate_unit_label"].config(text="[mmHg]")

        self.current_pressure_label.config(
            text=f"Current pressure [{self.current_unit_text()}]:"
        )

        self.update_pressure_display()
        self.update_live_plot()
    # ------------------------------------------------------------
    # UI / Serial
    # ------------------------------------------------------------
    def refresh_ports(self):
        self.port_cb["values"] = list_serial_ports()

    def open_port(self):
        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning("Port", "Wähle einen Port")
            return

        try:
            if self.ser and self.ser.is_open:
                self.ser.close()

            self.ser = serial.Serial(port, BAUDRATE, timeout=0.1)
            time.sleep(0.2)
            self.rx_buffer = ""
            self.log_insert(f"Opened {port}")
        except Exception as e:
            messagebox.showerror("Serial", str(e))

    def close_port(self):
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
            self.log_insert("Port closed")

    def open_help_window(self):
        help_win = tk.Toplevel(self.root)
        help_win.title("Anleitung")
        help_win.geometry("560x440")
        help_win.transient(self.root)
        help_win.grab_set()

        ttk.Label(
            help_win,
            text="Bedienungsanleitung",
            font=("Arial", 12, "bold")
        ).pack(pady=(10, 5))

        help_text = tk.Text(help_win, wrap="word", font=("Arial", 10))
        help_text.pack(fill="both", expand=True, padx=10, pady=10)

        anleitung = (
            "1. COM-Port auswählen.\n"
            "2. Auf 'Open port' klicken.\n"
            "3. Gewünschte Protokolle aktivieren.\n"
            "4. Inflate-/Deflate-Druck und Zeiten einstellen.\n"
            "5. Reps festlegen.\n"
            "6. Optional die Eingabeeinheit bar/mmHg umschalten.\n"
            "7. Dateinamen eingeben.\n"
            "8. Mit 'Start' den Ablauf starten.\n"
            "9. Mit 'Stop' abbrechen.\n\n"
            "Hinweise:\n"
            "- Die Umschaltung bar/mmHg betrifft nur die GUI.\n"
            "- An den Arduino werden weiterhin bar-basierte Werte gesendet.\n"
            "- Der aktuelle Druck wird rechts angezeigt.\n"
            "- Der Live Plot zeigt den Druckverlauf.\n"
            "- Nach Abschluss werden CSV und Plot gespeichert.\n"
        )

        help_text.insert("1.0", anleitung)
        help_text.config(state="disabled")

        ttk.Button(help_win, text="Schließen", command=help_win.destroy).pack(pady=(0, 10))

    def send_line(self, line):
        if not self.ser or not self.ser.is_open:
            return False
        self.ser.write((line + "\n").encode("ascii"))
        return True

    # ------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------
    def start(self):
        if not self.ser or not self.ser.is_open:
            messagebox.showwarning("Port", "Port öffnen zuerst")
            return

        if self.worker is not None and self.worker.is_alive():
            messagebox.showinfo("Running", "Already running")
            return

        selected = []
        for p in self.patterns:
            if not p["enabled"].get():
                continue

            try:
                inflate_input = float(p["inflate_bar"].get())
                deflate_input = float(p["deflate_bar"].get())

                inflate_bar = clamp(self.display_value_to_bar(inflate_input), 0.0, BAR_MAX)
                deflate_bar = clamp(self.display_value_to_bar(deflate_input), 0.0, BAR_MAX)

                inflate_s = max(0.0, float(p["inflate_s"].get()))
                deflate_s = max(0.0, float(p["deflate_s"].get()))
                reps = int(float(p["reps"].get()))
                if reps < 1:
                    reps = 1
            except Exception:
                messagebox.showerror("Fehler", f"Ungültige Werte bei {p['name']}")
                return

            selected.append({
                "name": p["name"],
                "inflate_bar": inflate_bar,
                "deflate_bar": deflate_bar,
                "inflate_s": inflate_s,
                "deflate_s": deflate_s,
                "reps": reps,
            })

        if not selected:
            messagebox.showwarning("Pattern", "Mindestens ein Muster auswählen")
            return

        filename_base = sanitize_filename_part(self.filename_var.get())
        now = datetime.now().strftime("%Y%m%d-%H%M%S")
        base_name = f"{now}-{filename_base}"
        csv_path = Path(f"{base_name}.csv")
        plot_path = Path(f"{base_name}.png")

        with self.rows_lock:
            self.rows = []

        self.last_pressure_bar = 0.0
        self.update_pressure_display()

        self.target_time_var.set("--")

        self.live_line.set_data([], [])
        self.live_ax.relim()
        self.live_ax.autoscale_view()
        self.live_canvas.draw_idle()

        if self.ser and self.ser.is_open:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

        self.stop_event.clear()
        self.worker = threading.Thread(
            target=self.worker_run,
            args=(selected, csv_path, plot_path),
            daemon=True
        )
        self.worker.start()
        self.status_var.set("RUNNING")

    def stop(self):
        self.stop_event.set()

        if self.ser and self.ser.is_open:
            self.send_line("STOP")

        self.last_pressure_bar = 0.0
        self.update_pressure_display()
        self.target_time_var.set("--")
        self.status_var.set("STOPPING...")

    # ------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------
    def worker_run(self, selected_patterns, csv_path, plot_path):
        file_exists = csv_path.exists()

        try:
            result = "STOPPED"

            for p in selected_patterns:
                if self.stop_event.is_set():
                    result = "STOPPED"
                    break

                inflate_v = bar_to_voltage(p["inflate_bar"])
                deflate_v = bar_to_voltage(p["deflate_bar"])
                inflate_ms = int(round(p["inflate_s"] * 1000))
                deflate_ms = int(round(p["deflate_s"] * 1000))
                reps = p["reps"]

                cmd = f"RUN {inflate_v:.3f} {deflate_v:.3f} {inflate_ms} {deflate_ms} {reps}"
                self.msg_queue.put(("status", f"RUNNING {p['name']}"))

                if not self.send_line(cmd):
                    self.msg_queue.put(("log", "Serial port not open"))
                    result = "STOPPED"
                    break

                finished = False

                # --- Target-time measurement state ---
                target_bar = p["inflate_bar"]
                inflate_start_time = None
                target_reached = False
                last_phase = None
                current_target_time = None

                while not self.stop_event.is_set():
                    lines = self.read_serial_lines()

                    for line in lines:
                        # --------------------------------------------------
                        # Phase messages from Arduino
                        # --------------------------------------------------
                        if line.startswith("PHASE INFLATE"):
                            inflate_start_time = time.perf_counter()
                            target_reached = False
                            last_phase = "INFLATE"
                            self.msg_queue.put(("target_time", "--"))
                            self.msg_queue.put(("log", f"<< {line}"))
                            continue

                        if line.startswith("PHASE DEFLATE"):
                            inflate_start_time = None
                            target_reached = False
                            last_phase = "DEFLATE"
                            self.msg_queue.put(("target_time", "--"))
                            self.msg_queue.put(("log", f"<< {line}"))
                            continue

                        # --------------------------------------------------
                        # End / error messages
                        # --------------------------------------------------
                        if (
                            line == "DONE"
                            or line == "STOPPED"
                            or line.startswith("ERR")
                        ):
                            self.msg_queue.put(("log", f"<< {line}"))

                            if line == "DONE":
                                finished = True
                                result = "DONE"
                                break
                            elif line == "STOPPED":
                                finished = True
                                result = "STOPPED"
                                break
                            else:
                                # ERR -> auch abbrechen
                                finished = True
                                result = "STOPPED"
                                break

                        # --------------------------------------------------
                        # Data messages
                        # --------------------------------------------------
                        if line.startswith("DATA,"):
                            parts = line.split(",")
                            if len(parts) >= 5:
                                pc_now = datetime.now()
                                try:
                                    t_ms = int(parts[1])
                                    phase = parts[2]
                                    adc_raw = int(parts[3])
                                    bar_val = float(parts[4])
                                except Exception:
                                    continue

                                phase_norm = str(phase).strip().upper()

                                # Zielzeit nur während Inflate messen
                                if (
                                    inflate_start_time is not None
                                    and not target_reached
                                    and phase_norm.startswith("INFLATE")
                                ):
                                    if bar_val >= target_bar:
                                        elapsed_s = time.perf_counter() - inflate_start_time
                                        target_reached = True

                                        # Target-Zeit speichern
                                        current_target_time = elapsed_s

                                        # GUI aktualisieren
                                        self.msg_queue.put(
                                            ("target_time", f"{elapsed_s:.2f}")
                                        )

                                with self.rows_lock:
                                    self.rows.append({
                                        "date": pc_now.strftime("%Y-%m-%d"),
                                        "time": pc_now.strftime("%H:%M:%S"),
                                        "pattern": p["name"],
                                        "t_ms": t_ms,
                                        "phase": phase,
                                        "adc_raw": adc_raw,
                                        "bar": bar_val,
                                        "mmHg": round(bar_to_mmhg(bar_val), 1),
                                        "target_time_s": (
                                            round(current_target_time, 2)
                                            if current_target_time is not None
                                            else ""
                                        ),
                                    })

                                self.msg_queue.put(("pressure", bar_val))
                                self.msg_queue.put(("plot_update", None))
                                continue

                        # Andere Zeilen nur ins Log
                        if line:
                            self.msg_queue.put(("log", f"<< {line}"))

                    if finished:
                        break

                    time.sleep(0.02)

                if result != "DONE":
                    break

            rows_snapshot = self.get_rows_snapshot()

            if result == "DONE":
                self.write_csv(csv_path, rows_snapshot, file_exists)
                self.save_plot(rows_snapshot, plot_path)
            else:
                self.msg_queue.put(("log", "Run stopped, not saved"))

            self.msg_queue.put(("status", "IDLE"))

        except Exception as e:
            self.msg_queue.put(("log", f"Worker error: {e}"))
            self.msg_queue.put(("status", "ERROR"))
        finally:
            self.msg_queue.put(("worker_done", None))
    # ------------------------------------------------------------
    # Daten / Plot
    # ------------------------------------------------------------
    def write_csv(self, csv_path, rows, file_exists):
        try:
            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["date", "time", "pattern", "t_ms", "phase", "adc_raw", "bar","mmHg","target_time_s"]
                )
                if not file_exists:
                    writer.writeheader()
                for row in rows:
                    writer.writerow(row)
        except Exception as e:
            self.msg_queue.put(("log", f"CSV write error: {e}"))

    def read_serial_lines(self):
        lines = []
        if not self.ser or not self.ser.is_open:
            return lines

        try:
            n = self.ser.in_waiting
            if n > 0:
                data = self.ser.read(n).decode("ascii", errors="ignore")
                if data:
                    self.rx_buffer += data.replace("\r", "")
                    while "\n" in self.rx_buffer:
                        line, self.rx_buffer = self.rx_buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            lines.append(line)
        except Exception:
            pass

        return lines

    def process_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()

                if kind == "log":
                    self.log_insert(payload)

                elif kind == "status":
                    self.status_var.set(payload)

                elif kind == "pressure":
                    self.last_pressure_bar = payload
                    self.update_pressure_display()

                elif kind == "plot_update":
                    self.update_live_plot()
                
                elif kind == "target_time":
                    self.target_time_var.set(payload)

                elif kind == "worker_done":
                    self.worker = None

        except queue.Empty:
            pass

        self.root.after(50, self.process_queue)

    def get_rows_snapshot(self):
        with self.rows_lock:
            return list(self.rows)

    def update_live_plot(self):
        rows = self.get_rows_snapshot()
        self.live_ax.set_ylabel(f"Druck [{self.current_unit_text()}]")

        if not rows:
            self.live_line.set_data([], [])
            self.live_ax.relim()
            self.live_ax.autoscale_view()
            self.live_canvas.draw_idle()
            return

        t0 = rows[0]["t_ms"]
        xs = [(r["t_ms"] - t0) / 1000.0 for r in rows]
        ys = [self.bar_to_display_value(r["bar"]) for r in rows]

        self.live_line.set_data(xs, ys)
        self.live_ax.relim()
        self.live_ax.autoscale_view()
        self.live_canvas.draw_idle()

    def save_plot(self, rows, plot_path):
        if not rows:
            return

        fig = Figure(figsize=(10, 5), dpi=100)
        ax = fig.add_subplot(111)

        pattern_order = []
        for r in rows:
            if r["pattern"] not in pattern_order:
                pattern_order.append(r["pattern"])

        offset_s = 0.0
        gap_s = 0.2

        for pattern in pattern_order:
            pattern_rows = [r for r in rows if r["pattern"] == pattern]
            if not pattern_rows:
                continue

            t0 = pattern_rows[0]["t_ms"]
            xs = [(r["t_ms"] - t0) / 1000.0 + offset_s for r in pattern_rows]
            ys = [self.bar_to_display_value(r["bar"]) for r in pattern_rows]

            ax.plot(xs, ys, label=pattern)

            duration_s = (pattern_rows[-1]["t_ms"] - t0) / 1000.0
            offset_s += duration_s + gap_s

        ax.set_xlabel("Zeit [s]")
        ax.set_ylabel(f"Druck [{self.current_unit_text()}]")
        ax.set_title("Druckverlauf")
        ax.grid(True)
        ax.legend()

        fig.savefig(plot_path, bbox_inches="tight")

    # ------------------------------------------------------------
    # Sonstiges
    # ------------------------------------------------------------
    def log_insert(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def on_close(self):
        try:
            self.stop_event.set()
            if self.ser and self.ser.is_open:
                self.send_line("STOP")
                time.sleep(0.1)
                self.ser.close()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = CuffApp(root)
    root.mainloop()