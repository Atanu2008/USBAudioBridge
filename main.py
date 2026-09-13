import socket
import struct
import threading
import time
import queue
import customtkinter as ctk
import pyaudiowpatch as pyaudio


# ============================================================
# CONFIG
# ============================================================

SERVER_HOST = "0.0.0.0"
SERVER_PORT = 9999

DEFAULT_RATE = 48000
DEFAULT_CHANNELS = 2
DEFAULT_CHUNK = 960       # 20 ms at 48 kHz
DEFAULT_FORMAT = pyaudio.paInt16

APP_TITLE = "USB Audio Bridge"
APP_SIZE = "720x520"


# ============================================================
# AUDIO SERVER
# ============================================================

class AudioServer:

    def __init__(self, log_callback, status_callback, level_callback):
        self.log = log_callback
        self.status = status_callback
        self.level = level_callback

        self.running = False
        self.server_socket = None
        self.audio_thread = None
        self.client_thread = None

        self.client_socket = None
        self.client_address = None

        self.lock = threading.Lock()

        self.sample_rate = DEFAULT_RATE
        self.channels = DEFAULT_CHANNELS
        self.chunk = DEFAULT_CHUNK

        self.pa = None
        self.stream = None

        self.bytes_sent = 0
        self.start_time = None

    # --------------------------------------------------------
    # FIND LOOPBACK DEVICES
    # --------------------------------------------------------

    def get_loopback_devices(self):

        devices = []

        try:
            with pyaudio.PyAudio() as pa:

                wasapi_info = pa.get_host_api_info_by_type(
                    pyaudio.paWASAPI
                )

                default_speakers = pa.get_device_info_by_index(
                    wasapi_info["defaultOutputDevice"]
                )

                for i in range(pa.get_device_count()):

                    device = pa.get_device_info_by_index(i)

                    if not device.get("isLoopbackDevice"):
                        continue

                    # Prefer devices belonging to the default speaker
                    name = device["name"]

                    devices.append({
                        "index": i,
                        "name": name,
                        "channels": int(device.get("maxInputChannels", 2)),
                        "rate": int(device.get("defaultSampleRate", 48000))
                    })

        except Exception as e:
            self.log(f"Audio device scan failed: {e}")

        return devices

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    def start(self, device_index, sample_rate, channels, chunk):

        if self.running:
            return False

        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.chunk = int(chunk)

        try:
            self.pa = pyaudio.PyAudio()

            device_info = self.pa.get_device_info_by_index(device_index)

            self.log(
                f"Selected loopback device: {device_info['name']}"
            )

            self.log(
                f"Audio format: "
                f"{self.sample_rate} Hz / "
                f"{self.channels} ch / "
                f"16-bit"
            )

            self.stream = self.pa.open(
                format=DEFAULT_FORMAT,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.chunk
            )

            self.server_socket = socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM
            )

            self.server_socket.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_REUSEADDR,
                1
            )

            self.server_socket.bind(
                (SERVER_HOST, SERVER_PORT)
            )

            self.server_socket.listen(5)

            self.server_socket.settimeout(1.0)

            self.running = True
            self.start_time = time.time()
            self.bytes_sent = 0

            self.audio_thread = threading.Thread(
                target=self.audio_loop,
                daemon=True
            )

            self.audio_thread.start()

            self.log(
                f"Server listening on "
                f"{SERVER_HOST}:{SERVER_PORT}"
            )

            self.status("WAITING FOR PHONE")

            return True

        except Exception as e:

            self.log(f"START ERROR: {e}")

            self.cleanup()

            return False

    # --------------------------------------------------------
    # AUDIO LOOP
    # --------------------------------------------------------

    def audio_loop(self):

        while self.running:

            # ------------------------------------------------
            # Capture audio
            # ------------------------------------------------

            try:

                data = self.stream.read(
                    self.chunk,
                    exception_on_overflow=False
                )

            except Exception as e:

                self.log(f"Audio capture error: {e}")
                break

            if not data:
                continue

            # ------------------------------------------------
            # Calculate audio level
            # ------------------------------------------------

            try:

                samples = struct.unpack(
                    "<" + "h" * (len(data) // 2),
                    data
                )

                if samples:

                    peak = max(
                        abs(x) for x in samples
                    )

                    level = min(
                        100,
                        (peak / 32768) * 100
                    )

                    self.level(level)

            except Exception:
                pass

            # ------------------------------------------------
            # Accept clients
            # ------------------------------------------------

            if self.client_socket is None:

                try:

                    client, address = (
                        self.server_socket.accept()
                    )

                    client.setsockopt(
                        socket.IPPROTO_TCP,
                        socket.TCP_NODELAY,
                        1
                    )

                    with self.lock:

                        # Close previous client
                        if self.client_socket:
                            try:
                                self.client_socket.close()
                            except Exception:
                                pass

                        self.client_socket = client
                        self.client_address = address

                    self.log(
                        f"Phone connected: {address[0]}:"
                        f"{address[1]}"
                    )

                    self.status("PHONE CONNECTED")

                    # Send stream information first
                    self.send_header(client)

                except socket.timeout:
                    continue

                except Exception as e:

                    if self.running:
                        self.log(
                            f"Client accept error: {e}"
                        )

                    continue

            # ------------------------------------------------
            # Send audio
            # ------------------------------------------------

            if self.client_socket:

                try:

                    # Packet:
                    #
                    # 4 bytes = packet size
                    # N bytes = PCM data
                    #
                    # !I = unsigned 32-bit network order

                    packet = struct.pack(
                        "!I",
                        len(data)
                    ) + data

                    self.client_socket.sendall(packet)

                    self.bytes_sent += len(data)

                except Exception as e:

                    self.log(
                        f"Phone disconnected: {e}"
                    )

                    self.disconnect_client()

        self.status("STOPPED")

    # --------------------------------------------------------
    # STREAM HEADER
    # --------------------------------------------------------

    def send_header(self, client):

        # Magic:
        # AUD1
        #
        # Sample rate: uint32
        # Channels:    uint16
        # Sample size: uint16

        header = struct.pack(
            "!4sIHH",
            b"AUD1",
            self.sample_rate,
            self.channels,
            16
        )

        try:
            client.sendall(header)

        except Exception:
            self.disconnect_client()

    # --------------------------------------------------------
    # DISCONNECT CLIENT
    # --------------------------------------------------------

    def disconnect_client(self):

        with self.lock:

            if self.client_socket:

                try:
                    self.client_socket.shutdown(
                        socket.SHUT_RDWR
                    )
                except Exception:
                    pass

                try:
                    self.client_socket.close()
                except Exception:
                    pass

            self.client_socket = None
            self.client_address = None

        if self.running:
            self.status("WAITING FOR PHONE")

    # --------------------------------------------------------
    # STOP
    # --------------------------------------------------------

    def stop(self):

        if not self.running:
            return

        self.running = False

        self.disconnect_client()

        try:
            if self.server_socket:
                self.server_socket.close()
        except Exception:
            pass

        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
        except Exception:
            pass

        try:
            if self.pa:
                self.pa.terminate()
        except Exception:
            pass

        self.server_socket = None
        self.stream = None
        self.pa = None

        self.status("STOPPED")

        self.log("Server stopped.")

    # --------------------------------------------------------
    # CLEANUP
    # --------------------------------------------------------

    def cleanup(self):

        self.running = False

        try:
            if self.client_socket:
                self.client_socket.close()
        except Exception:
            pass

        try:
            if self.server_socket:
                self.server_socket.close()
        except Exception:
            pass

        try:
            if self.stream:
                self.stream.close()
        except Exception:
            pass

        try:
            if self.pa:
                self.pa.terminate()
        except Exception:
            pass

        self.client_socket = None
        self.server_socket = None
        self.stream = None
        self.pa = None


# ============================================================
# GUI
# ============================================================

class AudioBridgeApp(ctk.CTk):

    def __init__(self):

        super().__init__()

        self.title(APP_TITLE)
        self.geometry(APP_SIZE)
        self.minsize(680, 480)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.server = AudioServer(
            self.log,
            self.set_status,
            self.update_level
        )

        self.devices = []

        self.build_ui()

        self.refresh_devices()

        self.after(
            1000,
            self.update_statistics
        )

        self.protocol(
            "WM_DELETE_WINDOW",
            self.on_close
        )

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------

    def build_ui(self):

        # Main grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------

        header = ctk.CTkFrame(
            self,
            corner_radius=15
        )

        header.grid(
            row=0,
            column=0,
            padx=18,
            pady=(18, 10),
            sticky="ew"
        )

        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="USB Audio Bridge",
            font=ctk.CTkFont(
                size=25,
                weight="bold"
            )
        )

        title.grid(
            row=0,
            column=0,
            padx=20,
            pady=(16, 2),
            sticky="w"
        )

        subtitle = ctk.CTkLabel(
            header,
            text="Windows system audio → USB → Android",
            text_color="gray"
        )

        subtitle.grid(
            row=1,
            column=0,
            padx=20,
            pady=(0, 16),
            sticky="w"
        )

        # ----------------------------------------------------
        # SETTINGS
        # ----------------------------------------------------

        settings = ctk.CTkFrame(
            self,
            corner_radius=15
        )

        settings.grid(
            row=1,
            column=0,
            padx=18,
            pady=8,
            sticky="ew"
        )

        settings.grid_columnconfigure(
            1,
            weight=1
        )

        # Device
        ctk.CTkLabel(
            settings,
            text="Loopback Device"
        ).grid(
            row=0,
            column=0,
            padx=15,
            pady=(15, 7),
            sticky="w"
        )

        self.device_combo = ctk.CTkComboBox(
            settings,
            values=["Scanning..."],
            width=420
        )

        self.device_combo.grid(
            row=0,
            column=1,
            padx=15,
            pady=(15, 7),
            sticky="ew"
        )

        self.refresh_button = ctk.CTkButton(
            settings,
            text="Refresh",
            width=100,
            command=self.refresh_devices
        )

        self.refresh_button.grid(
            row=0,
            column=2,
            padx=15,
            pady=(15, 7)
        )

        # Sample rate
        ctk.CTkLabel(
            settings,
            text="Sample Rate"
        ).grid(
            row=1,
            column=0,
            padx=15,
            pady=7,
            sticky="w"
        )

        self.rate_combo = ctk.CTkComboBox(
            settings,
            values=[
                "44100",
                "48000"
            ]
        )

        self.rate_combo.set("48000")

        self.rate_combo.grid(
            row=1,
            column=1,
            padx=15,
            pady=7,
            sticky="w"
        )

        # Channels
        ctk.CTkLabel(
            settings,
            text="Channels"
        ).grid(
            row=2,
            column=0,
            padx=15,
            pady=(7, 15),
            sticky="w"
        )

        self.channel_combo = ctk.CTkComboBox(
            settings,
            values=[
                "1",
                "2"
            ]
        )

        self.channel_combo.set("2")

        self.channel_combo.grid(
            row=2,
            column=1,
            padx=15,
            pady=(7, 15),
            sticky="w"
        )

        # ----------------------------------------------------
        # STATUS CARD
        # ----------------------------------------------------

        status_frame = ctk.CTkFrame(
            self,
            corner_radius=15
        )

        status_frame.grid(
            row=2,
            column=0,
            padx=18,
            pady=8,
            sticky="ew"
        )

        status_frame.grid_columnconfigure(
            1,
            weight=1
        )

        ctk.CTkLabel(
            status_frame,
            text="STATUS",
            font=ctk.CTkFont(
                size=12,
                weight="bold"
            )
        ).grid(
            row=0,
            column=0,
            padx=(18, 10),
            pady=15
        )

        self.status_label = ctk.CTkLabel(
            status_frame,
            text="STOPPED",
            font=ctk.CTkFont(
                size=15,
                weight="bold"
            )
        )

        self.status_label.grid(
            row=0,
            column=1,
            padx=10,
            pady=15,
            sticky="w"
        )

        self.start_button = ctk.CTkButton(
            status_frame,
            text="START SERVER",
            height=38,
            command=self.start_server
        )

        self.start_button.grid(
            row=0,
            column=2,
            padx=(5, 8),
            pady=10
        )

        self.stop_button = ctk.CTkButton(
            status_frame,
            text="STOP",
            height=38,
            command=self.stop_server,
            state="disabled"
        )

        self.stop_button.grid(
            row=0,
            column=3,
            padx=(5, 15),
            pady=10
        )

        # ----------------------------------------------------
        # LOG + LEVEL
        # ----------------------------------------------------

        bottom = ctk.CTkFrame(
            self,
            corner_radius=15
        )

        bottom.grid(
            row=3,
            column=0,
            padx=18,
            pady=(8, 18),
            sticky="nsew"
        )

        bottom.grid_columnconfigure(
            0,
            weight=1
        )

        bottom.grid_rowconfigure(
            1,
            weight=1
        )

        # Audio meter
        ctk.CTkLabel(
            bottom,
            text="SYSTEM AUDIO LEVEL",
            font=ctk.CTkFont(
                size=12,
                weight="bold"
            )
        ).grid(
            row=0,
            column=0,
            padx=15,
            pady=(15, 5),
            sticky="w"
        )

        self.level_bar = ctk.CTkProgressBar(
            bottom,
            height=18
        )

        self.level_bar.set(0)

        self.level_bar.grid(
            row=0,
            column=0,
            padx=180,
            pady=(15, 5),
            sticky="ew"
        )

        # Log
        self.log_box = ctk.CTkTextbox(
            bottom,
            corner_radius=10
        )

        self.log_box.grid(
            row=1,
            column=0,
            padx=15,
            pady=10,
            sticky="nsew"
        )

        self.log_box.configure(
            state="disabled"
        )

        self.log(
            "Ready. Select a WASAPI loopback device."
        )

    # --------------------------------------------------------
    # DEVICE SCAN
    # --------------------------------------------------------

    def refresh_devices(self):

        self.devices = (
            self.server.get_loopback_devices()
        )

        names = [
            d["name"]
            for d in self.devices
        ]

        if not names:

            names = [
                "No WASAPI loopback device found"
            ]

        self.device_combo.configure(
            values=names
        )

        self.device_combo.set(
            names[0]
        )

        self.log(
            f"Found {len(self.devices)} loopback device(s)."
        )

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    def start_server(self):

        if not self.devices:

            self.log(
                "No loopback device available."
            )

            return

        selected_name = (
            self.device_combo.get()
        )

        selected = None

        for device in self.devices:

            if device["name"] == selected_name:
                selected = device
                break

        if selected is None:

            self.log(
                "Invalid loopback device."
            )

            return

        try:

            rate = int(
                self.rate_combo.get()
            )

            channels = int(
                self.channel_combo.get()
            )

        except ValueError:

            self.log(
                "Invalid audio settings."
            )

            return

        self.log(
            f"Starting server on TCP port "
            f"{SERVER_PORT}..."
        )

        success = self.server.start(
            selected["index"],
            rate,
            channels,
            DEFAULT_CHUNK
        )

        if success:

            self.start_button.configure(
                state="disabled"
            )

            self.stop_button.configure(
                state="normal"
            )

            self.refresh_button.configure(
                state="disabled"
            )

            self.device_combo.configure(
                state="disabled"
            )

            self.rate_combo.configure(
                state="disabled"
            )

            self.channel_combo.configure(
                state="disabled"
            )

    # --------------------------------------------------------
    # STOP
    # --------------------------------------------------------

    def stop_server(self):

        self.server.stop()

        self.start_button.configure(
            state="normal"
        )

        self.stop_button.configure(
            state="disabled"
        )

        self.refresh_button.configure(
            state="normal"
        )

        self.device_combo.configure(
            state="normal"
        )

        self.rate_combo.configure(
            state="normal"
        )

        self.channel_combo.configure(
            state="normal"
        )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    def set_status(self, text):

        self.after(
            0,
            lambda: self.status_label.configure(
                text=text
            )
        )

    # --------------------------------------------------------
    # AUDIO LEVEL
    # --------------------------------------------------------

    def update_level(self, value):

        self.after(
            0,
            lambda: self.level_bar.set(
                value / 100
            )
        )

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    def log(self, text):

        def write():

            self.log_box.configure(
                state="normal"
            )

            timestamp = time.strftime(
                "%H:%M:%S"
            )

            self.log_box.insert(
                "end",
                f"[{timestamp}] {text}\n"
            )

            self.log_box.see("end")

            self.log_box.configure(
                state="disabled"
            )

        self.after(0, write)

    # --------------------------------------------------------
    # STATS
    # --------------------------------------------------------

    def update_statistics(self):

        if self.server.running:

            elapsed = (
                time.time()
                - self.server.start_time
            )

            mb = (
                self.server.bytes_sent
                / 1024
                / 1024
            )

            # Don't spam logs.
            # Status is handled separately.

        self.after(
            1000,
            self.update_statistics
        )

    # --------------------------------------------------------
    # CLOSE
    # --------------------------------------------------------

    def on_close(self):

        self.server.stop()

        self.destroy()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    app = AudioBridgeApp()

    app.mainloop()