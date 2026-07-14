import sys, os
import json
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import serial
import serial.tools.list_ports
import pymcprotocol

class PLC:
    def __init__(self, plc_ip, plc_port):
        self.plc_ip = plc_ip
        self.plc_port = int(plc_port)
        self.pymc3e = pymcprotocol.Type3E()
        self.pymc3e.setaccessopt()
        self.pymc3e.soc_timeout = 2.0 
        
    def connect(self):
        try:
            # Chỉ đóng socket cũ nếu thuộc tính nội bộ _sock thực sự tồn tại
            if hasattr(self.pymc3e, '_sock') and self.pymc3e._sock is not None:
                try:
                    self.pymc3e.close()
                except:
                    pass
            
            self.pymc3e.connect(self.plc_ip, self.plc_port)
            self.pymc3e.setaccessopt(commtype="binary", timer_sec=2)
            return True
        except:
            return False
            
    def convert_words_to_string(self, word_values, truncate_val=0):
        result = ''
        for num in word_values:
            high = (num >> 8) & 0xFF
            low = num & 0xFF
            result += chr(low) + chr(high)
        clean_str = result.replace('\x00', '').strip()
        
        try:
            val = int(truncate_val)
            if val > 0:
                return clean_str[val:]
            elif val < 0:
                return clean_str[:val]
        except:
            pass
        return clean_str


class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PLC to Serial Dashboard Pro")
        self.root.geometry("1000x560")
        self.root.configure(bg="#1e1e1e")

        if getattr(sys, 'frozen', False):
            self.root.iconbitmap(sys.executable)
        else:
            icon_path = os.path.abspath("app_icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        
        self.is_running = False
        self.plc = None
        self.ser = None
        
        # Biến cờ chống spam thông báo lỗi
        self.err_spam_flags = {"plc": False, "ser": False, "runtime": False}
        
        # Đường dẫn AppData ẩn
        self.appdata_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), "PLC_Serial_App")
        self.config_file = os.path.join(self.appdata_dir, "config.json")

        self.bg_dark = "#1e1e1e"
        self.bg_panel = "#2d2d2d"
        self.fg_light = "#e0e0e0"
        self.accent_blue = "#007acc"

        self.setup_dark_styles()

        # =========================================================================
        # LAYOUT BÊN TRÁI (LOGS / PROGRESS BAR)
        # =========================================================================
        frame_left = tk.Frame(root, bg=self.bg_dark)
        frame_left.pack(side="left", fill="both", expand=True, padx=(15, 7), pady=15)
        
        frame_log = tk.LabelFrame(frame_left, text=" Nhật ký rút gọn (Max 20 dòng) ", fg=self.fg_light, bg=self.bg_panel, font=("Arial", 10, "bold"), padx=5, pady=5)
        frame_log.pack(fill="both", expand=True, pady=(0, 10))
        
        scrollbar = tk.Scrollbar(frame_log, bg=self.bg_panel)
        scrollbar.pack(side="right", fill="y")
        
        self.txt_log = tk.Text(frame_log, height=18, bg="#121212", fg="#a9b7c6", insertbackground="white", yscrollcommand=scrollbar.set, font=("Courier New", 9))
        self.txt_log.pack(fill="both", expand=True)
        scrollbar.config(command=self.txt_log.yview)

        self.txt_log.tag_config("INFO", foreground="#4CAF50")
        self.txt_log.tag_config("WARN", foreground="#FFC107")
        self.txt_log.tag_config("ERROR", foreground="#F44336")
        self.txt_log.tag_config("NORMAL", foreground="#A9B7C6")

        self.progress = ttk.Progressbar(frame_left, orient="horizontal", mode="determinate", style="Dark.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=2)

        # =========================================================================
        # LAYOUT BÊN PHẢI (SETTINGS / CONTROL)
        # =========================================================================
        frame_right = tk.Frame(root, bg=self.bg_dark, width=410)
        frame_right.pack(side="right", fill="y", padx=(7, 15), pady=15)
        frame_right.pack_propagate(False)

        # 1. Cấu hình hệ thống kết nối
        frame_sys = tk.LabelFrame(frame_right, text=" Cấu hình kết nối & Sườn bắt tay ", fg=self.fg_light, bg=self.bg_panel, font=("Arial", 10, "bold"), padx=10, pady=6)
        frame_sys.pack(fill="x", pady=(0, 10))
        
        self.create_label_entry(frame_sys, "IP PLC:", "192.168.3.10", 0, 0, "ent_ip", width=14)
        self.create_label_entry(frame_sys, "Port PLC:", "5040", 0, 2, "ent_port", width=6)
        
        tk.Label(frame_sys, text="Cổng COM:", fg=self.fg_light, bg=self.bg_panel).grid(row=1, column=0, sticky="w", pady=4, padx=2)
        self.cb_com = ttk.Combobox(frame_sys, width=12, style="Dark.TCombobox")
        self.cb_com.grid(row=1, column=1, padx=5, pady=4, sticky="w")
        self.refresh_com_ports()

        tk.Label(frame_sys, text="Baudrate:", fg=self.fg_light, bg=self.bg_panel).grid(row=1, column=2, sticky="w", pady=4)
        self.cb_baud = ttk.Combobox(frame_sys, values=["9600", "19200", "38400", "115200"], width=5, style="Dark.TCombobox")
        self.cb_baud.set("9600")
        self.cb_baud.grid(row=1, column=3, padx=5, pady=4)

        self.create_label_entry(frame_sys, "Bit Trigger:", "M8010", 2, 0, "ent_bit_trigger", width=14)
        self.create_label_entry(frame_sys, "Bit Complete:", "M8011", 2, 2, "ent_bit_complete", width=6)

        # 2. Cấu hình thanh ghi D co giãn động mở rộng
        self.frame_d_reg = tk.LabelFrame(frame_right, text=" Cấu hình thanh ghi dữ liệu (D) ", fg=self.fg_light, bg=self.bg_panel, font=("Arial", 10, "bold"), padx=10, pady=6)
        self.frame_d_reg.pack(fill="both", expand=True, pady=(0, 10))

        tk.Label(self.frame_d_reg, text="Dòng", fg="#888888", bg=self.bg_panel, font=("Arial", 8, "bold")).grid(row=0, column=0, pady=2)
        tk.Label(self.frame_d_reg, text="Thanh ghi", fg="#888888", bg=self.bg_panel, font=("Arial", 8, "bold")).grid(row=0, column=1, pady=2)
        tk.Label(self.frame_d_reg, text="Size", fg="#888888", bg=self.bg_panel, font=("Arial", 8, "bold")).grid(row=0, column=2, pady=2)
        tk.Label(self.frame_d_reg, text="Truncate (+/-)", fg="#888888", bg=self.bg_panel, font=("Arial", 8, "bold")).grid(row=0, column=3, pady=2)

        self.d_configs = []
        self.default_d_rows = [
            {"reg": "D8310", "size": "15", "trunc": "0"},
            {"reg": "D8326", "size": "6",  "trunc": "2"},
            {"reg": "D8332", "size": "4",  "trunc": "0"},
            {"reg": "D8336", "size": "2",  "trunc": "0"}
        ]
        
        self.load_config()

        frame_d_buttons = tk.Frame(self.frame_d_reg, bg=self.bg_panel)
        frame_d_buttons.grid(row=99, column=0, columnspan=4, sticky="ew", pady=(5, 0))
        
        self.btn_add_d = tk.Button(frame_d_buttons, text=" ➕ Thêm hàng ghi D ", bg="#007acc", fg="white", font=("Arial", 8, "bold"), relief="flat", padx=10, command=self.add_d_row)
        self.btn_add_d.pack(side="left", padx=5)
        
        self.btn_remove_d = tk.Button(frame_d_buttons, text=" ➖ Xóa hàng cuối ", bg="#555555", fg="white", font=("Arial", 8, "bold"), relief="flat", padx=10, command=self.remove_last_d_row)
        self.btn_remove_d.pack(side="left", padx=5)

        # 3. Panel Điều khiển & Đèn LED
        frame_control = tk.Frame(frame_right, bg=self.bg_dark)
        frame_control.pack(fill="x", side="bottom")

        frame_leds = tk.Frame(frame_control, bg=self.bg_dark)
        frame_leds.pack(fill="x", pady=(0, 8))
        
        tk.Label(frame_leds, text="PLC:", fg=self.fg_light, bg=self.bg_dark, font=("Arial", 9)).pack(side="left", padx=(5, 2))
        self.canvas_plc_led = tk.Canvas(frame_leds, width=14, height=14, bg=self.bg_dark, highlightthickness=0)
        self.canvas_plc_led.pack(side="left", padx=(0, 25))
        self.plc_led = self.canvas_plc_led.create_oval(2, 2, 12, 12, fill="#555555")
        
        tk.Label(frame_leds, text="Serial:", fg=self.fg_light, bg=self.bg_dark, font=("Arial", 9)).pack(side="left", padx=2)
        self.canvas_ser_led = tk.Canvas(frame_leds, width=14, height=14, bg=self.bg_dark, highlightthickness=0)
        self.canvas_ser_led.pack(side="left")
        self.ser_led = self.canvas_ser_led.create_oval(2, 2, 12, 12, fill="#555555")

        self.lbl_status = tk.Label(frame_leds, text="Đang khởi động...", fg="orange", bg=self.bg_dark, font=("Arial", 9, "bold"))
        self.lbl_status.pack(side="right", padx=5)

        self.btn_toggle = tk.Button(frame_control, text="KẾT NỐI & GIÁM SÁT", bg="#4CAF50", fg="white", font=("Arial", 11, "bold"), relief="flat", activebackground="#45a049", pady=10, command=self.handle_toggle_click)
        self.btn_toggle.pack(fill="x")
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.after(100, self.toggle_monitoring)

    def setup_dark_styles(self):
        style = ttk.Style()
        style.theme_use('default')
        style.configure("Dark.Horizontal.TProgressbar", thickness=8, troughcolor="#2d2d2d", background=self.accent_blue, bordercolor="#2d2d2d")
        style.configure("Dark.TCombobox", arrowcolor=self.fg_light, fieldbackground="#1e1e1e", background="#2d2d2d", foreground=self.fg_light)
        style.map("Dark.TCombobox", fieldbackground=[('readonly', '#1e1e1e')], foreground=[('readonly', self.fg_light)])

    def create_label_entry(self, parent, label_text, default_val, row, col, attr_name, width=12):
        tk.Label(parent, text=label_text, fg=self.fg_light, bg=self.bg_panel).grid(row=row, column=col, sticky="w", pady=4, padx=2)
        ent = tk.Entry(parent, bg="#1e1e1e", fg=self.fg_light, insertbackground="white", width=width, bd=1, relief="flat")
        ent.grid(row=row, column=col+1, padx=5, pady=4, sticky="w")
        setattr(self, attr_name, ent)

    def refresh_com_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        if not ports:
            ports = ["COM15"]
        self.cb_com['values'] = ports
        if self.cb_com.get() not in ports:
            self.cb_com.set(ports[0])

    def add_d_row(self, reg_val="", size_val="", trunc_val=""):
        current_rows = len(self.d_configs)
        if current_rows >= 10:
            return
            
        row_idx = current_rows + 1
        lbl = tk.Label(self.frame_d_reg, text=f"Dòng {row_idx}", fg=self.fg_light, bg=self.bg_panel)
        lbl.grid(row=row_idx, column=0, padx=2, pady=4)
        
        ent_reg = tk.Entry(self.frame_d_reg, bg="#1e1e1e", fg=self.fg_light, insertbackground="white", width=10, bd=1, relief="flat")
        ent_reg.insert(0, reg_val)
        ent_reg.grid(row=row_idx, column=1, padx=4, pady=4)
        
        ent_size = tk.Entry(self.frame_d_reg, bg="#1e1e1e", fg=self.fg_light, insertbackground="white", width=6, bd=1, relief="flat", justify="center")
        ent_size.insert(0, size_val)
        ent_size.grid(row=row_idx, column=2, padx=4, pady=4)
        
        ent_trunc = tk.Entry(self.frame_d_reg, bg="#1e1e1e", fg=self.fg_light, insertbackground="white", width=8, bd=1, relief="flat", justify="center")
        ent_trunc.insert(0, trunc_val)
        ent_trunc.grid(row=row_idx, column=3, padx=4, pady=4)
        
        self.d_configs.append({"lbl": lbl, "reg": ent_reg, "size": ent_size, "trunc": ent_trunc})

    def remove_last_d_row(self):
        if len(self.d_configs) <= 1:
            return
        last_row = self.d_configs.pop()
        last_row["lbl"].destroy()
        last_row["reg"].destroy()
        last_row["size"].destroy()
        last_row["trunc"].destroy()

    def set_led(self, led_obj, canvas_obj, color):
        canvas_obj.itemconfig(led_obj, fill=color)

    def log(self, message, level="NORMAL"):
        current_time = time.strftime("[%H:%M:%S]")
        full_msg = f"{current_time} {message}\n"
        
        current_lines = int(self.txt_log.index('end-1c').split('.')[0])
        if current_lines >= 20:
            self.txt_log.delete("1.0", "2.0")
            
        self.txt_log.insert(tk.END, full_msg, level)
        self.txt_log.see(tk.END)

    def load_config(self):
        self.ent_ip.insert(0, "192.168.3.10")
        self.ent_port.insert(0, "5040")
        self.cb_com.set("COM15")
        self.cb_baud.set("9600")
        self.ent_bit_trigger.insert(0, "M8010")
        self.ent_bit_complete.insert(0, "M8011")

        target_rows = self.default_d_rows
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.ent_ip.delete(0, tk.END); self.ent_ip.insert(0, config.get("ip", "192.168.3.10"))
                    self.ent_port.delete(0, tk.END); self.ent_port.insert(0, config.get("port", "5040"))
                    self.refresh_com_ports()
                    self.cb_com.set(config.get("com", "COM15"))
                    self.cb_baud.set(config.get("baud", "9600"))
                    self.ent_bit_trigger.delete(0, tk.END); self.ent_bit_trigger.insert(0, config.get("bit_trigger", "M8010"))
                    self.ent_bit_complete.delete(0, tk.END); self.ent_bit_complete.insert(0, config.get("bit_complete", "M8011"))
                    if "d_regs" in config:
                        target_rows = config["d_regs"]
            except:
                pass
                
        for row in target_rows:
            self.add_d_row(row.get("reg", ""), row.get("size", ""), row.get("trunc", "0"))

    def save_config(self):
        d_regs_data = []
        for row in self.d_configs:
            d_regs_data.append({
                "reg": row["reg"].get().strip().upper(),
                "size": row["size"].get().strip(),
                "trunc": row["trunc"].get().strip()
            })

        config = {
            "ip": self.ent_ip.get().strip(),
            "port": self.ent_port.get().strip(),
            "com": self.cb_com.get().strip(),
            "baud": self.cb_baud.get(),
            "bit_trigger": self.ent_bit_trigger.get().strip().upper(),
            "bit_complete": self.ent_bit_complete.get().strip().upper(),
            "d_regs": d_regs_data
        }
        try:
            if not os.path.exists(self.appdata_dir):
                os.makedirs(self.appdata_dir)
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Không thể lưu file cấu hình: {e}")

    def handle_toggle_click(self):
        if self.is_running:
            self.ask_admin_password()
        else:
            self.toggle_monitoring()

    def ask_admin_password(self):
        popup = tk.Toplevel(self.root)
        popup.title("Xác thực hệ thống")
        popup.geometry("320x150")
        popup.configure(bg=self.bg_panel)
        popup.resizable(False, False)
        
        popup.transient(self.root)
        popup.grab_set()
        
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 160
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 75
        popup.geometry(f"+{x}+{y}")

        tk.Label(popup, text="Yêu cầu quyền Admin để thay đổi cấu hình:", fg=self.fg_light, bg=self.bg_panel, font=("Arial", 10)).pack(pady=(15, 5))
        
        ent_pass = tk.Entry(popup, bg="#1e1e1e", fg="white", font=("Arial", 11), show="*", insertbackground="white", width=22, bd=1, relief="flat")
        ent_pass.pack(pady=5)
        ent_pass.focus_set()

        def validate():
            if ent_pass.get() == "admin321":
                popup.destroy()
                self.log("🔑 Đã dừng để chỉnh sửa thông số.", "INFO")
                self.toggle_monitoring()
            else:
                messagebox.showerror("Sai mật khẩu", "Mật khẩu Admin không chính xác!", parent=popup)
                ent_pass.delete(0, tk.END)

        btn_frame = tk.Frame(popup, bg=self.bg_panel)
        btn_frame.pack(pady=15)

        tk.Button(btn_frame, text="Xác nhận", bg=self.accent_blue, fg="white", font=("Arial", 9, "bold"), relief="flat", padx=15, pady=4, command=validate).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Hủy", bg="#555555", fg="white", font=("Arial", 9), relief="flat", padx=15, pady=4, command=popup.destroy).pack(side="left", padx=5)
        
        popup.bind('<Return>', lambda event: validate())

    def toggle_monitoring(self):
        if not self.is_running:
            self.refresh_com_ports()
            self.ip = self.ent_ip.get().strip()
            self.port = self.ent_port.get().strip()
            self.com = self.cb_com.get().strip()
            self.baud = self.cb_baud.get()
            self.bit_trigger = self.ent_bit_trigger.get().strip().upper()
            self.bit_complete = self.ent_bit_complete.get().strip().upper()
            
            self.active_d_configs = []
            for row in self.d_configs:
                self.active_d_configs.append({
                    "reg": row["reg"].get().strip().upper(),
                    "size": int(row["size"].get().strip() or 0),
                    "trunc": int(row["trunc"].get().strip() or 0)
                })

            self.save_config()
            
            self.is_running = True
            self.btn_toggle.config(text="DỪNG GIÁM SÁT", bg="#d32f2f", activebackground="#b71c1c")
            self.lbl_status.config(text="ĐANG KẾT NỐI...", fg="orange")
            
            self.set_led(self.plc_led, self.canvas_plc_led, "yellow")
            self.set_led(self.ser_led, self.canvas_ser_led, "yellow")
            
            self.set_config_state("disabled")
            
            # Khởi tạo instance PLC duy nhất tại đây khi nhấn nút bắt đầu
            self.plc = PLC(self.ip, self.port)
            
            self.worker_thread = threading.Thread(target=self.plc_serial_worker, daemon=True)
            self.worker_thread.start()
        else:
            self.is_running = False
            self.btn_toggle.config(text="KẾT NỐI & GIÁM SÁT", bg="#4CAF50", activebackground="#45a049")
            self.lbl_status.config(text="Đang dừng", fg="#555555")
            self.set_led(self.plc_led, self.canvas_plc_led, "#555555")
            self.set_led(self.ser_led, self.canvas_ser_led, "#555555")
            
            self.set_config_state("normal")
            self.progress['value'] = 0
            self.err_spam_flags = {"plc": False, "ser": False, "runtime": False}

    def set_config_state(self, state_str):
        self.ent_ip.config(state=state_str)
        self.ent_port.config(state=state_str)
        self.cb_com.config(state=state_str)
        self.cb_baud.config(state=state_str)
        self.ent_bit_trigger.config(state=state_str)
        self.ent_bit_complete.config(state=state_str)
        self.btn_add_d.config(state=state_str)
        self.btn_remove_d.config(state=state_str)
        for row in self.d_configs:
            row["reg"].config(state=state_str)
            row["size"].config(state=state_str)
            row["trunc"].config(state=state_str)

    # ⭐ ĐÃ SỬA: Loại bỏ cơ chế khởi tạo lại liên tục đối tượng PLC, check hasattr để không bao giờ bị dính lỗi nội bộ thư viện
    def plc_serial_worker(self):
        last_trigger_state = 0
        total_lines = len(self.active_d_configs)
        
        while self.is_running:
            connected_plc_step = False
            connected_ser_step = False
            
            # --- Bước 1: Kết nối PLC qua hàm nội bộ an toàn ---
            if self.plc.connect():
                if self.err_spam_flags["plc"]:
                    self.log("✅ PLC đã kết nối lại thành công!", "INFO")
                else:
                    self.log("✅ PLC đã kết nối thành công!", "INFO")
                self.set_led(self.plc_led, self.canvas_plc_led, "#4CAF50")
                self.err_spam_flags["plc"] = False
                connected_plc_step = True
            else:
                if not self.err_spam_flags["plc"]:
                    self.log("❌ Lỗi: Kết nối PLC thất bại! Đang tự động kết nối lại...", "ERROR")
                    self.err_spam_flags["plc"] = True
                self.set_led(self.plc_led, self.canvas_plc_led, "#f44336")

            # --- Bước 2: Kết nối Cổng Serial (chỉ thử khi PLC thông) ---
            if connected_plc_step:
                try:
                    if self.ser and self.ser.is_open:
                        try: self.ser.close()
                        except: pass
                    self.ser = serial.Serial(port=self.com, baudrate=int(self.baud), parity=serial.PARITY_EVEN, timeout=2)
                    time.sleep(0.3)
                    self.set_led(self.ser_led, self.canvas_ser_led, "#4CAF50")
                    self.err_spam_flags["ser"] = False
                    connected_ser_step = True
                except:
                    if not self.err_spam_flags["ser"]:
                        self.log(f"❌ Lỗi: Mở cổng Serial {self.com} thất bại! Đang thử lại...", "ERROR")
                        self.err_spam_flags["ser"] = True
                    self.set_led(self.ser_led, self.canvas_ser_led, "#f44336")

            # Nếu bất kỳ kết nối nào lỗi, chuyển trạng thái UI chờ 3 giây rồi chạy lại vòng lặp
            if not (connected_plc_step and connected_ser_step):
                self.lbl_status.config(text="ĐANG KẾT NỐI LẠI...", fg="orange")
                for _ in range(30):
                    if not self.is_running: 
                        break
                    time.sleep(0.1)
                continue

            # --- Bước 3: Vòng lặp giám sát Runtime dữ liệu ---
            self.lbl_status.config(text=f"QUÉT {self.bit_trigger}...", fg="#4CAF50")
            self.err_spam_flags["runtime"] = False
            
            while self.is_running:
                try:
                    current_trigger_state = self.plc.pymc3e.batchread_bitunits(headdevice=self.bit_trigger, readsize=1)[0]
                    
                    if last_trigger_state == 0 and current_trigger_state == 1:
                        self.log(f"🔔 Phát hiện xung {self.bit_trigger} (Bắt đầu truyền)", "WARN")
                        self.progress['value'] = 0
                        
                        lines = []
                        for row_conf in self.active_d_configs:
                            words_data = self.plc.pymc3e.batchread_wordunits(headdevice=row_conf["reg"], readsize=row_conf["size"])
                            parsed_str = self.plc.convert_words_to_string(words_data, truncate_val=row_conf["trunc"])
                            lines.append(parsed_str)
                        
                        all_lines_success = True
                        
                        for i, line in enumerate(lines, start=1):
                            single_line_data = line + "\r"
                            self.ser.write(single_line_data.encode('utf-8'))
                            self.ser.flush()
                            
                            response_bytes = self.ser.read(1)
                            if response_bytes == b'\x06':
                                self.progress['value'] = (i / total_lines) * 100
                                self.root.update_idletasks()
                                time.sleep(0.05)
                            else:
                                all_lines_success = False
                                if response_bytes:
                                    self.log(f"❌ Lỗi dòng {i}: Byte phản hồi lạ ({response_bytes.hex().upper()})", "ERROR")
                                else:
                                    self.log(f"❌ Lỗi dòng {i}: Thiết bị không phản hồi (Timeout)", "ERROR")
                                break
                        
                        if all_lines_success:
                            self.log(f"🎉 Thành công: Đã truyền đủ {total_lines} dòng & kích hoạt {self.bit_complete}.", "INFO")
                            self.plc.pymc3e.batchwrite_bitunits(headdevice=self.bit_complete, values=[1])
                        else:
                            self.progress['value'] = 0
                            
                        time.sleep(0.150)
                        
                    last_trigger_state = current_trigger_state
                    time.sleep(0.05)
                    
                except Exception as e:
                    if not self.err_spam_flags["runtime"]:
                        self.log(f"⚠️ Mất kết nối thiết bị khi đang quét! Đang kích hoạt kết nối lại...", "ERROR")
                        self.err_spam_flags["runtime"] = True
                    self.set_led(self.plc_led, self.canvas_plc_led, "#f44336")
                    break 
                    
        # Giải phóng an toàn khi nhấn Dừng hẳn từ giao diện
        if self.plc: 
            if hasattr(self.plc.pymc3e, '_sock') and self.plc.pymc3e._sock is not None:
                try: self.plc.pymc3e.close()
                except: pass
        if self.ser and self.ser.is_open: 
            try: self.ser.close()
            except: pass
        self.log("🔌 Đã ngắt kết nối phần cứng an toàn.")

    def on_closing(self):
        self.is_running = False
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AppGUI(root)
    root.mainloop()