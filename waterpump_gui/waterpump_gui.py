import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import serial
import serial.tools.list_ports
import threading
import time
import csv
from datetime import datetime

BAUD = 19200

DRY_THRESHOLD = 14000
CONTACT_BREAK_THRESHOLD = 14100
WORKING_MAX = 15500


class WaterPumpGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Water Pump Controller")
        self.root.resizable(False, False)

        self.ser = None
        self.serial_lock = threading.Lock()

        self.monitoring = False
        self.monitor_thread = None
        self.log = []  # list of (elapsed_s, impedance)
        self.monitor_start = None

        self._build_ui()
        self._refresh_ports()

    # ------------------------------------------------------------------ build

    def _build_ui(self):
        pad = dict(padx=6, pady=4)

        # --- Connection ---
        conn_frame = ttk.LabelFrame(self.root, text="Connection")
        conn_frame.grid(row=0, column=0, columnspan=2, sticky="ew", **pad)

        ttk.Label(conn_frame, text="COM Port:").grid(row=0, column=0, **pad)
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(conn_frame, textvariable=self.port_var, width=12, state="readonly")
        self.port_cb.grid(row=0, column=1, **pad)

        ttk.Button(conn_frame, text="Refresh", command=self._refresh_ports).grid(row=0, column=2, **pad)
        self.btn_connect = ttk.Button(conn_frame, text="Connect", command=self._toggle_connect)
        self.btn_connect.grid(row=0, column=3, **pad)

        self.lbl_status = ttk.Label(conn_frame, text="Disconnected", foreground="red")
        self.lbl_status.grid(row=0, column=4, **pad)

        # --- Impedance display ---
        imp_frame = ttk.LabelFrame(self.root, text="Impedance")
        imp_frame.grid(row=1, column=0, columnspan=2, sticky="ew", **pad)

        self.lbl_impedance = ttk.Label(imp_frame, text="---", font=("Courier", 28, "bold"))
        self.lbl_impedance.grid(row=0, column=0, padx=12, pady=6)

        self.lbl_imp_state = ttk.Label(imp_frame, text="", font=("Courier", 11))
        self.lbl_imp_state.grid(row=0, column=1, padx=8)

        ttk.Button(imp_frame, text="Read once", command=self._read_once).grid(row=0, column=2, **pad)

        # --- Control ---
        ctrl_frame = ttk.LabelFrame(self.root, text="Control")
        ctrl_frame.grid(row=2, column=0, sticky="nsew", **pad)

        ttk.Button(ctrl_frame, text="Check connection (37045)", width=26,
                   command=lambda: self._send_cmd("37045")).grid(row=0, column=0, **pad)
        ttk.Button(ctrl_frame, text="Check status (37004)", width=26,
                   command=lambda: self._send_cmd("37004")).grid(row=1, column=0, **pad)

        ttk.Separator(ctrl_frame, orient="horizontal").grid(row=2, column=0, sticky="ew", pady=4)

        ttk.Button(ctrl_frame, text="INIT (37020)", width=26,
                   command=lambda: self._send_cmd("37020")).grid(row=3, column=0, **pad)
        ttk.Button(ctrl_frame, text="STOP (37021)", width=26,
                   command=lambda: self._send_cmd("37021")).grid(row=4, column=0, **pad)

        ttk.Separator(ctrl_frame, orient="horizontal").grid(row=5, column=0, sticky="ew", pady=4)

        ttk.Label(ctrl_frame, text="Auto mode:").grid(row=6, column=0, sticky="w", **pad)
        btn_auto_frame = ttk.Frame(ctrl_frame)
        btn_auto_frame.grid(row=7, column=0, **pad)
        ttk.Button(btn_auto_frame, text="ON  (37042 1)",
                   command=lambda: self._send_cmd("37042 1")).pack(side="left", padx=2)
        ttk.Button(btn_auto_frame, text="OFF (37042 0)",
                   command=lambda: self._send_cmd("37042 0")).pack(side="left", padx=2)
        ttk.Button(btn_auto_frame, text="Read (37043)",
                   command=lambda: self._send_cmd("37043")).pack(side="left", padx=2)

        ttk.Separator(ctrl_frame, orient="horizontal").grid(row=8, column=0, sticky="ew", pady=4)

        ttk.Label(ctrl_frame, text="Target impedance:").grid(row=9, column=0, sticky="w", **pad)
        target_frame = ttk.Frame(ctrl_frame)
        target_frame.grid(row=10, column=0, **pad)
        self.target_var = tk.StringVar(value="15450")
        ttk.Entry(target_frame, textvariable=self.target_var, width=8).pack(side="left", padx=2)
        ttk.Button(target_frame, text="Set target (37040)",
                   command=self._set_target).pack(side="left", padx=2)
        ttk.Button(target_frame, text="Read (37041)",
                   command=lambda: self._send_cmd("37041")).pack(side="left", padx=2)

        ttk.Separator(ctrl_frame, orient="horizontal").grid(row=11, column=0, sticky="ew", pady=4)

        ttk.Button(ctrl_frame, text="Gradual Fill", width=26,
                   command=self._gradual_fill).grid(row=12, column=0, **pad)
        ttk.Button(ctrl_frame, text="Safe Drain", width=26,
                   command=self._safe_drain).grid(row=13, column=0, **pad)

        # --- Monitoring ---
        mon_frame = ttk.LabelFrame(self.root, text="Monitoring")
        mon_frame.grid(row=2, column=1, sticky="nsew", **pad)

        ttk.Label(mon_frame, text="Duration (hours):").grid(row=0, column=0, sticky="w", **pad)
        self.duration_var = tk.StringVar(value="24")
        ttk.Entry(mon_frame, textvariable=self.duration_var, width=6).grid(row=0, column=1, **pad)

        ttk.Label(mon_frame, text="Interval (seconds):").grid(row=1, column=0, sticky="w", **pad)
        self.interval_var = tk.StringVar(value="60")
        ttk.Entry(mon_frame, textvariable=self.interval_var, width=6).grid(row=1, column=1, **pad)

        self.btn_monitor = ttk.Button(mon_frame, text="Start Monitoring", command=self._toggle_monitoring)
        self.btn_monitor.grid(row=2, column=0, columnspan=2, **pad)

        self.lbl_mon_status = ttk.Label(mon_frame, text="Idle")
        self.lbl_mon_status.grid(row=3, column=0, columnspan=2, **pad)

        self.lbl_mon_points = ttk.Label(mon_frame, text="Points: 0")
        self.lbl_mon_points.grid(row=4, column=0, columnspan=2, **pad)

        ttk.Separator(mon_frame, orient="horizontal").grid(row=5, column=0, columnspan=2, sticky="ew", pady=4)

        ttk.Button(mon_frame, text="Save log to CSV", command=self._save_csv).grid(
            row=6, column=0, columnspan=2, **pad)

        # --- Log ---
        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.grid(row=3, column=0, columnspan=2, sticky="ew", **pad)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, width=90,
                                                   state="disabled", font=("Courier", 9))
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

        ttk.Button(log_frame, text="Clear log", command=self._clear_log).pack(anchor="e", padx=4, pady=2)

    # ---------------------------------------------------------------- serial

    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb["values"] = ports
        if ports:
            self.port_var.set(ports[0])

    def _toggle_connect(self):
        if self.ser and self.ser.is_open:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        port = self.port_var.get()
        if not port:
            messagebox.showerror("Error", "Select a COM port first.")
            return
        try:
            self.ser = serial.Serial(port, BAUD, timeout=1)
            time.sleep(0.5)
            self.lbl_status.config(text=f"Connected ({port})", foreground="green")
            self.btn_connect.config(text="Disconnect")
            self._log(f"Connected to {port} @ {BAUD} baud")
        except Exception as e:
            messagebox.showerror("Connection error", str(e))

    def _disconnect(self):
        if self.monitoring:
            self._stop_monitoring()
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.lbl_status.config(text="Disconnected", foreground="red")
        self.btn_connect.config(text="Connect")
        self._log("Disconnected")

    def _send_cmd(self, cmd):
        if not self._check_connected():
            return None
        with self.serial_lock:
            try:
                self.ser.reset_input_buffer()
                self.ser.write((cmd + "\r").encode())
                # wait up to 1s for data to arrive
                deadline = time.time() + 1.0
                while self.ser.in_waiting == 0 and time.time() < deadline:
                    time.sleep(0.05)
                time.sleep(0.1)  # let the full response land
                resp = self.ser.read_all().decode(errors="ignore").strip()
                self._log(f">>> {cmd}")
                if resp:
                    self._log(f"    {resp}")
                else:
                    self._log(f"    (no response)")
                return resp
            except Exception as e:
                self._log(f"ERROR: {e}")
                return None

    def _check_connected(self):
        if not self.ser or not self.ser.is_open:
            messagebox.showwarning("Not connected", "Connect to a COM port first.")
            return False
        return True

    # ---------------------------------------------------------------- actions

    def _read_once(self):
        resp = self._send_cmd("37044")
        if resp:
            val = self._parse_impedance(resp)
            if val is not None:
                self._update_impedance_display(val)

    def _parse_impedance(self, resp):
        try:
            return int(resp.split()[1])
        except Exception:
            return None

    def _update_impedance_display(self, val):
        """Must be called from the main thread only."""
        self.lbl_impedance.config(text=str(val))
        if val < DRY_THRESHOLD:
            state, color = "DRY / air risk", "red"
        elif val < CONTACT_BREAK_THRESHOLD:
            state, color = "contact break zone", "orange"
        elif val <= WORKING_MAX:
            state, color = "working range", "green"
        else:
            state, color = "overfill risk", "red"
        self.lbl_imp_state.config(text=state, foreground=color)

    def _set_target(self):
        t = self.target_var.get().strip()
        if not t.isdigit():
            messagebox.showerror("Error", "Target must be an integer.")
            return
        self._send_cmd(f"37040 {t}")

    def _gradual_fill(self):
        if not self._check_connected():
            return
        targets = [15000, 15200, 15450]
        t = self.target_var.get().strip()
        if t.isdigit():
            final = int(t)
            targets = [15000, 15200, final] if final > 15200 else [15000, final]

        def run():
            self._log("--- GRADUAL FILL ---")
            self._send_cmd("37042 1")
            for target in targets:
                self._log(f"Setting target: {target}")
                self._send_cmd(f"37040 {target}")
                for _ in range(15):
                    resp = self._send_cmd("37044")
                    if resp:
                        val = self._parse_impedance(resp)
                        if val is not None:
                            self.root.after(0, lambda v=val: self._update_impedance_display(v))
                            if abs(val - target) < 200:
                                self._log(f"-> Close to {target}")
                                break
                    time.sleep(1)
            self._log("--- GRADUAL FILL DONE ---")

        threading.Thread(target=run, daemon=True).start()

    def _safe_drain(self):
        if not self._check_connected():
            return
        if not messagebox.askyesno("Safe Drain", "Start safe drain procedure?"):
            return

        def run():
            self._log("--- SAFE DRAIN ---")
            self._send_cmd("37040 15000")
            time.sleep(5)
            self._send_cmd("37021")
            time.sleep(1)
            self._send_cmd("37042 0")
            time.sleep(1)

            resp = self._send_cmd("37044")
            val = self._parse_impedance(resp) if resp else None
            if val is not None:
                self.root.after(0, lambda v=val: self._update_impedance_display(v))

            while val is not None and val > CONTACT_BREAK_THRESHOLD:
                self._log("Contact still present — raise objective or remove water manually")
                time.sleep(2)
                resp = self._send_cmd("37044")
                val = self._parse_impedance(resp) if resp else None
                if val is not None:
                    self.root.after(0, lambda v=val: self._update_impedance_display(v))

            self._log("Contact broken — draining")
            self._send_cmd("37030 200")

            for _ in range(30):
                resp = self._send_cmd("37044")
                val = self._parse_impedance(resp) if resp else None
                if val is not None:
                    self.root.after(0, lambda v=val: self._update_impedance_display(v))
                if val is None or val < DRY_THRESHOLD:
                    self._log("Stopping — dry threshold reached")
                    break
                self._send_cmd("37024 -100")
                time.sleep(1)

            self._log("--- SAFE DRAIN DONE ---")

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------ monitoring

    def _toggle_monitoring(self):
        if self.monitoring:
            self._stop_monitoring()
        else:
            self._start_monitoring()

    def _start_monitoring(self):
        if not self._check_connected():
            return
        try:
            duration_h = float(self.duration_var.get())
            interval_s = float(self.interval_var.get())
        except ValueError:
            messagebox.showerror("Error", "Duration and interval must be numbers.")
            return

        self.log = []
        self.monitoring = True
        self.monitor_start = time.time()
        self.btn_monitor.config(text="Stop Monitoring")
        self.lbl_mon_status.config(text="Running...")

        def run():
            duration_s = duration_h * 3600
            while self.monitoring and (time.time() - self.monitor_start) < duration_s:
                resp = self._send_cmd("37044")
                if resp:
                    val = self._parse_impedance(resp)
                    if val is not None:
                        elapsed = time.time() - self.monitor_start
                        self.log.append((elapsed, val))
                        ts = datetime.now().strftime("%H:%M:%S")
                        self._log(f"{ts} | {elapsed/60:.1f} min | {val}")
                        self.root.after(0, lambda v=val: self._update_impedance_display(v))
                        self.root.after(0, lambda n=len(self.log): self.lbl_mon_points.config(text=f"Points: {n}"))
                for _ in range(int(interval_s * 10)):
                    if not self.monitoring:
                        break
                    time.sleep(0.1)
            self.root.after(0, self._monitoring_ended)

        self.monitor_thread = threading.Thread(target=run, daemon=True)
        self.monitor_thread.start()

    def _stop_monitoring(self):
        self.monitoring = False

    def _monitoring_ended(self):
        self.monitoring = False
        self.btn_monitor.config(text="Start Monitoring")
        self.lbl_mon_status.config(text=f"Done — {len(self.log)} points")

    def _save_csv(self):
        if not self.log:
            messagebox.showinfo("No data", "No monitoring data to save.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"waterpump_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if not path:
            return
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time_s", "impedance"])
            writer.writerows(self.log)
        self._log(f"Saved {len(self.log)} rows to {path}")

    # ------------------------------------------------------------------- log

    def _log(self, msg):
        def _insert():
            self.log_text.config(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.root.after(0, _insert)

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    app = WaterPumpGUI(root)
    root.mainloop()
