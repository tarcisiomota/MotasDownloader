import customtkinter as ctk
import tkinter as tk
import threading
import yt_dlp
import subprocess
import os
import re
import sys
import shutil
import importlib.util
import urllib.request
import zipfile
import tempfile
from pathlib import Path
from audio_options import audio_options, audio_selector, combined_selector, audio_suffix
from subtitles import subtitle_choices, SIZES
from music_metadata import MusicMetadataPP
from clip_media import ClipMediaPP, clock, validate_range
from yt_dlp.postprocessor.ffmpeg import FFmpegExtractAudioPP

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DOWNLOADS_FOLDER = str(Path.home() / "Downloads")
INACTIVE_TEXT = ("#808080", "#888888")
INACTIVE_TITLE = ("#666666", "#b8b8b8")
INACTIVE_MENU = ("#979da2", "#4a4a4a")
SUCCESS_TEXT = ("#16733b", "#2ecc71")
HEADER_DARK  = "#1a1a2e"
HEADER_LIGHT = "#dde3f0"

FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"


def _bin_dir():
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "bin")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")


def get_ffmpeg_path():
    path = os.path.join(_bin_dir(), "ffmpeg.exe")
    return path if os.path.exists(path) else None


def has_ffmpeg():
    return bool(get_ffmpeg_path() or shutil.which("ffmpeg"))


def download_ffmpeg(progress_cb=None):
    """Download ffmpeg static binary into bin/. Calls progress_cb(pct, msg)."""
    bin_dir = _bin_dir()
    os.makedirs(bin_dir, exist_ok=True)

    zip_path = os.path.join(bin_dir, "_ffmpeg_dl.zip")

    def _reporthook(count, block, total):
        if total > 0 and progress_cb:
            pct = min(count * block / total, 1.0)
            progress_cb(pct * 0.8, f"Baixando ffmpeg… {int(pct*100)}%")

    if progress_cb:
        progress_cb(0, "Iniciando download do ffmpeg…")

    urllib.request.urlretrieve(FFMPEG_URL, zip_path, _reporthook)

    if progress_cb:
        progress_cb(0.82, "Extraindo arquivos…")

    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()
        for name in names:
            base = os.path.basename(name)
            if base in ("ffmpeg.exe", "ffprobe.exe"):
                dest = os.path.join(bin_dir, base)
                with z.open(name) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)

    os.remove(zip_path)

    if progress_cb:
        progress_cb(1.0, "ffmpeg instalado!")


def get_spotdl_path():
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
        candidate = os.path.join(base, "spotdl.exe")
        if os.path.exists(candidate):
            return [candidate]
    return [sys.executable, "-m", "spotdl"]


def get_gallery_dl_path():
    if getattr(sys, "frozen", False):
        candidate = os.path.join(sys._MEIPASS, "gallery-dl.exe")
        if os.path.exists(candidate):
            return [candidate]
    return [sys.executable, "-m", "gallery_dl"]


def has_gallery_dl():
    if getattr(sys, "frozen", False):
        return os.path.exists(os.path.join(sys._MEIPASS, "gallery-dl.exe"))
    return importlib.util.find_spec("gallery_dl") is not None


# Plataformas de redes sociais suportadas no spike. Cada entrada:
# (rótulo, cor de destaque, lista de domínios que identificam o link).
SOCIAL_PLATFORMS = [
    ("TikTok",    "#ff0050", ("tiktok.com", "vm.tiktok.com", "vt.tiktok.com")),
    ("Twitter/X", "#1d9bf0", ("twitter.com", "x.com", "t.co")),
    ("Instagram", "#e4405f", ("instagram.com", "instagr.am")),
    ("Facebook",  "#1877f2", ("facebook.com", "fb.watch", "fb.com", "m.facebook.com")),
]


def detect_social_platform(url):
    """Retorna (rótulo, cor) da plataforma do link, ou (None, None)."""
    host = re.sub(r"^https?://", "", url.strip().lower()).split("/")[0]
    host = host.split("@")[-1].split(":")[0]  # ignora user:pass@ e :porta
    for label, color, domains in SOCIAL_PLATFORMS:
        if any(host == d or host.endswith("." + d) for d in domains):
            return label, color
    return None, None


class DownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Mota's Downloader")
        self.geometry("760x760")
        self.resizable(False, False)
        self._is_dark = True

        # ── Header ──────────────────────────────────────────────────────────
        self._header = ctk.CTkFrame(self, height=56, corner_radius=0, fg_color=HEADER_DARK)
        self._header.pack(fill="x")
        self._header.pack_propagate(False)

        self._title_label = ctk.CTkLabel(
            self._header,
            text="  Mota's Downloader",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="white",
        )
        self._title_label.pack(side="left", padx=20)

        self._theme_btn = ctk.CTkButton(
            self._header, text="☀  Claro", width=90, height=30,
            fg_color="transparent", hover_color="#2a2a4e",
            border_width=1, border_color="#555577", text_color="#ccccee",
            font=ctk.CTkFont(size=12), command=self._toggle_theme,
        )
        self._theme_btn.pack(side="right", padx=10)

        ctk.CTkButton(
            self._header, text="?", width=30, height=30,
            fg_color="transparent", hover_color="#2a2a4e",
            border_width=1, border_color="#555577", text_color="#ccccee",
            font=ctk.CTkFont(size=13, weight="bold"), command=self._show_help,
        ).pack(side="right", padx=(0, 4))

        self._folder_btn = ctk.CTkButton(
            self._header, text="📁  Downloads",
            fg_color="transparent", hover_color="#2a2a4e",
            command=self._open_downloads,
            font=ctk.CTkFont(size=11), text_color="#aaaacc",
        )
        self._folder_btn.pack(side="right", padx=4)

        self._ffmpeg_widget = None
        self._refresh_ffmpeg_badge()

        # ── Tabs ─────────────────────────────────────────────────────────────
        self.tabview = ctk.CTkTabview(self, width=740, height=600, anchor="nw")
        self.tabview.pack(padx=10, pady=8, fill="both", expand=True)
        self.tabview.add("  YouTube  ")
        self.tabview.add("  YT Music  ")
        self.tabview.add("  Spotify  ")
        self.tabview.add("  Redes Sociais  ")

        self._yt_formats     = {}    # format_id -> format dict (from yt-dlp)
        self._yt_info        = None  # full info dict
        self._yt_is_playlist = False # True when analyzed URL is a playlist

        self._build_youtube_tab()
        self._build_ytmusic_tab()
        self._build_spotify_tab()
        self._build_social_tab()

    # ── Theme ──────────────────────────────────────────────────────────────

    def _toggle_theme(self):
        self._is_dark = not self._is_dark
        if self._is_dark:
            ctk.set_appearance_mode("dark")
            self._header.configure(fg_color=HEADER_DARK)
            self._title_label.configure(text_color="white")
            self._theme_btn.configure(text="☀  Claro", hover_color="#2a2a4e",
                                      border_color="#555577", text_color="#ccccee")
            self._folder_btn.configure(hover_color="#2a2a4e", text_color="#aaaacc")
        else:
            ctk.set_appearance_mode("light")
            self._header.configure(fg_color=HEADER_LIGHT)
            self._title_label.configure(text_color="#1a1a2e")
            self._theme_btn.configure(text="🌙  Escuro", hover_color="#c0c8de",
                                      border_color="#9999bb", text_color="#333355")
            self._folder_btn.configure(hover_color="#c0c8de", text_color="#444466")

        if hasattr(self, "cut_check"):
            self._refresh_cut()

    @property
    def _fg_text(self):
        return "#111111" if not self._is_dark else "#ffffff"

    # ── Helpers ────────────────────────────────────────────────────────────

    def _open_downloads(self):
        os.startfile(DOWNLOADS_FOLDER)

    def _build_dest_row(self, tab):
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(anchor="w", padx=14, pady=(4, 0))
        ctk.CTkLabel(row, text=f"📁  Salvando em:  {DOWNLOADS_FOLDER}",
                     text_color="#888888", font=ctk.CTkFont(size=10)).pack(side="left")
        ctk.CTkButton(row, text="↗", width=24, height=22,
                      fg_color="transparent", hover_color="#2a2a4e",
                      border_width=1, border_color="#555577", text_color="#aaaacc",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._open_downloads).pack(side="left", padx=6)

    def _log(self, box, msg):
        box.configure(state="normal")
        box.insert("end", msg + "\n")
        box.see("end")
        box.configure(state="disabled")

    def _install_paste_menu(self, entry):
        # Tk Menu uses the native Windows popup style.
        menu = tk.Menu(entry, tearoff=False)
        def paste():
            if entry.cget("state") != "disabled":
                entry.focus_set()
                entry._entry.event_generate("<<Paste>>")
        menu.add_command(label="Colar", command=paste)
        def popup(event):
            menu.entryconfigure(0, state="disabled" if entry.cget("state") == "disabled" else "normal")
            entry.focus_set()
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return "break"
        entry.bind("<Button-3>", popup, add=True)
        entry._paste_menu = menu

    def _set_status(self, label, text, color="active"):
        if color == "active":
            color = self._fg_text
        if color == "#2ecc71":
            color = SUCCESS_TEXT
        label.configure(text=text, text_color=color)

    def _show_help(self):
        win = ctk.CTkToplevel(self)
        win.title("Como usar — Mota's Downloader")
        win.geometry("600x660")
        win.resizable(False, False)
        win.grab_set()

        # Rodapé fixo: aviso + botão fechar
        footer = ctk.CTkFrame(win, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=14, pady=(4, 12))
        ctk.CTkLabel(
            footer,
            text="⚠  Este programa não deve ser utilizado para fins comerciais.",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#e67e22",
        ).pack(pady=(0, 6))
        ctk.CTkButton(footer, text="Fechar", width=140, height=36,
                      command=win.destroy).pack()

        # Scroll frame ocupa o resto
        scroll = ctk.CTkScrollableFrame(win, width=570)
        scroll.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        def section(title, color):
            ctk.CTkLabel(scroll, text=title, font=ctk.CTkFont(size=14, weight="bold"),
                         text_color=color, anchor="w").pack(fill="x", pady=(14, 4))
            ctk.CTkFrame(scroll, height=1, fg_color=color).pack(fill="x", pady=(0, 6))

        def line(text, indent=0):
            ctk.CTkLabel(scroll, text=("    " * indent) + text,
                         font=ctk.CTkFont(size=12), anchor="w",
                         justify="left", wraplength=520).pack(fill="x", pady=1)

        # ── Cabeçalho ──────────────────────────────────────────────────────
        ctk.CTkLabel(scroll, text="Mota's Downloader",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(4, 2))
        ctk.CTkLabel(scroll, text="Baixe vídeos e áudios do YouTube, YouTube Music, Spotify e redes sociais.",
                     font=ctk.CTkFont(size=12), text_color="#888888").pack(pady=(0, 8))

        # ── YouTube ────────────────────────────────────────────────────────
        section("▶  YouTube", "#c4302b")
        line("1. Cole o link de um vídeo ou playlist no campo URL.")
        line("2. Clique em 🔍 Analisar — o app consulta os formatos disponíveis.")
        line("3. Escolha o Tipo de download:")
        line("• Vídeo + Áudio → MP4 com vídeo e som", 1)
        line("• Só Vídeo → apenas a imagem, sem áudio", 1)
        line("• Só Áudio → MP3 extraído do vídeo", 1)
        line("4. Selecione a Resolução e a Qualidade de áudio nos dropdowns.")
        line("5. Opcional: marque Recortar trecho e informe Início e Fim (00:00:00).")
        line("6. Clique em Baixar. O arquivo inteiro é baixado antes do recorte preciso.")
        line("Recorte: apenas vídeos individuais; o vídeo é recodificado para H.264/MP4.")
        line("Legendas: marque Gravar legendas no vídeo e escolha idioma, tamanho e cor.")
        line("Português tem prioridade, preferindo legendas do autor. O contorno é preto.")
        line("As legendas ficam permanentes na imagem e exigem recodificação do vídeo.")
        line("🎵 Só Áudio: incorpora automaticamente nome, artista, álbum, ano e imagem.")
        line("Usa dados do link e campos explícitos da descrição; sem IA ou busca externa.")
        line("Artista, álbum e ano ficam vazios se não houver informação confiável.")
        line("")
        line("📋 Playlist: ao colar um link de playlist, o app detecta automaticamente,")
        line("mostra o número de vídeos e baixa todos na pasta Downloads/Nome-da-Playlist/.")

        # ── YT Music ──────────────────────────────────────────────────────
        section("🎵  YouTube Music", "#cc0000")
        line("1. Cole o link de uma música ou playlist do YouTube Music.")
        line("2. Clique em 🔍 Analisar — lista os streams de áudio reais disponíveis.")
        line("3. Configure:")
        line("• Stream → escolha o formato de origem (opus 139kbps, m4a 129kbps…)", 1)
        line("• Salvar como → MP3, M4A, WAV ou FLAC", 1)
        line("• Bitrate → qualidade do arquivo de saída (320k, 256k…)", 1)
        line("• Metadados → incorpora título, artista e álbum no arquivo", 1)
        line("• Capa do álbum → embute a imagem da capa no arquivo de áudio", 1)
        line("A imagem vem do próprio link; usa a miniatura quando não há capa disponível.")
        line("O ano é o lançamento informado, não a data de postagem do vídeo.")
        line("4. Clique em ⬇ Baixar.")
        line("")
        line("📋 Playlist: detectada automaticamente. Cria pasta com o nome da playlist.")

        # ── Spotify ───────────────────────────────────────────────────────
        section("🎧  Spotify", "#1DB954")
        line("1. Cole o link do Spotify no campo URL.")
        line("   Suporta:  🎵 Música  •  💿 Álbum  •  📋 Playlist")
        line("2. Selecione a Qualidade do MP3 (320k recomendado).")
        line("3. Clique em ⬇ Baixar.")
        line("")
        line("ℹ  O Spotify não permite download direto. O app usa o spotdl para")
        line("   buscar cada faixa no YouTube Music e baixar com metadados completos.")

        # ── Redes Sociais ───────────────────────────────────────────────────
        section("🌐  Redes Sociais", "#8e44ad")
        line("Baixa de TikTok, Twitter/X, Instagram e Facebook.")
        line("1. Cole o link do post, vídeo ou perfil. O app detecta a plataforma.")
        line("2. Escolha o Tipo:")
        line("• Vídeo → usa o yt-dlp; selecione a qualidade (Melhor, 1080p…)", 1)
        line("• Fotos / galeria → usa o gallery-dl para imagens e carrosséis", 1)
        line("3. Clique em ⬇ Baixar. As fotos vão para Downloads/Redes Sociais/.")
        line("")
        line("ℹ  Conteúdo privado ou restrito pode exigir login (cookies).")
        line("   Fotos exigem o gallery-dl instalado:  pip install gallery-dl")

        # ── Geral ─────────────────────────────────────────────────────────
        section("⚙  Geral", "#888888")
        line("📁  Downloads — abre a pasta de destino (padrão: Downloads, dentro da pasta do programa).")
        line("☀ / 🌙  — alterna entre tema claro e escuro.")
        line("✓ ffmpeg OK — componente necessário para HD, MP3 e mesclagem de streams.")
        line("⬇ Instalar ffmpeg — aparece se o ffmpeg não for encontrado;")
        line("   clique para instalar automaticamente sem sair do app.", 1)
        line("")
        line("💡  Dicas:")
        line("• Links do WhatsApp/compartilhamento funcionam normalmente.", 1)
        line("• Pressione Enter no campo URL para acionar o Analisar.", 1)
        line("• Playlists grandes podem demorar — o progresso aparece na barra.", 1)


    def _refresh_ffmpeg_badge(self):
        if self._ffmpeg_widget:
            self._ffmpeg_widget.destroy()
            self._ffmpeg_widget = None

        if has_ffmpeg():
            lbl = ctk.CTkLabel(
                self._header, text="✓ ffmpeg OK",
                text_color="#2ecc71", font=ctk.CTkFont(size=10),
            )
            lbl.pack(side="right", padx=8)
            self._ffmpeg_widget = lbl
        else:
            btn = ctk.CTkButton(
                self._header, text="⬇ Instalar ffmpeg", width=130, height=26,
                fg_color="#c0500a", hover_color="#954010",
                font=ctk.CTkFont(size=10), text_color="white",
                command=self._install_ffmpeg,
            )
            btn.pack(side="right", padx=8)
            self._ffmpeg_widget = btn

    def _install_ffmpeg(self):
        if self._ffmpeg_widget:
            self._ffmpeg_widget.configure(state="disabled", text="Instalando…")

        # Mostra janela de progresso
        win = ctk.CTkToplevel(self)
        win.title("Instalando ffmpeg")
        win.geometry("420x140")
        win.resizable(False, False)
        win.grab_set()

        ctk.CTkLabel(win, text="Baixando e instalando ffmpeg…",
                     font=ctk.CTkFont(size=13)).pack(pady=(20, 6))
        bar = ctk.CTkProgressBar(win, width=380)
        bar.pack(pady=4)
        bar.set(0)
        status_lbl = ctk.CTkLabel(win, text="Aguarde…", font=ctk.CTkFont(size=11),
                                  text_color="#888888")
        status_lbl.pack(pady=4)

        def _progress(pct, msg):
            self.after(0, lambda: bar.set(pct))
            self.after(0, lambda: status_lbl.configure(text=msg))

        def _run():
            try:
                download_ffmpeg(progress_cb=_progress)
                self.after(0, lambda: win.destroy())
                self.after(100, self._refresh_ffmpeg_badge)
                self.after(100, lambda: self._set_status(
                    self.yt_status, "✓ ffmpeg instalado! Analise novamente.", "#2ecc71"))
            except Exception as exc:
                self.after(0, lambda: win.destroy())
                self.after(0, lambda exc=exc: self._set_status(
                    self.yt_status, f"✗ Erro ao instalar ffmpeg: {exc}", "#e74c3c"))
                self.after(100, self._refresh_ffmpeg_badge)

        threading.Thread(target=_run, daemon=True).start()

    # ── YouTube tab ────────────────────────────────────────────────────────

    def _build_youtube_tab(self):
        tab = self.tabview.tab("  YouTube  ")

        # ── URL + Analisar ──────────────────────────────────────────────────
        ctk.CTkLabel(tab, text="URL do vídeo ou playlist:", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=12, pady=(12, 2)
        )
        url_row = ctk.CTkFrame(tab, fg_color="transparent")
        url_row.pack(fill="x", padx=12, pady=(0, 6))

        self.yt_url = ctk.CTkEntry(
            url_row, height=36,
            placeholder_text="https://www.youtube.com/watch?v=...",
        )
        self._install_paste_menu(self.yt_url)
        self.yt_url.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.yt_url.bind("<Return>", lambda _: self._start_analyze())

        self.yt_analyze_btn = ctk.CTkButton(
            url_row, text="🔍  Analisar", width=110, height=36,
            font=ctk.CTkFont(size=13),
            fg_color="#2a5caa", hover_color="#1e4080",
            command=self._start_analyze,
        )
        self.yt_analyze_btn.pack(side="left")

        # ── Info do vídeo ───────────────────────────────────────────────────
        self._yt_info_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self._yt_info_frame.pack(fill="x", padx=12, pady=(0, 4))
        self._yt_title_label = ctk.CTkLabel(
            self._yt_info_frame, text="", font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#aaaaaa", anchor="w", wraplength=700,
        )
        self._yt_title_label.pack(anchor="w")

        # ── Opções de formato ───────────────────────────────────────────────
        self._yt_opts_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self._yt_opts_frame.pack(fill="x", padx=12, pady=4)

        # Tipo
        row_tipo = ctk.CTkFrame(self._yt_opts_frame, fg_color="transparent")
        row_tipo.pack(fill="x", pady=2)
        ctk.CTkLabel(row_tipo, text="Tipo:", width=60).pack(side="left")
        self.yt_type = ctk.CTkSegmentedButton(
            row_tipo,
            values=["Vídeo + Áudio", "Só Vídeo", "Só Áudio"],
            command=self._on_yt_type_change,
        )
        self.yt_type.pack(side="left", padx=8)
        self.yt_type.set("Vídeo + Áudio")

        # Qualidade
        self._yt_qual_row = ctk.CTkFrame(self._yt_opts_frame, fg_color="transparent")
        self._yt_qual_row.pack(fill="x", pady=2)

        self._vq_frame = ctk.CTkFrame(self._yt_qual_row, fg_color="transparent")
        self._vq_frame.pack(side="left", padx=(0, 20))
        ctk.CTkLabel(self._vq_frame, text="Resolução:").pack(side="left", padx=(0, 6))
        self.yt_vq = ctk.CTkOptionMenu(self._vq_frame, values=["—"], width=145)
        self.yt_vq.pack(side="left")

        self._aq_frame = ctk.CTkFrame(self._yt_qual_row, fg_color="transparent")
        self._aq_frame.pack(side="left")
        ctk.CTkLabel(self._aq_frame, text="Qualidade áudio:").pack(side="left", padx=(0, 6))
        self.yt_aq = ctk.CTkOptionMenu(self._aq_frame, values=["—"], width=315, font=ctk.CTkFont(size=11))
        self.yt_aq.pack(side="left")

        self._yt_busy = False
        self._yt_analyzed_url = None
        self._cut_duration = None
        self.cut_enabled = ctk.BooleanVar(value=False)
        self.cut_start = ctk.StringVar(value="00:00:00")
        self.cut_end = ctk.StringVar(value="00:00:00")
        cut_row = ctk.CTkFrame(self._yt_opts_frame, fg_color="transparent")
        cut_row.pack(fill="x", pady=(12, 0))
        self.cut_check = ctk.CTkCheckBox(cut_row, text="Recortar trecho", width=140,
            variable=self.cut_enabled, command=self._refresh_cut)
        self._cut_title_color = self.cut_check.cget("text_color")
        self.cut_check.pack(side="left", padx=(0, 12))
        self.cut_labels, self.cut_entries = [], []
        for label, variable in (("Início", self.cut_start), ("Fim", self.cut_end)):
            widget = ctk.CTkLabel(cut_row, text=label)
            widget.pack(side="left", padx=(0, 6))
            self.cut_labels.append(widget)
            entry = ctk.CTkEntry(cut_row, width=90, textvariable=variable, justify="center")
            entry.pack(side="left", padx=(0, 14))
            self.cut_entries.append(entry)
        self.cut_summary = ctk.CTkLabel(cut_row, text="", font=ctk.CTkFont(size=11))
        self.cut_summary.pack(side="right")
        self.cut_hint = ctk.CTkLabel(self._yt_opts_frame, text="", anchor="w",
            font=ctk.CTkFont(size=11), wraplength=690)
        self.cut_hint.pack(fill="x", pady=(3, 0))
        self.cut_start.trace_add("write", lambda *_: self._refresh_cut())
        self.cut_end.trace_add("write", lambda *_: self._refresh_cut())

        self.sub_enabled = ctk.BooleanVar(value=False)
        self._sub_choices = {}
        subrow = ctk.CTkFrame(self._yt_opts_frame, fg_color="transparent")
        subrow.pack(fill="x", pady=(8, 0))
        self.sub_check = ctk.CTkCheckBox(subrow, text="Gravar legendas no vídeo",
            variable=self.sub_enabled, command=self._refresh_subtitles)
        self._sub_title_color = self.sub_check.cget("text_color")
        self.sub_check.pack(side="left", padx=(0, 12))
        self.sub_lang = ctk.CTkOptionMenu(subrow, values=["Sem legendas"], width=420)
        self.sub_lang.pack(side="left")
        style = ctk.CTkFrame(self._yt_opts_frame, fg_color="transparent")
        style.pack(fill="x", pady=(5, 0))
        self.sub_size_label = ctk.CTkLabel(style, text="Tamanho:")
        self.sub_size_label.pack(side="left", padx=(0, 6))
        self.sub_size = ctk.CTkOptionMenu(style, values=list(SIZES), width=140)
        self.sub_size.pack(side="left", padx=(0, 18))
        self.sub_color_label = ctk.CTkLabel(style, text="Cor:")
        self.sub_color_label.pack(side="left", padx=(0, 6))
        self.sub_color = ctk.CTkOptionMenu(style, values=["Branca", "Amarela"], width=120)
        self.sub_color.pack(side="left")
        self.sub_hint = ctk.CTkLabel(self._yt_opts_frame, text="", anchor="w",
            font=ctk.CTkFont(size=11), wraplength=690)
        self.sub_hint.pack(fill="x")
        self._sub_menu_colors = {widget: {key: widget.cget(key) for key in
            ('fg_color', 'button_color', 'button_hover_color')} for widget in
            (self.sub_lang, self.sub_size, self.sub_color)}
        self._sub_label_colors = {widget: widget.cget('text_color') for widget in
            (self.sub_size_label, self.sub_color_label, self.sub_hint)}
        self._refresh_subtitles()

        # Estado inicial: opções desabilitadas até analisar
        self._yt_opts_frame.pack_forget()

        # ── Botão Baixar ────────────────────────────────────────────────────
        self.yt_btn = ctk.CTkButton(
            tab, text="⬇   Baixar", width=720, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#c4302b", hover_color="#9b2321",
            command=self._start_yt_download, state="disabled",
        )
        self.yt_btn.pack(padx=12, pady=8)

        # ── Progresso + log ─────────────────────────────────────────────────
        self.yt_bar = ctk.CTkProgressBar(tab, width=720)
        self.yt_bar.pack(padx=12, pady=(0, 4))
        self.yt_bar.set(0)

        self.yt_status = ctk.CTkLabel(tab, text="Cole um link e clique em Analisar.",
                                       text_color="#888888", font=ctk.CTkFont(size=11))
        self.yt_status.pack(anchor="w", padx=14)

        self._build_dest_row(tab)

        self.yt_log = ctk.CTkTextbox(tab, width=720, height=130,
                                      font=ctk.CTkFont(size=10, family="Consolas"))
        self.yt_log.pack(padx=12, pady=6)
        self.yt_log.configure(state="disabled")

    def _refresh_subtitles(self):
        if not hasattr(self, 'sub_check'):
            return
        live = (self._yt_info or {}).get('is_live') or (self._yt_info or {}).get('live_status') == 'is_upcoming'
        available = bool(self._sub_choices) and not self._yt_is_playlist and not live and self.yt_type.get() != 'Só Áudio' and has_ffmpeg()
        if not available:
            self.sub_enabled.set(False)
        self.sub_check.configure(state='normal' if available and not self._yt_busy else 'disabled')
        active = available and self.sub_enabled.get() and not self._yt_busy
        self.sub_check.configure(text_color=self._sub_title_color if active else INACTIVE_TITLE,
            text_color_disabled=INACTIVE_TITLE)
        for widget, original in self._sub_label_colors.items():
            widget.configure(text_color=original if active else INACTIVE_TEXT)
        for widget in (self.sub_lang, self.sub_size, self.sub_color):
            widget.configure(**(self._sub_menu_colors[widget] if active else
                dict(fg_color=INACTIVE_MENU, button_color=INACTIVE_MENU, button_hover_color=INACTIVE_MENU)))
            widget.configure(text_color_disabled=INACTIVE_TEXT)
            widget.configure(state='normal' if active else 'disabled',
                text_color=('#202124','#eeeeee') if active else ('#808080','#888888'))
        if live:
            hint = 'Legendas gravadas disponíveis após o encerramento da transmissão.'
        elif self._yt_is_playlist:
            hint = 'Legendas gravadas disponíveis para vídeos individuais.'
        elif self.yt_type.get() == 'Só Áudio':
            hint = 'Escolha um tipo com vídeo para gravar legendas.'
        elif not self._sub_choices:
            hint = 'Nenhuma legenda compatível encontrada neste vídeo.'
        elif not any(c['code'].lower().split('-')[0]=='pt' for c in self._sub_choices.values()):
            hint = 'Português indisponível. Escolha outro idioma. A legenda será permanente.'
        else:
            hint = ''
        self.sub_hint.configure(text=hint)
        if hint:
            self.sub_hint.pack(fill="x")
        else:
            self.sub_hint.pack_forget()

    def _refresh_cut(self):
        self._refresh_subtitles()
        available = self._cut_duration is not None and not self._yt_is_playlist and has_ffmpeg()
        busy = self._yt_busy
        self.cut_check.configure(state="normal" if available and not busy else "disabled")
        enabled = available and self.cut_enabled.get()
        self.cut_check.configure(text_color=self._cut_title_color if enabled and not busy else INACTIVE_TITLE,
            text_color_disabled=INACTIVE_TITLE)
        color = ("#202124", "#eeeeee") if enabled and not busy else INACTIVE_TEXT
        for label in self.cut_labels:
            label.configure(text_color=color)
        for entry in self.cut_entries:
            entry.configure(state="normal" if enabled and not busy else "disabled", text_color=color)
        error = None
        if not available:
            hint = "Recorte disponível para vídeos individuais com duração definida e FFmpeg."
            summary = ""
        elif enabled:
            try:
                a,b = validate_range(self.cut_start.get(), self.cut_end.get(), self._cut_duration)
                summary = "Trecho · " + clock(b-a)
                hint = "O arquivo inteiro será baixado; depois, o trecho será recortado."
            except ValueError as exc:
                error = str(exc)
                summary, hint = "Trecho inválido", error
        else:
            summary = "Inteiro · " + clock(self._cut_duration)
            hint = "Use horas:minutos:segundos. O fim recebe a duração do vídeo."
        self.cut_summary.configure(text=summary, text_color=("#62656b", "#a0a2a9") if enabled and not busy else INACTIVE_TEXT)
        self.cut_hint.configure(text=hint, text_color=("#aa2222", "#ff9992") if error else (("#62656b", "#a0a2a9") if enabled and not busy else INACTIVE_TEXT))
        if hasattr(self, "yt_btn") and not busy:
            self.yt_btn.configure(text="⬇   Baixar trecho" if enabled else "⬇   Baixar",
                state="normal" if self._yt_info is not None and not error else "disabled")

    def _finish_yt_download(self):
        self._yt_busy = False
        self.yt_url.configure(state="normal")
        self.yt_analyze_btn.configure(state="normal")
        self.yt_type.configure(state="normal")
        self.yt_vq.configure(state="normal")
        self.yt_aq.configure(state="normal")
        self._refresh_cut()

    # ── Análise ────────────────────────────────────────────────────────────

    def _start_analyze(self):
        url = self.yt_url.get().strip()
        if not url:
            self._set_status(self.yt_status, "⚠  Cole um link válido.", "orange")
            return

        self._yt_analyzed_url = None
        self._yt_analyzing_url = url
        self._cut_duration = None
        self.cut_enabled.set(False)
        self.yt_url.configure(state="disabled")
        self.yt_analyze_btn.configure(state="disabled", text="Analisando…")
        self.yt_btn.configure(state="disabled")
        self._yt_opts_frame.pack_forget()
        self._yt_title_label.configure(text="")
        self.yt_bar.set(0)
        self._set_status(self.yt_status, "Analisando link…")
        self._yt_formats.clear()
        self._yt_info = None

        threading.Thread(target=self._analyze, args=(url,), daemon=True).start()

    @staticmethod
    def _url_is_playlist(url):
        return "playlist" in url or ("list=" in url and "watch" not in url) or \
               ("/album/" in url) or ("list=" in url)

    def _analyze(self, url):
        try:
            is_pl = self._url_is_playlist(url)
            self._yt_is_playlist = is_pl

            if is_pl:
                # Extração rápida: só metadados da playlist, sem buscar cada vídeo
                opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)

                self._yt_info = info
                title    = info.get("title", "Playlist")
                uploader = info.get("uploader", info.get("channel", ""))
                entries  = info.get("entries") or []
                count    = len(entries)

                # Playlists usam seletores genéricos (sem format_id por vídeo)
                ff = has_ffmpeg()
                self._yt_video_opts = {
                    "Melhor disponível": None,
                    "4K (2160p)": 2160, "1080p": 1080,
                    "720p": 720, "480p": 480, "360p": 360,
                }
                self._yt_audio_opts = {
                    "320 kbps": "320", "256 kbps": "256",
                    "192 kbps": "192", "128 kbps": "128",
                }
                self._yt_combo_opts = {}  # não usado em modo playlist

                self.after(0, lambda: self._update_ui_after_analyze(
                    title, uploader, "", count=count))
            else:
                # Vídeo único: busca formatos reais
                opts = {"quiet": True, "no_warnings": True}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)

                self._yt_info = info
                formats = info.get("formats", [])
                ff = has_ffmpeg()

                video_opts = {}
                audio_opts = {}
                combo_opts = {}

                for f in formats:
                    vcodec = f.get("vcodec", "none") or "none"
                    acodec = f.get("acodec", "none") or "none"
                    ext    = f.get("ext", "")
                    height = f.get("height")
                    abr    = f.get("abr")
                    fid    = f["format_id"]

                    if vcodec == "none" and acodec != "none" and abr:
                        label = f"{int(abr)}kbps {ext}"
                        if label not in audio_opts:
                            audio_opts[label] = fid

                    if ff and vcodec != "none" and acodec == "none" and height:
                        label = f"{height}p {ext}"
                        if label not in video_opts:
                            video_opts[label] = fid

                    if vcodec != "none" and acodec != "none" and height:
                        label = f"{height}p {ext}"
                        if label not in combo_opts:
                            combo_opts[label] = fid

                def sort_lbl(lbl):
                    try:
                        return int(lbl.split("p")[0])
                    except Exception:
                        return 0

                self._yt_video_opts = {k: video_opts[k] for k in sorted(video_opts, key=sort_lbl, reverse=True)}
                self._yt_combo_opts = {k: combo_opts[k] for k in sorted(combo_opts, key=sort_lbl, reverse=True)}
                self._yt_audio_opts = audio_options(formats)

                title    = info.get("title", "")
                duration = info.get("duration_string", "")
                uploader = info.get("uploader", "")

                self.after(0, lambda: self._update_ui_after_analyze(
                    title, uploader, duration))

        except Exception as exc:
            self.after(0, lambda message=str(exc): self._analyze_error(message))

    def _update_ui_after_analyze(self, title, uploader, duration, count=0):
        self.yt_url.configure(state="normal")
        self._yt_analyzed_url = self._yt_analyzing_url
        choices = subtitle_choices(self._yt_info or {}) if not self._yt_is_playlist else []
        self._sub_choices = {c['label']:c for c in choices}
        self.sub_enabled.set(False)
        self.sub_lang.configure(values=list(self._sub_choices) or ['Sem legendas'])
        self.sub_lang.set(next(iter(self._sub_choices), 'Sem legendas'))
        info = self._yt_info or {}
        duration_seconds = info.get("duration")
        import math
        self._cut_duration = (duration_seconds if not self._yt_is_playlist
            and not info.get("is_live") and info.get("live_status") != "is_upcoming"
            and isinstance(duration_seconds, (float, int)) and math.isfinite(duration_seconds)
            and duration_seconds >= 1 else None)
        self.cut_enabled.set(False)
        self.cut_start.set("00:00:00")
        self.cut_end.set(clock(self._cut_duration or 0))
        self.yt_analyze_btn.configure(state="normal", text="🔍  Analisar")

        if count:
            badge = f"📋  Playlist  •  {count} vídeos"
            info_text = f"{badge}\n{title}"
            if uploader:
                info_text += f"  —  {uploader}"
            self._yt_title_label.configure(text=info_text, text_color="#7fb3e8")
        else:
            info_text = title
            if uploader:
                info_text += f"  —  {uploader}"
            if duration:
                info_text += f"  ({duration})"
            self._yt_title_label.configure(text=info_text, text_color="#aaaaaa")

        self.yt_aq.set(next(iter(self._yt_audio_opts), "—"))
        self._on_yt_type_change(self.yt_type.get())
        self._yt_opts_frame.pack(fill="x", padx=12, pady=4, before=self.yt_btn)
        self._refresh_cut()
        self._set_status(self.yt_status, "✓  Análise concluída. Configure e clique em Baixar.", "#2ecc71")

    def _analyze_error(self, msg):
        self.yt_url.configure(state="normal")
        self.yt_analyze_btn.configure(state="normal", text="🔍  Analisar")
        self._set_status(self.yt_status, f"✗  {msg[:80]}", "#e74c3c")
        self._log(self.yt_log, f"ERRO na análise: {msg}\n")

    def _on_yt_type_change(self, value):
        previous_audio = self.yt_aq.get()
        ff = has_ffmpeg()
        is_pl = getattr(self, "_yt_is_playlist", False)

        for w in self._yt_qual_row.winfo_children():
            w.pack_forget()

        audio_labels = list(self._yt_audio_opts.keys()) if hasattr(self, "_yt_audio_opts") and self._yt_audio_opts \
                       else ["320 kbps", "256 kbps", "192 kbps", "128 kbps"]

        if value == "Só Áudio":
            self.yt_aq.configure(values=audio_labels)
            self.yt_aq.set(previous_audio if previous_audio in audio_labels else audio_labels[0])
            self._aq_frame.pack(side="left")

        elif value == "Só Vídeo":
            video_labels = list(self._yt_video_opts.keys()) if hasattr(self, "_yt_video_opts") and self._yt_video_opts \
                           else (["Melhor disponível"] if ff else ["Sem formatos"])
            self.yt_vq.configure(values=video_labels)
            self.yt_vq.set(video_labels[0])
            self._vq_frame.pack(side="left")

        else:  # Vídeo + Áudio
            if ff or is_pl:
                video_labels = list(self._yt_video_opts.keys()) if hasattr(self, "_yt_video_opts") and self._yt_video_opts \
                               else ["Melhor disponível"]
            else:
                video_labels = list(self._yt_combo_opts.keys()) if hasattr(self, "_yt_combo_opts") and self._yt_combo_opts \
                               else ["Sem formatos combinados"]

            self.yt_vq.configure(values=video_labels)
            self.yt_vq.set(video_labels[0])
            self._vq_frame.pack(side="left", padx=(0, 20))

            if ff:
                self.yt_aq.configure(values=audio_labels)
                self.yt_aq.set(previous_audio if previous_audio in audio_labels else audio_labels[0])
                self._aq_frame.pack(side="left")

        self._refresh_subtitles()

    # ── Download ───────────────────────────────────────────────────────────

    def _start_yt_download(self):
        url = self.yt_url.get().strip()
        if not url:
            return
        if url != self._yt_analyzed_url:
            self._set_status(self.yt_status, "O link mudou. Clique em Analisar novamente.", "orange")
            return
        selection = None
        if self.cut_enabled.get():
            try:
                if self._yt_is_playlist:
                    raise ValueError("Recorte disponível somente para vídeos individuais.")
                selection = validate_range(self.cut_start.get(), self.cut_end.get(), self._cut_duration)
            except ValueError as exc:
                self._set_status(self.yt_status, str(exc), "orange")
                return
        subtitle = None
        if self.sub_enabled.get():
            subtitle = dict(self._sub_choices[self.sub_lang.get()], size=self.sub_size.get(), color=self.sub_color.get())
        settings = (self.yt_type.get(), self.yt_vq.get(), self.yt_aq.get(), selection, subtitle)
        self._yt_busy = True
        self.yt_url.configure(state="disabled")
        self.yt_type.configure(state="disabled")
        self.yt_vq.configure(state="disabled")
        self.yt_aq.configure(state="disabled")
        self._refresh_cut()
        self.yt_btn.configure(state="disabled", text="Baixando…")
        self.yt_analyze_btn.configure(state="disabled")
        self.yt_bar.set(0)
        self._set_status(self.yt_status, "Iniciando download…")
        threading.Thread(target=self._dl_yt, args=(url, settings), daemon=True).start()

    def _dl_yt(self, url, settings):
        dl_type, vq_label, aq_label, selection, subtitle = settings
        ff       = has_ffmpeg()

        def progress_hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                if total:
                    self.yt_bar.set(downloaded / total)
                pct = d.get("_percent_str", "").strip()
                spd = d.get("_speed_str", "").strip()
                self._log(self.yt_log, f"{pct}  {spd}")
                self._set_status(self.yt_status, f"Baixando {pct}")
            elif d["status"] == "finished":
                self.yt_bar.set(1)
                self._log(self.yt_log, f"✓  {os.path.basename(d['filename'])}")

        is_pl = getattr(self, "_yt_is_playlist", False)

        # Template de saída: playlist gera subpasta própria
        if is_pl:
            outtmpl = os.path.join(DOWNLOADS_FOLDER,
                                   "%(playlist_title)s", "%(playlist_index)02d - %(title)s.%(ext)s")
        else:
            outtmpl = os.path.join(DOWNLOADS_FOLDER, "%(title)s.%(ext)s")

        if selection:
            a,b = selection
            suffix = f" [trecho {clock(a).replace(':','-')}_{clock(b).replace(':','-')}]"
            outtmpl = os.path.join(DOWNLOADS_FOLDER, "%(title)s" + suffix + ".%(ext)s")

        if not is_pl and dl_type != "Só Vídeo":
            outtmpl = outtmpl.replace('.%(ext)s', audio_suffix((self._yt_info or {}).get('formats', []),
                self._yt_audio_opts.get(aq_label)) + '.%(ext)s')
        if subtitle:
            suffix = f" [legenda {subtitle['code']} {subtitle['color']} {subtitle['size']}]"
            outtmpl = outtmpl.replace('.%(ext)s', suffix + '.%(ext)s')

        # Contador de vídeos para playlists
        _pl_counter = [0]

        def progress_hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                if total:
                    self.yt_bar.set(downloaded / total)
                pct = d.get("_percent_str", "").strip()
                spd = d.get("_speed_str", "").strip()

                if is_pl:
                    idx = d.get("info_dict", {}).get("playlist_index") or _pl_counter[0]
                    n   = d.get("info_dict", {}).get("n_entries", "?")
                    self._set_status(self.yt_status, f"Vídeo {idx}/{n} — {pct}  {spd}")
                else:
                    self._log(self.yt_log, f"{pct}  {spd}")
                    self._set_status(self.yt_status, f"Baixando {pct}")

            elif d["status"] == "finished":
                self.yt_bar.set(1)
                _pl_counter[0] += 1
                self._log(self.yt_log, f"✓  {os.path.basename(d['filename'])}")

        ydl_opts = {
            "outtmpl": outtmpl,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
        }
        ffp = get_ffmpeg_path()
        if ffp:
            ydl_opts["ffmpeg_location"] = os.path.dirname(ffp)

        try:
            if dl_type == "Só Áudio":
                if ff:
                    kbps = self._yt_audio_opts.get(aq_label) or aq_label.split()[0] if is_pl \
                           else (self._yt_audio_opts.get(aq_label) or "0")
                    ydl_opts["format"] = audio_selector(None if is_pl else self._yt_audio_opts.get(aq_label))
                    ydl_opts["writethumbnail"] = True
                    ydl_opts["postprocessors"] = [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": kbps if is_pl else "0",
                    }]
                else:
                    audio_fid = getattr(self, "_yt_audio_opts", {}).get(aq_label)
                    ydl_opts["format"] = audio_fid or "bestaudio[ext=m4a]/bestaudio"
                    self._log(self.yt_log, "⚠  Sem ffmpeg — áudio no formato original.\n")

            elif dl_type == "Só Vídeo":
                if is_pl:
                    h = self._yt_video_opts.get(vq_label)
                    ydl_opts["format"] = f"bestvideo[height<={h}]/bestvideo" if h else "bestvideo"
                else:
                    video_fid = getattr(self, "_yt_video_opts", {}).get(vq_label)
                    ydl_opts["format"] = video_fid or "bestvideo"

            else:  # Vídeo + Áudio
                if ff:
                    if is_pl:
                        h = self._yt_video_opts.get(vq_label)
                        if h:
                            ydl_opts["format"] = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"
                        else:
                            ydl_opts["format"] = "bestvideo+bestaudio/best"
                    else:
                        video_fid = getattr(self, "_yt_video_opts", {}).get(vq_label)
                        audio_fid = getattr(self, "_yt_audio_opts", {}).get(aq_label)
                        ydl_opts["format"] = combined_selector(video_fid, audio_fid)
                    ydl_opts["merge_output_format"] = "mp4"
                else:
                    combo_fid = getattr(self, "_yt_combo_opts", {}).get(vq_label)
                    if not combo_fid and not is_pl:
                        self._set_status(self.yt_status,
                                         "⚠  ffmpeg necessário — clique em '⬇ Instalar ffmpeg' no topo.",
                                         "#e67e22")
                        self._log(self.yt_log,
                                  "✗  Este vídeo não tem formato combinado.\n"
                                  "   Clique em '⬇ Instalar ffmpeg' no cabeçalho.\n")
                        return
                    ydl_opts["format"] = combo_fid or "best"
                    if not ff:
                        self._log(self.yt_log, "⚠  Sem ffmpeg — usando formato combinado disponível.\n")

            if subtitle:
                ydl_opts.update(writesubtitles=not subtitle['automatic'],
                    writeautomaticsub=subtitle['automatic'], subtitleslangs=[subtitle['code']],
                    subtitlesformat='json3/vtt/srt', overwrites=True)
            extract_options = None
            if selection:
                ydl_opts["overwrites"] = True
                self._log(self.yt_log, "Baixando o arquivo completo antes do recorte preciso.")
                if dl_type == "Só Áudio":
                    extract_options = ydl_opts.pop("postprocessors")[0]
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if selection or subtitle:
                    def cut_log(message):
                        self._log(self.yt_log, message)
                        self._set_status(self.yt_status, "Gravando legendas…" if subtitle else "Recortando trecho…")
                    ydl.add_post_processor(ClipMediaPP(ydl, *(selection or (0, None)),
                        ffmpeg=get_ffmpeg_path(), audio_only=dl_type == "Só Áudio", log=cut_log, subtitles=subtitle))
                    if extract_options:
                        ydl.add_post_processor(FFmpegExtractAudioPP(ydl, preferredcodec="mp3",
                            preferredquality=extract_options["preferredquality"]))
                if dl_type == "Só Áudio" and ff:
                    ydl.add_post_processor(MusicMetadataPP(
                        ydl, log=lambda message: self._log(self.yt_log, message)))
                ydl.download([url])

            if is_pl:
                dest = os.path.join(DOWNLOADS_FOLDER, self._yt_info.get("title", "playlist"))
                self._set_status(self.yt_status,
                                 f"✓  {_pl_counter[0]} vídeo(s) baixado(s)!", "#2ecc71")
                self._log(self.yt_log, f"Salvo em: {dest}\n")
            else:
                self._set_status(self.yt_status, "✓  Download concluído!", "#2ecc71")
                self._log(self.yt_log, f"Salvo em: {DOWNLOADS_FOLDER}\n")

        except Exception as exc:
            self._set_status(self.yt_status, f"✗  {str(exc)[:80]}", "#e74c3c")
            self._log(self.yt_log, f"ERRO: {exc}\n")
        finally:
            self.after(0, self._finish_yt_download)

    # ── YouTube Music tab ──────────────────────────────────────────────────

    def _build_ytmusic_tab(self):
        tab = self.tabview.tab("  YT Music  ")

        self._ytm_is_playlist = False
        self._ytm_audio_opts  = {}   # label -> format_id

        # ── URL + Analisar ──────────────────────────────────────────────────
        ctk.CTkLabel(tab, text="URL do YouTube Music (música ou playlist):",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", padx=12, pady=(12, 2))

        url_row = ctk.CTkFrame(tab, fg_color="transparent")
        url_row.pack(fill="x", padx=12, pady=(0, 6))

        self.ytm_url = ctk.CTkEntry(
            url_row, height=36,
            placeholder_text="https://music.youtube.com/watch?v=...  ou  /playlist?list=...",
        )
        self._install_paste_menu(self.ytm_url)
        self.ytm_url.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.ytm_url.bind("<Return>", lambda _: self._start_ytm_analyze())

        self.ytm_analyze_btn = ctk.CTkButton(
            url_row, text="🔍  Analisar", width=110, height=36,
            font=ctk.CTkFont(size=13),
            fg_color="#2a5caa", hover_color="#1e4080",
            command=self._start_ytm_analyze,
        )
        self.ytm_analyze_btn.pack(side="left")

        # ── Info da faixa/playlist ──────────────────────────────────────────
        self._ytm_info_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self._ytm_info_frame.pack(fill="x", padx=12, pady=(0, 2))
        self._ytm_title_label = ctk.CTkLabel(
            self._ytm_info_frame, text="", font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#aaaaaa", anchor="w", wraplength=720,
        )
        self._ytm_title_label.pack(anchor="w")

        # ── Opções (oculto até analisar) ────────────────────────────────────
        self._ytm_opts_frame = ctk.CTkFrame(tab, fg_color="transparent")

        # Linha 1: stream de áudio real + formato de saída
        row1 = ctk.CTkFrame(self._ytm_opts_frame, fg_color="transparent")
        row1.pack(fill="x", pady=(4, 2))

        ctk.CTkLabel(row1, text="Stream:").pack(side="left", padx=(0, 6))
        self.ytm_stream = ctk.CTkOptionMenu(row1, values=["—"], width=230)
        self.ytm_stream.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(row1, text="Salvar como:").pack(side="left", padx=(0, 6))
        self.ytm_fmt = ctk.CTkOptionMenu(
            row1, values=["MP3", "M4A", "WAV", "FLAC"],
            width=100, command=self._on_ytm_fmt_change,
        )
        self.ytm_fmt.set("MP3")
        self.ytm_fmt.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(row1, text="Bitrate:").pack(side="left", padx=(0, 6))
        self.ytm_bitrate = ctk.CTkOptionMenu(
            row1, values=["320 kbps", "256 kbps", "192 kbps", "128 kbps"], width=120,
        )
        self.ytm_bitrate.set("320 kbps")
        self.ytm_bitrate.pack(side="left")

        # Linha 2: extras
        row2 = ctk.CTkFrame(self._ytm_opts_frame, fg_color="transparent")
        row2.pack(fill="x", pady=(2, 4))

        self.ytm_embed_meta = ctk.CTkCheckBox(row2, text="Metadados",
                                               font=ctk.CTkFont(size=12))
        self.ytm_embed_meta.pack(side="left", padx=(0, 16))
        self.ytm_embed_meta.select()

        self.ytm_embed_thumb = ctk.CTkCheckBox(row2, text="Capa do álbum",
                                                font=ctk.CTkFont(size=12))
        self.ytm_embed_thumb.pack(side="left")
        self.ytm_embed_thumb.select()

        # ── Botão Baixar ────────────────────────────────────────────────────
        self.ytm_btn = ctk.CTkButton(
            tab, text="⬇   Baixar", width=720, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#cc0000", hover_color="#990000",
            command=self._start_ytm, state="disabled",
        )
        self.ytm_btn.pack(padx=12, pady=8)

        self.ytm_bar = ctk.CTkProgressBar(tab, width=720)
        self.ytm_bar.pack(padx=12, pady=(0, 4))
        self.ytm_bar.set(0)

        self.ytm_status = ctk.CTkLabel(tab, text="Cole um link e clique em Analisar.",
                                        text_color="#888888", font=ctk.CTkFont(size=11))
        self.ytm_status.pack(anchor="w", padx=14)

        self._build_dest_row(tab)

        self.ytm_log = ctk.CTkTextbox(tab, width=720, height=155,
                                       font=ctk.CTkFont(size=10, family="Consolas"))
        self.ytm_log.pack(padx=12, pady=6)
        self.ytm_log.configure(state="disabled")

    def _on_ytm_fmt_change(self, fmt):
        if fmt in ("WAV", "FLAC"):
            self.ytm_bitrate.configure(state="disabled")
        else:
            self.ytm_bitrate.configure(state="normal")

    # ── Análise YT Music ───────────────────────────────────────────────────

    def _start_ytm_analyze(self):
        url = self.ytm_url.get().strip()
        if not url:
            self._set_status(self.ytm_status, "⚠  Cole um link válido.", "orange")
            return
        self.ytm_analyze_btn.configure(state="disabled", text="Analisando…")
        self.ytm_btn.configure(state="disabled")
        self._ytm_opts_frame.pack_forget()
        self._ytm_title_label.configure(text="")
        self.ytm_bar.set(0)
        self._set_status(self.ytm_status, "Analisando link…")
        self._ytm_audio_opts.clear()
        threading.Thread(target=self._ytm_analyze, args=(url,), daemon=True).start()

    def _ytm_analyze(self, url):
        try:
            is_pl = self._url_is_playlist(url)
            self._ytm_is_playlist = is_pl

            if is_pl:
                opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                title    = info.get("title", "Playlist")
                uploader = info.get("uploader", info.get("channel", ""))
                count    = len(info.get("entries") or [])
                # Para playlists, streams genéricos ordenados por qualidade
                self._ytm_audio_opts = {
                    "Melhor disponível (opus/webm)": None,
                    "Melhor m4a": None,
                    "251 — opus ~130kbps  (webm)": "251",
                    "140 — aac  ~128kbps  (m4a)":  "140",
                }
                self.after(0, lambda: self._update_ytm_ui(title, uploader, "", count))
            else:
                opts = {"quiet": True, "no_warnings": True}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)

                title    = info.get("title", "")
                uploader = info.get("uploader", info.get("channel", ""))
                duration = info.get("duration_string", "")
                formats  = info.get("formats", [])

                audio_opts = {}
                for f in formats:
                    if (f.get("vcodec", "none") or "none") != "none":
                        continue  # pula streams com vídeo
                    acodec = f.get("acodec", "none") or "none"
                    if acodec == "none":
                        continue
                    abr  = f.get("abr") or f.get("tbr") or 0
                    ext  = f.get("ext", "")
                    fid  = f["format_id"]
                    note = f.get("format_note", "")
                    label = f"{fid} — {acodec}  ~{int(abr)}kbps  ({ext})"
                    if note:
                        label += f"  [{note}]"
                    audio_opts[label] = (fid, abr)

                # Ordena por bitrate decrescente
                sorted_keys = sorted(audio_opts, key=lambda k: audio_opts[k][1], reverse=True)
                self._ytm_audio_opts = {k: audio_opts[k][0] for k in sorted_keys}

                self.after(0, lambda: self._update_ytm_ui(title, uploader, duration))

        except Exception as exc:
            self.after(0, lambda message=str(exc): self._ytm_analyze_error(message))

    def _update_ytm_ui(self, title, uploader, duration, count=0):
        self.ytm_analyze_btn.configure(state="normal", text="🔍  Analisar")

        if count:
            info_text = f"📋  Playlist  •  {count} faixas\n{title}"
            if uploader:
                info_text += f"  —  {uploader}"
            self._ytm_title_label.configure(text=info_text, text_color="#7fb3e8")
        else:
            info_text = title
            if uploader:
                info_text += f"  —  {uploader}"
            if duration:
                info_text += f"  ({duration})"
            self._ytm_title_label.configure(text=info_text, text_color="#aaaaaa")

        stream_labels = list(self._ytm_audio_opts.keys())
        self.ytm_stream.configure(values=stream_labels)
        self.ytm_stream.set(stream_labels[0] if stream_labels else "—")

        self._ytm_opts_frame.pack(fill="x", padx=12, pady=4)
        self.ytm_btn.configure(state="normal")
        self._set_status(self.ytm_status, "✓  Análise concluída. Configure e clique em Baixar.", "#2ecc71")

    def _ytm_analyze_error(self, msg):
        self.ytm_analyze_btn.configure(state="normal", text="🔍  Analisar")
        self._set_status(self.ytm_status, f"✗  {msg[:80]}", "#e74c3c")
        self._log(self.ytm_log, f"ERRO na análise: {msg}\n")

    # ── Download YT Music ──────────────────────────────────────────────────

    def _start_ytm(self):
        url = self.ytm_url.get().strip()
        if not url:
            return
        self.ytm_btn.configure(state="disabled", text="Baixando…")
        self.ytm_analyze_btn.configure(state="disabled")
        self.ytm_bar.set(0)
        self._set_status(self.ytm_status, "Iniciando…")
        threading.Thread(target=self._dl_ytm, args=(url,), daemon=True).start()

    def _dl_ytm(self, url):
        stream_label = self.ytm_stream.get()
        fmt          = self.ytm_fmt.get()
        bitrate      = self.ytm_bitrate.get().split()[0]   # "320"
        do_meta      = self.ytm_embed_meta.get()
        do_thumb     = self.ytm_embed_thumb.get()
        ff           = has_ffmpeg()
        is_pl        = self._ytm_is_playlist
        codec_map    = {"MP3": "mp3", "M4A": "m4a", "WAV": "wav", "FLAC": "flac"}
        codec        = codec_map[fmt]

        stream_fid = self._ytm_audio_opts.get(stream_label)

        _pl_counter = [0]

        def progress_hook(d):
            if d["status"] == "downloading":
                total      = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                if total:
                    self.ytm_bar.set(downloaded / total)
                pct = d.get("_percent_str", "").strip()
                spd = d.get("_speed_str", "").strip()
                if is_pl:
                    idx = d.get("info_dict", {}).get("playlist_index") or _pl_counter[0] + 1
                    n   = d.get("info_dict", {}).get("n_entries", "?")
                    self._set_status(self.ytm_status, f"Faixa {idx}/{n} — {pct}  {spd}")
                else:
                    self._log(self.ytm_log, f"{pct}  {spd}")
                    self._set_status(self.ytm_status, f"Baixando {pct}")
            elif d["status"] == "finished":
                self.ytm_bar.set(1)
                _pl_counter[0] += 1
                self._log(self.ytm_log, f"✓  {os.path.basename(d['filename'])}")

        if is_pl:
            outtmpl = os.path.join(DOWNLOADS_FOLDER,
                                   "%(playlist_title)s", "%(playlist_index)02d - %(title)s.%(ext)s")
        else:
            outtmpl = os.path.join(DOWNLOADS_FOLDER, "%(title)s.%(ext)s")

        # Resolve o seletor de formato
        if stream_fid is None:
            # Seletores genéricos para playlist ou opção "Melhor disponível"
            if "m4a" in stream_label.lower():
                fmt_sel = "bestaudio[ext=m4a]/bestaudio"
            else:
                fmt_sel = "bestaudio/best"
        else:
            fmt_sel = stream_fid

        ydl_opts = {
            "format": fmt_sel,
            "outtmpl": outtmpl,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            "writethumbnail": bool(do_thumb and ff),
        }
        ffp = get_ffmpeg_path()
        if ffp:
            ydl_opts["ffmpeg_location"] = os.path.dirname(ffp)

        postprocessors = []
        if ff:
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": bitrate if fmt == "MP3" else "0",
            })
        else:
            self._log(self.ytm_log, "⚠  Sem ffmpeg — baixando no formato original (sem conversão).\n")

        if postprocessors:
            ydl_opts["postprocessors"] = postprocessors

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if ff and (do_meta or do_thumb):
                    ydl.add_post_processor(MusicMetadataPP(
                        ydl, metadata=bool(do_meta), artwork=bool(do_thumb),
                        log=lambda message: self._log(self.ytm_log, message)))
                ydl.download([url])
            if is_pl:
                self._set_status(self.ytm_status, f"✓  {_pl_counter[0]} faixa(s) baixada(s)!", "#2ecc71")
            else:
                self._set_status(self.ytm_status, "✓  Download concluído!", "#2ecc71")
            self._log(self.ytm_log, f"Salvo em: {DOWNLOADS_FOLDER}\n")
        except Exception as exc:
            self._set_status(self.ytm_status, f"✗  {str(exc)[:80]}", "#e74c3c")
            self._log(self.ytm_log, f"ERRO: {exc}\n")
        finally:
            self.ytm_btn.configure(state="normal", text="⬇   Baixar")
            self.ytm_analyze_btn.configure(state="normal")

    # ── Spotify tab ────────────────────────────────────────────────────────

    def _build_spotify_tab(self):
        tab = self.tabview.tab("  Spotify  ")

        ctk.CTkLabel(tab, text="URL do Spotify:", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=12, pady=(12, 2)
        )
        hint = ctk.CTkLabel(tab,
            text="  Suporta:  🎵 Música  •  💿 Álbum  •  📋 Playlist",
            font=ctk.CTkFont(size=11), text_color="#888888")
        hint.pack(anchor="w", padx=12, pady=(0, 4))
        self.sp_url = ctk.CTkEntry(
            tab, width=720, height=36,
            placeholder_text="https://open.spotify.com/track/...  ou  /album/...  ou  /playlist/...",
        )
        self._install_paste_menu(self.sp_url)
        self.sp_url.pack(padx=12, pady=(0, 8))

        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(row, text="Qualidade do MP3:").pack(side="left", padx=(0, 8))
        self.sp_quality = ctk.CTkOptionMenu(row, values=["320k", "256k", "192k", "128k"], width=120)
        self.sp_quality.set("320k")
        self.sp_quality.pack(side="left")

        self.sp_btn = ctk.CTkButton(
            tab, text="⬇   Baixar", width=720, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#1DB954", hover_color="#17963f",
            command=self._start_sp,
        )
        self.sp_btn.pack(padx=12, pady=10)

        self.sp_bar = ctk.CTkProgressBar(tab, width=720, mode="indeterminate")
        self.sp_bar.pack(padx=12, pady=(0, 4))

        self.sp_status = ctk.CTkLabel(tab, text="Pronto.", text_color="#888888", font=ctk.CTkFont(size=11))
        self.sp_status.pack(anchor="w", padx=14)

        self._build_dest_row(tab)

        self.sp_log = ctk.CTkTextbox(tab, width=720, height=280,
                                      font=ctk.CTkFont(size=10, family="Consolas"))
        self.sp_log.pack(padx=12, pady=6)
        self.sp_log.configure(state="disabled")

    def _start_sp(self):
        url = self.sp_url.get().strip()
        if not url:
            self._set_status(self.sp_status, "⚠  Cole um link válido.", "orange")
            return
        self.sp_btn.configure(state="disabled", text="Baixando…")
        self.sp_bar.start()
        self._set_status(self.sp_status, "Buscando…")
        threading.Thread(target=self._dl_sp, args=(url,), daemon=True).start()

    def _dl_sp(self, url):
        quality = self.sp_quality.get()

        # Remove parâmetros de rastreamento do link (ex: ?si=...&utm_source=...)
        clean_url = url.split("?")[0].strip()

        cmd = get_spotdl_path() + ["--output", DOWNLOADS_FOLDER, "--bitrate", quality,
                                    "download", clean_url]

        # Adiciona bin/ ao PATH do subprocesso para o spotdl encontrar o ffmpeg
        env = os.environ.copy()
        bin_d = _bin_dir()
        if os.path.isdir(bin_d):
            env["PATH"] = bin_d + os.pathsep + env.get("PATH", "")

        try:
            self._log(self.sp_log, f"Baixando: {clean_url}\n")
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self._log(self.sp_log, line)
                    if any(k in line for k in ("Downloaded", "Skipping", "Found")):
                        self._set_status(self.sp_status, line[:80])
            proc.wait()
            if proc.returncode == 0:
                self._set_status(self.sp_status, "✓  Download concluído!", "#2ecc71")
                self._log(self.sp_log, f"\nSalvo em: {DOWNLOADS_FOLDER}\n")
            else:
                self._set_status(self.sp_status, "✗  Erro — veja o log.", "#e74c3c")
        except FileNotFoundError:
            self._set_status(self.sp_status, "✗  spotdl não encontrado.", "#e74c3c")
            self._log(self.sp_log, "Instale spotdl:  pip install spotdl\n")
        except Exception as exc:
            self._set_status(self.sp_status, f"✗  {exc}", "#e74c3c")
            self._log(self.sp_log, f"ERRO: {exc}\n")
        finally:
            self.sp_bar.stop()
            self.sp_bar.set(0)
            self.sp_btn.configure(state="normal", text="⬇   Baixar")

    # ── Redes Sociais tab (spike) ────────────────────────────────────────────

    def _build_social_tab(self):
        tab = self.tabview.tab("  Redes Sociais  ")

        ctk.CTkLabel(tab, text="URL da rede social:", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=12, pady=(12, 2)
        )
        ctk.CTkLabel(tab,
            text="  Suporta:  ▶ TikTok  •  🐦 Twitter/X  •  📸 Instagram  •  👍 Facebook",
            font=ctk.CTkFont(size=11), text_color="#888888").pack(anchor="w", padx=12, pady=(0, 4))

        self.social_url = ctk.CTkEntry(
            tab, width=720, height=36,
            placeholder_text="Cole o link do post, vídeo ou perfil…",
        )
        self._install_paste_menu(self.social_url)
        self.social_url.pack(padx=12, pady=(0, 4))
        self.social_url.bind("<KeyRelease>", self._on_social_url_change)

        # Badge que identifica a plataforma do link colado
        self.social_platform_lbl = ctk.CTkLabel(
            tab, text="Cole um link para detectar a plataforma.",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#888888")
        self.social_platform_lbl.pack(anchor="w", padx=14, pady=(0, 6))

        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(row, text="Tipo:").pack(side="left", padx=(0, 8))
        self.social_mode = ctk.CTkOptionMenu(
            row, values=["Vídeo", "Fotos / galeria"], width=160,
            command=lambda _=None: self._on_social_url_change())
        self.social_mode.set("Vídeo")
        self.social_mode.pack(side="left", padx=(0, 16))

        self.social_vq_lbl = ctk.CTkLabel(row, text="Qualidade:")
        self.social_vq_lbl.pack(side="left", padx=(0, 8))
        self.social_vq = ctk.CTkOptionMenu(
            row, values=["Melhor", "1080p", "720p", "480p"], width=120)
        self.social_vq.set("Melhor")
        self.social_vq.pack(side="left")

        self.social_btn = ctk.CTkButton(
            tab, text="⬇   Baixar", width=720, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start_social,
        )
        self.social_btn.pack(padx=12, pady=10)

        self.social_bar = ctk.CTkProgressBar(tab, width=720, mode="indeterminate")
        self.social_bar.pack(padx=12, pady=(0, 4))

        self.social_status = ctk.CTkLabel(tab, text="Pronto.", text_color="#888888",
                                          font=ctk.CTkFont(size=11))
        self.social_status.pack(anchor="w", padx=14)

        self._build_dest_row(tab)

        self.social_log = ctk.CTkTextbox(tab, width=720, height=230,
                                          font=ctk.CTkFont(size=10, family="Consolas"))
        self.social_log.pack(padx=12, pady=6)
        self.social_log.configure(state="disabled")

    def _on_social_url_change(self, _event=None):
        url = self.social_url.get().strip()
        # Qualidade só faz sentido para vídeo
        is_video = self.social_mode.get() == "Vídeo"
        state = "normal" if is_video else "disabled"
        self.social_vq.configure(state=state)
        self.social_vq_lbl.configure(text_color=self._fg_text if is_video else INACTIVE_TEXT)

        if not url:
            self.social_platform_lbl.configure(
                text="Cole um link para detectar a plataforma.", text_color="#888888")
            return
        label, color = detect_social_platform(url)
        if label:
            self.social_platform_lbl.configure(text=f"●  {label} detectado", text_color=color)
        else:
            self.social_platform_lbl.configure(
                text="⚠  Plataforma não reconhecida — o download pode não funcionar.",
                text_color="#e67e22")

    def _start_social(self):
        url = self.social_url.get().strip()
        if not url:
            self._set_status(self.social_status, "⚠  Cole um link válido.", "orange")
            return
        mode = self.social_mode.get()
        if mode.startswith("Fotos") and not has_gallery_dl():
            self._set_status(self.social_status, "✗  gallery-dl não encontrado.", "#e74c3c")
            self._log(self.social_log, "Para baixar fotos/galerias, instale o gallery-dl:\n"
                                       "   pip install gallery-dl\n")
            return
        settings = (mode, self.social_vq.get())
        self.social_btn.configure(state="disabled", text="Baixando…")
        self.social_bar.start()
        self._set_status(self.social_status, "Iniciando…")
        threading.Thread(target=self._dl_social, args=(url, settings), daemon=True).start()

    def _dl_social(self, url, settings):
        mode, vq = settings
        label, _ = detect_social_platform(url)
        try:
            if mode.startswith("Fotos"):
                self._dl_social_photos(url)
            else:
                self._dl_social_video(url, vq, label)
        except Exception as exc:
            self._set_status(self.social_status, f"✗  {str(exc)[:80]}", "#e74c3c")
            self._log(self.social_log, f"ERRO: {exc}\n")
        finally:
            self.social_bar.stop()
            self.social_bar.set(0)
            self.social_btn.configure(state="normal", text="⬇   Baixar")

    def _dl_social_video(self, url, vq, label):
        fmt_map = {
            "Melhor": "bestvideo*+bestaudio/best",
            "1080p":  "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "720p":   "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
            "480p":   "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
        }
        outtmpl = os.path.join(DOWNLOADS_FOLDER, "%(uploader,uploader_id|rede)s - %(title).60B [%(id)s].%(ext)s")

        def progress_hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                if total:
                    self.social_bar.configure(mode="determinate")
                    self.social_bar.set(d.get("downloaded_bytes", 0) / total)
                pct = d.get("_percent_str", "").strip()
                spd = d.get("_speed_str", "").strip()
                self._set_status(self.social_status, f"Baixando {pct}  {spd}")
            elif d["status"] == "finished":
                self.social_bar.set(1)
                self._log(self.social_log, f"✓  {os.path.basename(d['filename'])}")

        ydl_opts = {
            "outtmpl": outtmpl,
            "format": fmt_map.get(vq, "best"),
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
            "noplaylist": False,
            "quiet": True,
            "no_warnings": True,
        }
        ffp = get_ffmpeg_path()
        if ffp:
            ydl_opts["ffmpeg_location"] = os.path.dirname(ffp)

        self._log(self.social_log, f"Baixando vídeo de {label or 'link'}: {url}\n")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        self._set_status(self.social_status, "✓  Download concluído!", "#2ecc71")
        self._log(self.social_log, f"Salvo em: {DOWNLOADS_FOLDER}\n")

    def _dl_social_photos(self, url):
        dest = os.path.join(DOWNLOADS_FOLDER, "Redes Sociais")
        cmd = get_gallery_dl_path() + ["--dest", dest, url]

        env = os.environ.copy()
        bin_d = _bin_dir()
        if os.path.isdir(bin_d):
            env["PATH"] = bin_d + os.pathsep + env.get("PATH", "")

        self._log(self.social_log, f"Baixando fotos/galeria: {url}\n")
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        count = 0
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            self._log(self.social_log, line)
            # gallery-dl imprime o caminho de cada arquivo salvo (começa com ./ ou a pasta)
            if line.lstrip().startswith(("/", ".", dest)) or re.search(r"\.(jpe?g|png|webp|mp4|gif)$", line, re.I):
                count += 1
                self._set_status(self.social_status, f"Baixados {count} arquivo(s)…")
        proc.wait()
        if proc.returncode == 0:
            self._set_status(self.social_status, f"✓  Concluído — {count} arquivo(s).", "#2ecc71")
            self._log(self.social_log, f"\nSalvo em: {dest}\n")
        else:
            self._set_status(self.social_status, "✗  Erro — veja o log.", "#e74c3c")


if __name__ == "__main__":
    app = DownloaderApp()
    app.mainloop()
