"""
Interface gráfica do AutoDraw.

Responsabilidades desta camada: coletar as escolhas do usuário, mostrar
prévias e coordenar as threads. Todo o trabalho pesado (visão computacional e
movimentação do mouse) fica nos outros módulos; a interface só troca mensagens
com eles através de uma fila, o que mantém a janela responsiva.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, Optional, Tuple

from PIL import ImageTk

from .area_selector import AreaSelector
from .config import BACKENDS, DEFAULT_SETTINGS_PATH, MODE_HELP, MODE_MIXED, MODES, Settings
from .countdown import CountdownWindow
from .hotkeys import EscapeListener
from .image_processing import ImageError, LoadedImage, load_image
from .mouse import DrawingEngine, InputBackendError, MouseBackend, Progress, estimate_duration
from .path_generation import Drawing, FittedDrawing, extract_paths, fit_to_rect
from .preview import render_paths, thumbnail
from .screen import Rect, avoid_corners, contains, primary_screen, session_warning

IMAGE_BOX = (330, 250)
PREVIEW_BOX = (430, 300)
COUNTDOWN_SECONDS = 5
RESPONSIVE_BREAKPOINT = 1050
MIN_WINDOW_WIDTH = 720
MIN_WINDOW_HEIGHT = 560
DEFAULT_WINDOW_WIDTH = 1100
DEFAULT_WINDOW_HEIGHT = 700

# Fases do fluxo principal. Fora de PHASE_IDLE a imagem, a área e os traços
# ficam congelados até o desenho terminar ou ser cancelado.
PHASE_IDLE = "idle"
PHASE_COUNTDOWN = "countdown"
PHASE_DRAWING = "drawing"


def _fmt_time(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class ConfirmDialog(tk.Toplevel):
    """Diálogo de confirmação com três saídas: iniciar, reselecionar, cancelar."""

    def __init__(self, master: tk.Misc, detail: str) -> None:
        super().__init__(master)
        self.title("Confirmar desenho")
        self.resizable(False, False)
        self.result = "cancelar"

        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Deseja iniciar o desenho?",
                  font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, text=detail, justify="left").pack(anchor="w", pady=(8, 16))

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e")
        ttk.Button(buttons, text="Cancelar",
                   command=lambda: self._choose("cancelar")).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Selecionar área novamente",
                   command=lambda: self._choose("reselecionar")).pack(side="right", padx=(8, 0))
        start = ttk.Button(buttons, text="Iniciar desenho",
                           command=lambda: self._choose("iniciar"))
        start.pack(side="right")
        start.focus_set()

        self.bind("<Return>", lambda _e: self._choose("iniciar"))
        self.bind("<Escape>", lambda _e: self._choose("cancelar"))
        self.transient(master)
        self.grab_set()
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + 120
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _choose(self, value: str) -> None:
        self.result = value
        self.destroy()


class AutoDrawApp(tk.Tk):
    """Janela principal."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Roblox AutoDraw")
        self.geometry(f"{DEFAULT_WINDOW_WIDTH}x{DEFAULT_WINDOW_HEIGHT}")
        self.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.resizable(True, True)

        self.settings = Settings.load(DEFAULT_SETTINGS_PATH)

        # Estado
        self.image: Optional[LoadedImage] = None
        self.drawing: Optional[Drawing] = None
        self.fitted: Optional[FittedDrawing] = None
        self.area: Optional[Rect] = None

        # Threads
        self._phase = PHASE_IDLE
        self._queue: queue.Queue[Dict[str, Any]] = queue.Queue()
        self._stop_event = threading.Event()
        self._draw_thread: Optional[threading.Thread] = None
        self._engine: Optional[DrawingEngine] = None
        # Um worker só: ajustes rápidos nos sliders não empilham extrações.
        self._regen_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="regen")
        self._regen_future: Optional[Future] = None
        self._regen_token = 0
        self._regen_after: Optional[str] = None
        self._regen_pending = False  # ajuste feito enquanto ocupado
        self._countdown: Optional[CountdownWindow] = None
        self._hotkey = EscapeListener(self._panic_stop)

        # Referências das imagens exibidas (o Tk não segura sozinho)
        self._image_photo: Optional[ImageTk.PhotoImage] = None
        self._preview_photo: Optional[ImageTk.PhotoImage] = None

        # Estado do layout responsivo
        self._layout_mode: Optional[str] = None
        self._resize_after: Optional[str] = None

        self._ui_ready = False
        self._build_ui()
        self._ui_ready = True
        self._render_image_preview()
        self._render_result_preview()
        self._update_controls()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._poll_queue)

        warning = session_warning()
        if warning:
            self._log(warning)

    # ==================================================================
    # Construção da interface
    # ==================================================================
    def _build_ui(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        outer = ttk.Frame(self)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        self._ui_canvas = tk.Canvas(outer, highlightthickness=0)
        self._ui_canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            outer,
            orient="vertical",
            command=self._ui_canvas.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._ui_canvas.configure(yscrollcommand=scrollbar.set)

        self._content = ttk.Frame(self._ui_canvas, padding=12)
        self._content_window = self._ui_canvas.create_window(
            (0, 0),
            window=self._content,
            anchor="nw",
        )

        self._left = ttk.Frame(self._content)
        self._right = ttk.Frame(self._content)
        self._bottom = ttk.Frame(self._content)

        self._build_image_panel(self._left)
        self._build_area_panel(self._left)
        self._build_settings_panel(self._right)
        self._build_preview_panel(self._right)
        self._build_action_panel(self._bottom)

        self._content.bind("<Configure>", self._on_content_configure)
        self._ui_canvas.bind("<Configure>", self._on_canvas_configure)
        self.bind("<Configure>", self._schedule_responsive_update)

        self._ui_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self._ui_canvas.bind_all("<Button-4>", self._on_mousewheel)
        self._ui_canvas.bind_all("<Button-5>", self._on_mousewheel)

        self.after_idle(self._update_responsive_layout)

    def _build_image_panel(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="1 · Imagem", padding=10)
        box.pack(fill="x")

        self.btn_image = ttk.Button(box, text="Selecionar imagem", command=self.choose_image)
        self.btn_image.pack(fill="x")
        self.image_label = ttk.Label(box, text="Nenhuma imagem carregada",
                                     wraplength=IMAGE_BOX[0])
        self.image_label.pack(anchor="w", pady=(8, 6))
        self.image_canvas = tk.Canvas(box, width=IMAGE_BOX[0], height=IMAGE_BOX[1],
                                      highlightthickness=1, highlightbackground="#c9ced6")
        self.image_canvas.pack(fill="x")

    def _build_area_panel(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="2 · Área de desenho", padding=10)
        box.pack(fill="x", pady=(12, 0))

        row = ttk.Frame(box)
        row.pack(fill="x")
        self.btn_area = ttk.Button(row, text="Selecionar área", command=self.choose_area)
        self.btn_area.pack(side="left", fill="x", expand=True)
        self.btn_clear_area = ttk.Button(row, text="Limpar", width=8, command=self.clear_area)
        self.btn_clear_area.pack(side="left", padx=(8, 0))

        self.area_label = ttk.Label(box, text="Nenhuma área definida", wraplength=IMAGE_BOX[0])
        self.area_label.pack(anchor="w", pady=(8, 0))

    def _build_settings_panel(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="3 · Ajustes", padding=10)
        box.pack(fill="x")

        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="Modo de traçado").pack(side="left")
        self.mode_var = tk.StringVar(value=self.settings.mode)
        combo = ttk.Combobox(row, textvariable=self.mode_var, values=list(MODES),
                             state="readonly", width=14)
        combo.pack(side="right")
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_mode_change())

        self.mode_help = ttk.Label(box, text=MODE_HELP[self.settings.mode],
                                   wraplength=PREVIEW_BOX[0], foreground="#5a6472")
        self.mode_help.pack(anchor="w", pady=(4, 8))

        self.var_detail = self._slider(box, "Detalhes", self.settings.detail, self._on_image_setting)
        self.var_precision = self._slider(box, "Precisão", self.settings.precision, self._on_image_setting)
        self.var_tolerance = self._slider(box, "Tolerância de cores", self.settings.color_tolerance,
                                          self._on_image_setting)

        self.var_invert = tk.BooleanVar(value=self.settings.invert)
        self.chk_invert = ttk.Checkbutton(box, text="Inverter claro e escuro", variable=self.var_invert,
                                          command=self._on_image_setting)
        self.chk_invert.pack(anchor="w", pady=(2, 8))

        # Controles exclusivos do modo misto (aparecem só nele).
        self.mixed_box = ttk.Frame(box)
        self.var_shading = self._slider(self.mixed_box, "Intensidade das sombras", self.settings.shading,
                                        self._on_image_setting)
        self.var_crosshatch = tk.BooleanVar(value=self.settings.crosshatch)
        ttk.Checkbutton(self.mixed_box, text="Hachura cruzada nas sombras fortes",
                        variable=self.var_crosshatch,
                        command=self._on_image_setting).pack(anchor="w", pady=(2, 8))
        self._update_mode_widgets()

        ttk.Separator(box).pack(fill="x", pady=6)

        self.var_speed = self._slider(box, "Velocidade do mouse", self.settings.speed,
                                      self._on_mouse_setting)
        self.var_smoothing = self._slider(box, "Suavidade", self.settings.smoothing,
                                          self._on_mouse_setting)
        self.var_natural = self._slider(box, "Variação natural", self.settings.naturalness,
                                        self._on_mouse_setting)

        row2 = ttk.Frame(box)
        row2.pack(fill="x", pady=(8, 0))
        ttk.Label(row2, text="Envio de entrada").pack(side="left")
        self.backend_var = tk.StringVar(value=self.settings.backend)
        backend_combo = ttk.Combobox(row2, textvariable=self.backend_var, state="readonly",
                                     width=14, values=list(BACKENDS))
        backend_combo.pack(side="right")
        backend_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_mouse_setting())
        self.backend_help = ttk.Label(
            box,
            text="Se o jogo ignorar o cursor, troque para pydirectinput.",
            wraplength=PREVIEW_BOX[0],
            foreground="#5a6472",
        )
        self.backend_help.pack(anchor="w", pady=(4, 0))

    def _slider(self, parent: tk.Misc, label: str, initial: int, command) -> tk.IntVar:
        holder = ttk.Frame(parent)
        holder.pack(fill="x", pady=2)
        var = tk.IntVar(value=initial)
        head = ttk.Frame(holder)
        head.pack(fill="x")
        ttk.Label(head, text=label).pack(side="left")
        value_label = ttk.Label(head, text=str(initial), width=4, anchor="e")
        value_label.pack(side="right")

        def on_move(_value: str) -> None:
            var.set(int(float(_value)))
            value_label.configure(text=str(var.get()))
            command()

        ttk.Scale(holder, from_=0, to=100, orient="horizontal",
                  variable=var, command=on_move).pack(fill="x")
        return var

    def _build_preview_panel(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="4 · Prévia do resultado", padding=10)
        box.pack(fill="x", pady=(12, 0))

        self.preview_canvas = tk.Canvas(box, width=PREVIEW_BOX[0], height=PREVIEW_BOX[1],
                                        highlightthickness=1, highlightbackground="#c9ced6")
        self.preview_canvas.pack(fill="x")
        self.stats_label = ttk.Label(box, text="—", wraplength=PREVIEW_BOX[0])
        self.stats_label.pack(anchor="w", pady=(8, 0))

    def _build_action_panel(self, parent: ttk.Frame) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x")
        self.btn_start = ttk.Button(row, text="Iniciar desenho", command=self.start_flow)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(row, text="Parar (Esc)", command=self._request_stop,
                                   state="disabled")
        self.btn_stop.pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(parent, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(10, 4))

        self.status_label = ttk.Label(parent, text="Pronto. Comece carregando uma imagem.")
        self.status_label.pack(anchor="w")

        self.log = tk.Text(parent, height=5, state="disabled", wrap="word",
                           background="#f6f7f9", relief="flat")
        self.log.pack(fill="x", pady=(8, 0))

    def _on_content_configure(self, _event: tk.Event) -> None:
        self._ui_canvas.configure(scrollregion=self._ui_canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._ui_canvas.itemconfigure(self._content_window, width=event.width)
        self._schedule_responsive_update()

    def _schedule_responsive_update(self, _event: Optional[tk.Event] = None) -> None:
        if self._resize_after is not None:
            try:
                self.after_cancel(self._resize_after)
            except tk.TclError:
                pass
        self._resize_after = self.after(80, self._update_responsive_layout)

    def _update_responsive_layout(self) -> None:
        self._resize_after = None
        width = max(self._ui_canvas.winfo_width(), self.winfo_width())
        layout_mode = "single" if width < RESPONSIVE_BREAKPOINT else "double"

        if layout_mode != self._layout_mode:
            self._left.grid_remove()
            self._right.grid_remove()
            self._bottom.grid_remove()

            if layout_mode == "double":
                self._content.grid_columnconfigure(0, weight=1, uniform="main")
                self._content.grid_columnconfigure(1, weight=1, uniform="main")

                self._left.grid(
                    row=0,
                    column=0,
                    sticky="new",
                    padx=(0, 6),
                )
                self._right.grid(
                    row=0,
                    column=1,
                    sticky="new",
                    padx=(6, 0),
                )
                self._bottom.grid(
                    row=1,
                    column=0,
                    columnspan=2,
                    sticky="ew",
                    pady=(12, 0),
                )
            else:
                self._content.grid_columnconfigure(0, weight=1, uniform="")
                self._content.grid_columnconfigure(1, weight=0, uniform="")

                self._left.grid(row=0, column=0, sticky="ew")
                self._right.grid(row=1, column=0, sticky="ew", pady=(12, 0))
                self._bottom.grid(row=2, column=0, sticky="ew", pady=(12, 0))

            self._layout_mode = layout_mode

        self.update_idletasks()
        self._update_wraplengths()
        self._render_image_preview()
        self._render_result_preview()
        self._ui_canvas.configure(scrollregion=self._ui_canvas.bbox("all"))

    def _update_wraplengths(self) -> None:
        left_width = max(200, self._left.winfo_width() - 30)
        right_width = max(200, self._right.winfo_width() - 30)

        self.image_label.configure(wraplength=left_width)
        self.area_label.configure(wraplength=left_width)
        self.mode_help.configure(wraplength=right_width)
        self.backend_help.configure(wraplength=right_width)
        self.stats_label.configure(wraplength=right_width)

    def _canvas_size(self, canvas: tk.Canvas, fallback: Tuple[int, int]) -> Tuple[int, int]:
        width = canvas.winfo_width()
        height = canvas.winfo_height()

        if width <= 1:
            width = fallback[0]
        if height <= 1:
            height = fallback[1]

        return max(1, width), max(1, height)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if getattr(event, "num", None) == 4:
            direction = -1
        elif getattr(event, "num", None) == 5:
            direction = 1
        else:
            delta = getattr(event, "delta", 0)
            if delta == 0:
                return
            direction = -1 if delta > 0 else 1

        self._ui_canvas.yview_scroll(direction, "units")

    # ==================================================================
    # Etapa 1 — imagem
    # ==================================================================
    def choose_image(self) -> None:
        if self._is_busy():
            return
        path = filedialog.askopenfilename(
            title="Selecionar imagem",
            filetypes=[("Imagens PNG e JPEG", "*.png *.jpg *.jpeg"),
                       ("PNG", "*.png"), ("JPEG", "*.jpg *.jpeg")])
        if not path:
            return
        try:
            self.image = load_image(path)
        except ImageError as exc:
            self.image = None
            messagebox.showerror("Imagem inválida", str(exc))
            self._set_status("A imagem não pôde ser carregada.")
            self._log(f"Erro ao carregar {Path(path).name}: {exc}")
            self._render_image_preview()
            self._update_controls()
            return

        w, h = self.image.original_size
        self.image_label.configure(text=f"{self.image.path.name} · {w}×{h} px")
        self._log(f"Imagem carregada: {self.image.path.name} ({w}×{h}).")
        self._render_image_preview()
        self._schedule_regeneration(delay=0)

    def _render_image_preview(self) -> None:
        self.image_canvas.delete("all")
        canvas_size = self._canvas_size(self.image_canvas, IMAGE_BOX)
        canvas_width, canvas_height = canvas_size

        if self.image is None:
            self.image_canvas.create_text(
                canvas_width // 2,
                canvas_height // 2,
                text="A prévia aparece aqui",
                fill="#8b93a1",
            )
            self._image_photo = None
            return

        thumb = thumbnail(self.image.pil, canvas_size)
        self._image_photo = ImageTk.PhotoImage(thumb)
        x = max(0, (canvas_width - thumb.width) // 2)
        y = max(0, (canvas_height - thumb.height) // 2)
        self.image_canvas.create_image(x, y, image=self._image_photo, anchor="nw")

    # ==================================================================
    # Etapa 2 — área
    # ==================================================================
    def choose_area(self) -> None:
        if self._is_busy():
            return
        self._set_status("Arraste sobre a tela para marcar a área de desenho.")
        self.withdraw()
        self.after(180, lambda: AreaSelector(self, self._on_area_selected).start())

    def _on_area_selected(self, rect: Optional[Rect]) -> None:
        self.deiconify()
        self.lift()
        if rect is None:
            self._set_status("Seleção de área cancelada.")
            return
        safe = avoid_corners(rect, primary_screen(self))
        if safe != rect:
            self._log("Área recuada alguns pixels do canto da tela para não acionar a parada "
                      "de emergência (failsafe).")
        self.area = safe
        x, y, w, h = safe
        self.area_label.configure(text=f"{w}×{h} px · canto superior esquerdo em ({x}, {y})")
        self._log(f"Área definida: {w}×{h} em ({x}, {y}).")
        self._refit()
        self._set_status("Área definida. Confira a prévia e inicie o desenho.")

    def clear_area(self) -> None:
        self.area = None
        self.area_label.configure(text="Nenhuma área definida")
        self._refit()
        self._set_status("Área removida. Selecione uma nova área antes de desenhar.")

    # ==================================================================
    # Ajustes → regeneração dos traços
    # ==================================================================
    def _current_settings(self) -> Settings:
        return replace(
            self.settings,
            mode=self.mode_var.get(),
            detail=self.var_detail.get(),
            precision=self.var_precision.get(),
            color_tolerance=self.var_tolerance.get(),
            invert=bool(self.var_invert.get()),
            shading=self.var_shading.get(),
            crosshatch=bool(self.var_crosshatch.get()),
            speed=self.var_speed.get(),
            smoothing=self.var_smoothing.get(),
            naturalness=self.var_natural.get(),
            backend=self.backend_var.get(),
        )

    def _on_mode_change(self) -> None:
        if not self._ui_ready:
            return
        self.mode_help.configure(text=MODE_HELP.get(self.mode_var.get(), ""))
        self._update_mode_widgets()
        self._on_image_setting()

    def _update_mode_widgets(self) -> None:
        if self.mode_var.get() == MODE_MIXED:
            self.mixed_box.pack(fill="x", after=self.chk_invert)
        else:
            self.mixed_box.pack_forget()

    def _on_image_setting(self) -> None:
        if not self._ui_ready:
            return
        self.settings = self._current_settings()
        self._schedule_regeneration()

    def _on_mouse_setting(self) -> None:
        if not self._ui_ready:
            return
        self.settings = self._current_settings()
        self._update_stats()

    def _schedule_regeneration(self, delay: int = 300) -> None:
        """Agenda a extração de traços, agrupando ajustes feitos em sequência."""
        if self.image is None:
            return
        if self._is_busy():
            self._regen_pending = True
            return
        if self._regen_after is not None:
            try:
                self.after_cancel(self._regen_after)
            except tk.TclError:
                pass
        self._regen_after = self.after(delay, self._start_regeneration)

    def _start_regeneration(self) -> None:
        self._regen_after = None
        if self.image is None:
            return
        self._regen_token += 1
        token = self._regen_token
        settings = self._current_settings()
        image = self.image
        self._set_status("Convertendo a imagem em traços…")
        if self._regen_future is not None:
            self._regen_future.cancel()  # só surte efeito se ainda estiver na fila
        self._regen_future = self._regen_executor.submit(
            self._regeneration_worker, token, image, settings)

    def _regeneration_worker(self, token: int, image: LoadedImage, settings: Settings) -> None:
        try:
            drawing = extract_paths(image, settings)
            self._post({"kind": "drawing", "token": token, "drawing": drawing})
        except Exception as exc:  # noqa: BLE001 — qualquer falha vira mensagem na UI
            self._post({"kind": "error", "text": f"Falha ao gerar os traços: {exc}"})

    # ==================================================================
    # Prévia do resultado
    # ==================================================================
    def _refit(self) -> None:
        if self.drawing is None:
            self.fitted = None
        else:
            area = self.area if self.area else self._default_area()
            self.fitted = fit_to_rect(self.drawing, area, self.settings.min_segment_px)
        self._render_result_preview()
        self._update_stats()
        self._update_controls()

    def _default_area(self) -> Rect:
        """Área hipotética usada só para a prévia antes de o usuário escolher."""
        assert self.drawing is not None
        return (0, 0, self.drawing.width, self.drawing.height)

    def _render_result_preview(self) -> None:
        self.preview_canvas.delete("all")
        area = self.area if self.area else (self._default_area() if self.drawing else None)
        message = "Carregue uma imagem para ver a prévia"
        canvas_size = self._canvas_size(self.preview_canvas, PREVIEW_BOX)
        img = render_paths(self.fitted, area, canvas_size, message)
        self._preview_photo = ImageTk.PhotoImage(img)
        self.preview_canvas.create_image(0, 0, image=self._preview_photo, anchor="nw")

    def _update_stats(self) -> None:
        if self.fitted is None or not self.fitted.paths:
            self.stats_label.configure(text="—")
            return

        seconds = estimate_duration(self.fitted.paths, self._current_settings())
        x, y, w, h = self.fitted.rect
        self.stats_label.configure(
            text=(f"{self.fitted.stroke_count} traços · área ocupada {w}×{h} px · "
                  f"tempo estimado {_fmt_time(seconds)}"))

    # ==================================================================
    # Etapas 3 a 5 — confirmação, contagem, desenho
    # ==================================================================
    def start_flow(self) -> None:
        if self._is_busy():
            return
        if self.image is None:
            messagebox.showinfo("Falta a imagem", "Selecione uma imagem PNG ou JPEG primeiro.")
            return
        if self.area is None:
            messagebox.showinfo("Falta a área", "Selecione a área da tela onde o desenho será feito.")
            return
        if self.fitted is None or not self.fitted.paths:
            messagebox.showinfo("Nada para desenhar",
                                "Os ajustes atuais não geraram traços. Aumente os detalhes "
                                "ou escolha outro modo.")
            return

        self._check_monitor()

        seconds = estimate_duration(self.fitted.paths, self._current_settings())
        x, y, w, h = self.fitted.rect
        detail = (f"{self.fitted.stroke_count} traços serão desenhados em uma área de "
                  f"{w}×{h} px a partir de ({x}, {y}).\n"
                  f"Tempo estimado: {_fmt_time(seconds)}.\n"
                  f"Para interromper: botão Parar, tecla Esc ou leve o cursor ao canto "
                  f"superior esquerdo da tela.")

        dialog = ConfirmDialog(self, detail)
        self.wait_window(dialog)

        if dialog.result == "reselecionar":
            self.choose_area()
            return
        if dialog.result != "iniciar":
            self._set_status("Desenho cancelado. A área continua selecionada.")
            return

        self._begin_countdown()

    def _check_monitor(self) -> None:
        """Oferece trocar para pyautogui quando a área está fora do monitor principal.

        O pydirectinput envia coordenadas absolutas normalizadas pelo monitor
        principal, então um desenho em uma tela secundária sai no lugar errado.
        Fora do Windows o pydirectinput nunca é usado, então não há o que avisar.
        """
        if sys.platform != "win32" or self.area is None:
            return
        if contains(primary_screen(self), self.area):
            return
        if self.backend_var.get() == "pyautogui":
            return
        trocar = messagebox.askyesno(
            "Área fora do monitor principal",
            "A área selecionada está em outro monitor. O modo pydirectinput "
            "posiciona o cursor pelo monitor principal e erraria o alvo.\n\n"
            "Trocar o envio de entrada para pyautogui agora?")
        if trocar:
            self.backend_var.set("pyautogui")
            self._on_mouse_setting()
            self._log("Envio de entrada alterado para pyautogui (área em monitor secundário).")

    def _begin_countdown(self) -> None:
        # Congela os traços confirmados: extrações em andamento são descartadas
        # e refeitas quando o fluxo voltar ao repouso.
        if self._regen_after is not None or (
                self._regen_future is not None and not self._regen_future.done()):
            self._regen_pending = True
        if self._regen_after is not None:
            self.after_cancel(self._regen_after)
            self._regen_after = None
        self._regen_token += 1
        self._set_phase(PHASE_COUNTDOWN)
        self._set_status(f"Iniciando em {COUNTDOWN_SECONDS} segundos… posicione a janela do jogo.")
        self._countdown = CountdownWindow(self, COUNTDOWN_SECONDS,
                                          on_finish=self._launch_drawing,
                                          on_cancel=self._cancel_countdown)
        self._countdown.start()

    def _cancel_countdown(self) -> None:
        self._countdown = None
        self._set_status("Contagem cancelada.")
        self._set_phase(PHASE_IDLE)

    def _launch_drawing(self) -> None:
        self._countdown = None
        if self.fitted is None or not self.fitted.paths:
            self._set_phase(PHASE_IDLE)
            return

        self._stop_event.clear()
        self.progress.configure(value=0)
        self.iconify()  # sai da frente do jogo

        settings = self._current_settings()
        paths = list(self.fitted.paths)
        self._hotkey.start()

        self._draw_thread = threading.Thread(target=self._drawing_worker,
                                             args=(paths, settings), daemon=True)
        self._draw_thread.start()
        self._set_phase(PHASE_DRAWING)
        self._log(f"Desenho iniciado: {len(paths)} traços.")

    def _drawing_worker(self, paths, settings: Settings) -> None:
        last_emit = 0.0
        try:
            backend = MouseBackend(settings.backend)
            engine = DrawingEngine(settings, backend)
            self._engine = engine
            self._post({"kind": "status", "text": f"Desenhando com {backend.name}…"})

            def on_progress(p: Progress) -> None:
                nonlocal last_emit
                now = time.perf_counter()
                if p.finished or p.stopped or p.error or (now - last_emit) > 0.08:
                    last_emit = now
                    self._post({"kind": "progress", "progress": p})

            result = engine.draw(paths, self._stop_event, on_progress)
            self._post({"kind": "progress", "progress": result})
        except InputBackendError as exc:
            self._post({"kind": "error", "text": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._post({"kind": "error", "text": f"Erro durante o desenho: {exc}"})
        finally:
            self._engine = None
            self._post({"kind": "draw_done"})

    def _panic_stop(self) -> None:
        """Parada acionada pela tecla global, em outra thread.

        Faz na hora só o que é seguro fora da thread do Tk (sinalizar o evento e
        soltar o botão) e delega o resto para a fila de mensagens.
        """
        self._stop_event.set()
        engine = self._engine
        if engine is not None:
            engine.stop_now()
        self._post({"kind": "stop"})

    def _request_stop(self) -> None:
        """Parada de emergência: interrompe o laço e solta o botão do mouse."""
        if self._countdown is not None:
            self._countdown.cancel()
            return
        if self._phase != PHASE_DRAWING:
            return
        self._stop_event.set()
        engine = self._engine
        if engine is not None:
            engine.stop_now()
        self._post({"kind": "status", "text": "Parando…"})

    def _is_busy(self) -> bool:
        return self._phase != PHASE_IDLE

    def _set_phase(self, phase: str) -> None:
        self._phase = phase
        if phase == PHASE_IDLE and self._regen_pending:
            self._regen_pending = False
            self._schedule_regeneration(delay=0)
        self._update_controls()

    # ==================================================================
    # Fila de mensagens entre threads
    # ==================================================================
    def _post(self, message: Dict[str, Any]) -> None:
        self._queue.put(message)

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass
        finally:
            self.after(50, self._poll_queue)

    def _handle_message(self, msg: Dict[str, Any]) -> None:
        kind = msg.get("kind")

        if kind == "drawing":
            if msg.get("token") != self._regen_token:
                return  # resultado obsoleto: o usuário já mudou os ajustes
            self.drawing = msg["drawing"]
            self._refit()
            if self.drawing and self.drawing.stroke_count == 0:
                self._set_status("Nenhum traço foi encontrado. Ajuste os detalhes ou o modo.")
            else:
                self._set_status("Traços prontos." if self.area
                                 else "Traços prontos. Agora selecione a área de desenho.")

        elif kind == "progress":
            self._apply_progress(msg["progress"])

        elif kind == "status":
            self._set_status(msg["text"])

        elif kind == "stop":
            self._request_stop()

        elif kind == "error":
            if self.state() == "iconic":
                self.deiconify()
            self._set_status(msg["text"])
            self._log(msg["text"])
            messagebox.showerror("Erro", msg["text"])

        elif kind == "draw_done":
            self._draw_thread = None
            self._hotkey.stop()
            self.deiconify()
            self.lift()
            self._set_phase(PHASE_IDLE)

    def _apply_progress(self, p: Progress) -> None:
        self.progress.configure(value=p.fraction * 100)
        done = f"{p.stroke}/{p.total_strokes}"
        if p.error:
            self._set_status(p.error)
            self._log(p.error)
        elif p.stopped:
            self._set_status(f"Interrompido em {done} traços após {_fmt_time(p.elapsed)}.")
            self._log("Desenho interrompido pelo usuário.")
        elif p.finished:
            self.progress.configure(value=100)
            self._set_status(f"Desenho concluído: {p.total_strokes} traços em {_fmt_time(p.elapsed)}.")
            self._log("Desenho concluído.")
        else:
            restante = ""
            if p.fraction > 0.02:
                total = p.elapsed / p.fraction
                restante = f" · restam ~{_fmt_time(total - p.elapsed)}"
            self._set_status(f"Desenhando {done} ({p.fraction * 100:.0f}%)"
                             f" · {_fmt_time(p.elapsed)}{restante}")

    # ==================================================================
    # Utilidades de interface
    # ==================================================================
    def _set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("[%H:%M:%S] ") + text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _update_controls(self) -> None:
        busy = self._is_busy()
        ready = (self.image is not None and self.area is not None
                 and self.fitted is not None and bool(self.fitted.paths))
        self.btn_start.configure(state="disabled" if busy or not ready else "normal")
        self.btn_stop.configure(state="normal" if busy else "disabled")
        self.btn_image.configure(state="disabled" if busy else "normal")
        self.btn_area.configure(state="disabled" if busy else "normal")
        self.btn_clear_area.configure(
            state="normal" if (self.area is not None and not busy) else "disabled")

    def _on_close(self) -> None:
        self._stop_event.set()
        if self._engine is not None:
            self._engine.stop_now()
        self._hotkey.stop()
        self._regen_executor.shutdown(wait=False, cancel_futures=True)
        try:
            self._current_settings().save(DEFAULT_SETTINGS_PATH)
        except OSError:
            pass
        self.destroy()


def run() -> None:
    """Ponto de entrada usado por `main.py`."""
    app = AutoDrawApp()
    app.mainloop()
