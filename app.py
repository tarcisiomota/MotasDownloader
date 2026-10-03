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
import json
from tkinter import filedialog
from pathlib import Path
from audio_options import audio_options, audio_selector, combined_selector, audio_suffix
from subtitles import subtitle_choices, SIZES
from music_metadata import MusicMetadataPP
from clip_media import ClipMediaPP, clock, validate_range, parse_clock
import media_library
import media_editor
import timeline_editor
from yt_dlp.postprocessor.ffmpeg import FFmpegExtractAudioPP

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DOWNLOADS_FOLDER = str(Path.home() / "Downloads")

def _config_path():
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "MotasDownloader" / "config.json"

def load_config():
    try:
        return json.loads(_config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_config(data):
    try:
        path = _config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

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
        self.geometry("1120x780")
        self.resizable(True, True)
        self.minsize(980, 700)
        self._is_dark = True

        # Pasta de download persistida (sobrepõe o padrão definido na inicialização).
        self._dest_labels = []
        saved_folder = load_config().get("download_folder")
        if saved_folder and os.path.isdir(saved_folder):
            global DOWNLOADS_FOLDER
            DOWNLOADS_FOLDER = saved_folder

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
        self.tabview = ctk.CTkTabview(self, width=1100, height=700, anchor="nw")
        self.tabview.pack(padx=10, pady=8, fill="both", expand=True)
        self.tabview.add("  YouTube  ")
        self.tabview.add("  YT Music  ")
        self.tabview.add("  Spotify  ")
        self.tabview.add("  Redes Sociais  ")
        self.tabview.add("  Biblioteca  ")
        self.tabview.add("  Editar Vídeo  ")

        self._yt_formats     = {}    # format_id -> format dict (from yt-dlp)
        self._yt_info        = None  # full info dict
        self._yt_is_playlist = False # True when analyzed URL is a playlist

        self._build_youtube_tab()
        self._build_ytmusic_tab()
        self._build_spotify_tab()
        self._build_social_tab()
        self._build_library_tab()
        self._build_edit_video_tab()

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
        os.makedirs(DOWNLOADS_FOLDER, exist_ok=True)
        os.startfile(DOWNLOADS_FOLDER)

    def _choose_folder(self):
        global DOWNLOADS_FOLDER
        folder = filedialog.askdirectory(
            initialdir=DOWNLOADS_FOLDER if os.path.isdir(DOWNLOADS_FOLDER) else None,
            title="Escolha a pasta de download")
        if not folder:
            return
        DOWNLOADS_FOLDER = os.path.normpath(folder)
        for label in self._dest_labels:
            label.configure(text=f"📁  Salvando em:  {DOWNLOADS_FOLDER}")
        cfg = load_config()
        cfg["download_folder"] = DOWNLOADS_FOLDER
        save_config(cfg)

    def _mask_time(self, event, entry, var):
        # Formata digitação livre em HH:MM:SS inserindo os dois-pontos automaticamente.
        if event.keysym in ("Left", "Right", "Up", "Down", "Home", "End", "Tab",
                             "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return
        raw = var.get()
        try:
            cursor = entry.index("insert")
        except Exception:
            cursor = len(raw)
        digits_before = len(re.sub(r"\D", "", raw[:cursor]))
        digits = re.sub(r"\D", "", raw)[:6]
        parts = [digits[0:2], digits[2:4], digits[4:6]]
        formatted = ":".join(p for p in parts if p)
        if formatted == raw:
            return
        var.set(formatted)
        pos, seen = 0, 0
        for i, ch in enumerate(formatted):
            if seen >= digits_before:
                break
            pos = i + 1
            if ch.isdigit():
                seen += 1
        entry.icursor(pos if digits_before else 0)

    def _tab_content(self, raw_tab, width=760):
        # Mantém os formulários numa coluna de largura fixa, centralizada na
        # janela widescreen (as colunas laterais absorvem o espaço extra).
        raw_tab.grid_columnconfigure(0, weight=1)
        raw_tab.grid_columnconfigure(1, minsize=width)
        raw_tab.grid_columnconfigure(2, weight=1)
        raw_tab.grid_rowconfigure(0, weight=1)
        inner = ctk.CTkFrame(raw_tab, fg_color="transparent")
        inner.grid(row=0, column=1, sticky="nsew")
        return inner

    def _build_dest_row(self, tab):
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(anchor="w", padx=14, pady=(4, 0))
        label = ctk.CTkLabel(row, text=f"📁  Salvando em:  {DOWNLOADS_FOLDER}",
                             text_color="#888888", font=ctk.CTkFont(size=10))
        label.pack(side="left")
        self._dest_labels.append(label)
        ctk.CTkButton(row, text="↗", width=24, height=22,
                      fg_color="transparent", hover_color="#2a2a4e",
                      border_width=1, border_color="#555577", text_color="#aaaacc",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._open_downloads).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Alterar…", width=62, height=22,
                      fg_color="transparent", hover_color="#2a2a4e",
                      border_width=1, border_color="#555577", text_color="#aaaacc",
                      font=ctk.CTkFont(size=11),
                      command=self._choose_folder).pack(side="left")

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

        # ── Biblioteca ────────────────────────────────────────────────────
        section("🎵  Biblioteca", "#2e8b57")
        line("Toca os áudios e vídeos que você baixou, sem sair do app.")
        line("1. A lista mostra as mídias da pasta de downloads (🔄 Atualizar recarrega).")
        line("2. Clique numa faixa para tocar; use ⏮ ⏯ ⏹ ⏭, a barra de progresso e o volume.")
        line("3. Vídeos tocam na janela embutida; o áudio avança sozinho para a próxima faixa.")
        line("ℹ  Usa o componente de vídeo (libVLC). Se faltar, há um botão para instalar.")

        # ── Editar Vídeo ────────────────────────────────────────────────────
        section("🎬  Editar Vídeo", "#3b6fb0")
        line("Editor em linha do tempo (timeline) com trilhas, parecido com o Premiere.")
        line("1. ➕ Vídeo / ➕ Áudio adicionam clipes nas trilhas (V1, A1, A2).")
        line("2. Ferramenta ▶ Selecionar: arraste o meio do bloco para mover (no tempo e")
        line("   entre trilhas); arraste as pontas para aparar início/fim.", 1)
        line("3. Ferramenta ✂ Cortar: clique nela e depois no clipe para dividir ali.")
        line("   Para cortar de novo, clique em ✂ Cortar outra vez.", 1)
        line("4. Clique na régua para mover o playhead; o Program Monitor mostra o quadro.")
        line("5. Efeitos por clipe: selecione um clipe, escolha o Efeito e ＋ Aplicar.")
        line("• Velocidade, Reverter, Girar, Espelhar, Preto e branco, Inverter cores,", 1)
        line("  Brilho/Contraste, Fade e Texto/Legenda. Removível no painel do clipe.", 1)
        line("6. ⬇ Exportar MP4 renderiza a sequência inteira com os efeitos.")
        line("ℹ  O preview é por quadro (scrub), sem áudio ao vivo; o áudio sai na exportação.")

        # ── Geral ─────────────────────────────────────────────────────────
        section("⚙  Geral", "#888888")
        line("📁  Downloads — abre a pasta de destino (padrão: Downloads, dentro da pasta do programa).")
        line("Alterar… — escolhe outra pasta de download; a escolha fica salva entre sessões.")
        line("Nos campos de tempo (Início/Fim), digite só números: 012345 vira 01:23:45.")
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

    # ── Biblioteca / Player ──────────────────────────────────────────────────

    @staticmethod
    def _fmt_ms(ms):
        s = int(max(0, ms) / 1000)
        return f"{s // 60:02d}:{s % 60:02d}"

    @staticmethod
    def _trim(text, n):
        return text if len(text) <= n else text[:n - 1] + "…"

    def _build_library_tab(self):
        tab = self.tabview.tab("  Biblioteca  ")
        self._lib_player = None
        self._lib_items = []
        self._lib_current = -1
        self._lib_row_widgets = []
        self._lib_poll_active = False
        self._build_dest_row(tab)
        self._lib_body = ctk.CTkFrame(tab, fg_color="transparent")
        self._lib_body.pack(fill="both", expand=True, padx=12, pady=(8, 10))
        self._render_library()

    def _render_library(self):
        for widget in self._lib_body.winfo_children():
            widget.destroy()
        if not media_library.has_vlc(_bin_dir()):
            self._render_library_missing()
            return
        vlc = media_library.load_vlc(_bin_dir())
        if vlc is None:
            self._render_library_missing(error="O componente de vídeo não pôde ser carregado.")
            return
        if self._lib_player is None:
            try:
                self._lib_player = media_library.MediaLibraryPlayer(vlc)
            except Exception as exc:
                self._render_library_missing(error=f"Falha ao iniciar o player: {exc}")
                return
        self._build_player_ui(self._lib_body)
        self._scan_library()
        if not self._lib_poll_active:
            self._lib_poll_active = True
            self.after(500, self._poll_player)

    def _render_library_missing(self, error=None):
        box = ctk.CTkFrame(self._lib_body, fg_color="transparent")
        box.pack(expand=True)
        ctk.CTkLabel(box, text="🎬  Player de mídia", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(40, 8))
        msg = ("Para tocar os áudios e vídeos baixados aqui dentro, é preciso\n"
               "instalar o componente de vídeo (libVLC, ~77 MB). Isso é feito\n"
               "uma única vez e fica guardado no aplicativo.")
        if error:
            msg = error + "\n\n" + msg
        ctk.CTkLabel(box, text=msg, font=ctk.CTkFont(size=12),
                     text_color="#aaaaaa", justify="center").pack(pady=(0, 16))
        self._lib_install_btn = ctk.CTkButton(
            box, text="⬇   Instalar player de mídia", width=260, height=42,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._install_vlc)
        self._lib_install_btn.pack()
        self._lib_install_status = ctk.CTkLabel(box, text="", font=ctk.CTkFont(size=11),
                                                text_color="#888888")
        self._lib_install_status.pack(pady=(10, 0))
        self._lib_install_bar = ctk.CTkProgressBar(box, width=300)

    def _install_vlc(self):
        self._lib_install_btn.configure(state="disabled", text="Instalando…")
        self._lib_install_bar.pack(pady=(8, 0))
        self._lib_install_bar.set(0)

        def _progress(pct, message):
            self.after(0, lambda: self._lib_install_bar.set(pct))
            self.after(0, lambda: self._lib_install_status.configure(text=message))

        def _run():
            try:
                media_library.download_vlc(_bin_dir(), progress_cb=_progress)
                self.after(200, self._render_library)
            except Exception as exc:
                self.after(0, lambda exc=exc: self._lib_install_status.configure(
                    text=f"✗ Erro: {exc}", text_color="#e74c3c"))
                self.after(0, lambda: self._lib_install_btn.configure(
                    state="normal", text="⬇   Tentar novamente"))

        threading.Thread(target=_run, daemon=True).start()

    def _build_player_ui(self, parent):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(header, text="🎵  Biblioteca", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        self._lib_count = ctk.CTkLabel(header, text="", font=ctk.CTkFont(size=11), text_color="#888888")
        self._lib_count.pack(side="left", padx=10)
        ctk.CTkButton(header, text="🔄 Atualizar", width=100, height=26,
                      command=self._scan_library).pack(side="right")

        split = ctk.CTkFrame(parent, fg_color="transparent")
        split.pack(fill="both", expand=True, pady=(8, 0))
        self._lib_list = ctk.CTkScrollableFrame(split, width=270)
        self._lib_list.pack(side="left", fill="y")
        self._lib_video = tk.Frame(split, bg="black", width=420, height=250)
        self._lib_video.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self._lib_video.pack_propagate(False)

        self._lib_now = ctk.CTkLabel(parent, text="Nada tocando", anchor="w",
                                     font=ctk.CTkFont(size=12, weight="bold"))
        self._lib_now.pack(fill="x", pady=(8, 2))

        seekrow = ctk.CTkFrame(parent, fg_color="transparent")
        seekrow.pack(fill="x")
        self._lib_elapsed = ctk.CTkLabel(seekrow, text="00:00", width=46, font=ctk.CTkFont(size=11))
        self._lib_elapsed.pack(side="left")
        self._lib_seek = ctk.CTkSlider(seekrow, from_=0, to=1000, command=self._on_seek)
        self._lib_seek.set(0)
        self._lib_seek.pack(side="left", fill="x", expand=True, padx=6)
        self._lib_total = ctk.CTkLabel(seekrow, text="00:00", width=46, font=ctk.CTkFont(size=11))
        self._lib_total.pack(side="left")

        controls = ctk.CTkFrame(parent, fg_color="transparent")
        controls.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(controls, text="⏮", width=46, command=self._lib_prev).pack(side="left", padx=4)
        self._lib_play_btn = ctk.CTkButton(controls, text="▶", width=64, command=self._lib_toggle_play)
        self._lib_play_btn.pack(side="left", padx=4)
        ctk.CTkButton(controls, text="⏹", width=46, command=self._lib_stop).pack(side="left", padx=4)
        ctk.CTkButton(controls, text="⏭", width=46, command=self._lib_next).pack(side="left", padx=4)
        ctk.CTkLabel(controls, text="🔊", font=ctk.CTkFont(size=14)).pack(side="left", padx=(22, 4))
        self._lib_vol = ctk.CTkSlider(controls, from_=0, to=100, width=120, command=self._on_volume)
        self._lib_vol.set(70)
        self._lib_vol.pack(side="left")
        self.after(300, lambda: self._lib_player.set_output(self._lib_video.winfo_id()))
        self._lib_player.set_volume(70)

    def _scan_library(self):
        self._lib_items = media_library.scan_library(DOWNLOADS_FOLDER)
        self._lib_count.configure(text=f"{len(self._lib_items)} arquivo(s)")
        for widget in self._lib_list.winfo_children():
            widget.destroy()
        self._lib_row_widgets = []
        if not self._lib_items:
            ctk.CTkLabel(self._lib_list, justify="left", text_color="#888888",
                         font=ctk.CTkFont(size=11),
                         text="Nenhuma mídia nesta pasta.\nBaixe algo nas outras abas\nou troque a pasta acima.").pack(
                anchor="w", padx=4, pady=10)
            return
        for idx, item in enumerate(self._lib_items):
            icon = "🎬" if item["is_video"] else "🎵"
            label = (f'{item["artist"]} — {item["title"]}' if item["artist"] else item["title"])
            btn = ctk.CTkButton(
                self._lib_list, text=self._trim(f"{icon} {label}", 34), anchor="w", height=30,
                fg_color="transparent", hover_color=("#dddddd", "#333355"),
                text_color=("#202124", "#dddddd"),
                command=lambda i=idx: self._lib_play_index(i))
            btn.pack(fill="x", pady=1)
            self._lib_row_widgets.append(btn)
        self._highlight_current()

    def _highlight_current(self):
        for i, btn in enumerate(self._lib_row_widgets):
            btn.configure(fg_color=("#c4d0f5", "#39416b") if i == self._lib_current else "transparent")

    def _lib_play_index(self, idx):
        if not (0 <= idx < len(self._lib_items)):
            return
        self._lib_current = idx
        item = self._lib_items[idx]
        try:
            self._lib_player.set_output(self._lib_video.winfo_id())
        except Exception:
            pass
        self._lib_player.load(item["path"])
        self._lib_player.play()
        self._lib_player.set_volume(int(self._lib_vol.get()))
        icon = "🎬 " if item["is_video"] else "🎵 "
        label = (f'{item["artist"]} — {item["title"]}' if item["artist"] else item["title"])
        self._lib_now.configure(text=icon + label)
        self._lib_play_btn.configure(text="⏸")
        self._highlight_current()

    def _lib_toggle_play(self):
        if self._lib_current < 0:
            if self._lib_items:
                self._lib_play_index(0)
            return
        self._lib_player.pause()

    def _lib_stop(self):
        if self._lib_player:
            self._lib_player.stop()
        self._lib_play_btn.configure(text="▶")
        self._lib_seek.set(0)
        self._lib_elapsed.configure(text="00:00")

    def _lib_next(self, auto=False):
        if not self._lib_items:
            return
        nxt = self._lib_current + 1
        if nxt >= len(self._lib_items):
            if auto:
                self._lib_stop()
                self._lib_current = -1
                self._highlight_current()
                return
            nxt = 0
        self._lib_play_index(nxt)

    def _lib_prev(self):
        if not self._lib_items:
            return
        prev = self._lib_current - 1 if self._lib_current > 0 else len(self._lib_items) - 1
        self._lib_play_index(prev)

    def _on_seek(self, value):
        if self._lib_current >= 0:
            self._lib_player.set_position(value / 1000.0)

    def _on_volume(self, value):
        if self._lib_player:
            self._lib_player.set_volume(int(value))

    def _poll_player(self):
        try:
            if self._lib_player is not None and self._lib_current >= 0:
                if "Ended" in self._lib_player.get_state():
                    self._lib_next(auto=True)
                else:
                    length = self._lib_player.get_length()
                    elapsed = self._lib_player.get_time()
                    if length > 0:
                        self._lib_seek.set(min(1000, elapsed / length * 1000))
                        self._lib_elapsed.configure(text=self._fmt_ms(elapsed))
                        self._lib_total.configure(text=self._fmt_ms(length))
                    self._lib_play_btn.configure(text="⏸" if self._lib_player.is_playing() else "▶")
        except Exception:
            pass
        self.after(500, self._poll_player)

    # ── Editar (PyDub / MoviePy) ─────────────────────────────────────────────

    _ED_AUDIO_OPS = ["Cortar trecho", "Converter formato", "Normalizar volume",
                     "Ajustar volume", "Fade in/out"]
    _ED_VIDEO_OPS = ["Cortar trecho", "Velocidade", "Reverter", "Girar", "Espelhar",
                     "Preto e branco", "Inverter cores", "Brilho/Contraste",
                     "Fade (vídeo)", "Texto/Legenda", "Extrair áudio", "Remover áudio"]
    _ED_POS = {"Embaixo": "bottom", "Em cima": "top", "Centro": "center"}
    _ED_COLOR = {"Branca": "white", "Amarela": "yellow", "Preta": "black", "Vermelha": "red"}

    _FX_CATALOG = ["Velocidade", "Reverter", "Girar", "Espelhar", "Preto e branco",
                   "Inverter cores", "Brilho/Contraste", "Fade", "Texto/Legenda"]
    _PM_W = 380
    _PM_H = 234

    def _build_edit_video_tab(self):
        outer = self.tabview.tab("  Editar Vídeo  ")
        # Estado da timeline
        self._tl_tracks = [
            {"name": "🎬 Vídeo 1", "kind": "video"},
            {"name": "🔊 Áudio 1", "kind": "audio"},
            {"name": "🔊 Áudio 2", "kind": "audio"},
        ]
        self._tl_clips = []
        self._tl_next_id = 1
        self._tl_sel = None
        self._tl_pps = 18.0
        self._tl_drag = None
        self._tl_busy = False
        self._tl_tool = "select"
        self._tl_playhead = 0.0
        self._tl_preview = timeline_editor.TimelinePreview()
        self._tl_prev_after = None
        self._pm_imgref = None
        self._tl_playing = False

        # ── Topo: Program Monitor + painel lateral ───────────────────────────
        top = ctk.CTkFrame(outer, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 4))
        mon_col = ctk.CTkFrame(top, fg_color="transparent")
        mon_col.pack(side="left")
        holder = tk.Frame(mon_col, bg="black", width=self._PM_W, height=self._PM_H)
        holder.pack()
        holder.pack_propagate(False)
        self._pm_label = tk.Label(holder, bg="black", fg="#777777", text="(sem vídeo)")
        self._pm_label.pack(expand=True)
        trans = ctk.CTkFrame(mon_col, fg_color="transparent")
        trans.pack(fill="x", pady=(4, 0))
        self._pm_play = ctk.CTkButton(trans, text="▶", width=52, command=self._tl_play_toggle)
        self._pm_play.pack(side="left")
        ctk.CTkButton(trans, text="⟲ Início", width=70,
                      command=lambda: self._tl_set_playhead(0.0)).pack(side="left", padx=6)
        self._pm_time = ctk.CTkLabel(trans, text="0:00 / 0:00", font=ctk.CTkFont(size=11))
        self._pm_time.pack(side="left", padx=6)

        side = ctk.CTkFrame(top, fg_color="transparent")
        side.pack(side="left", fill="both", expand=True, padx=(12, 0))
        imp = ctk.CTkFrame(side, fg_color="transparent")
        imp.pack(fill="x")
        ctk.CTkButton(imp, text="➕ Vídeo", width=90,
                      command=lambda: self._tl_add("video")).pack(side="left", padx=(0, 6))
        ctk.CTkButton(imp, text="➕ Áudio", width=90,
                      command=lambda: self._tl_add("audio")).pack(side="left")
        self._tl_render_btn = ctk.CTkButton(imp, text="⬇ Exportar MP4", width=140,
                                            font=ctk.CTkFont(weight="bold"),
                                            fg_color="#2e8b57", hover_color="#1f5e3a",
                                            command=self._tl_render)
        self._tl_render_btn.pack(side="right")

        fxrow = ctk.CTkFrame(side, fg_color="transparent")
        fxrow.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(fxrow, text="Efeito:").pack(side="left", padx=(0, 6))
        self._fx_menu = ctk.CTkOptionMenu(fxrow, values=self._FX_CATALOG, width=150,
                                          command=lambda _v=None: self._fx_refresh_params())
        self._fx_menu.pack(side="left")
        ctk.CTkButton(fxrow, text="＋ Aplicar ao clipe", width=140,
                      command=self._tl_apply_effect).pack(side="left", padx=(8, 0))
        self._fx_param_frame = ctk.CTkFrame(side, fg_color="transparent")
        self._fx_param_frame.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(side, text="Efeitos do clipe selecionado:",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(6, 0))
        self._fx_list = ctk.CTkScrollableFrame(side, height=90, fg_color=("#e8e8ef", "#20203a"))
        self._fx_list.pack(fill="both", expand=True)

        # ── Barra de ferramentas ─────────────────────────────────────────────
        toolbar = ctk.CTkFrame(outer, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=(6, 2))
        self._tool_btns = {}
        self._tool_btns["select"] = ctk.CTkButton(toolbar, text="▶ Selecionar", width=110,
                                                  command=lambda: self._tl_set_tool("select"))
        self._tool_btns["select"].pack(side="left", padx=(0, 6))
        self._tool_btns["razor"] = ctk.CTkButton(toolbar, text="✂ Cortar", width=90,
                                                 command=lambda: self._tl_set_tool("razor"))
        self._tool_btns["razor"].pack(side="left", padx=(0, 6))
        ctk.CTkButton(toolbar, text="🗑 Excluir", width=84, fg_color="#7a2e2e",
                      hover_color="#9b2321", command=self._tl_delete).pack(side="left", padx=(0, 6))
        ctk.CTkButton(toolbar, text="🔍−", width=44,
                      command=lambda: self._tl_zoom(1 / 1.4)).pack(side="left", padx=(12, 2))
        ctk.CTkButton(toolbar, text="🔍+", width=44,
                      command=lambda: self._tl_zoom(1.4)).pack(side="left")
        ctk.CTkLabel(toolbar, text="Dica: Selecionar move/apara. Cortar → clique no clipe divide ali "
                     "(depois volta p/ Selecionar). Clique na régua move o playhead.",
                     font=ctk.CTkFont(size=11), text_color="#888888").pack(side="left", padx=12)

        # ── Timeline (canvas) ────────────────────────────────────────────────
        self._tl_build_canvas(outer)

        self._tl_bar = ctk.CTkProgressBar(outer)
        self._tl_bar.set(0)
        self._tl_status = ctk.CTkLabel(outer, text="", font=ctk.CTkFont(size=11), text_color="#888888")
        self._tl_status.pack(anchor="w", padx=12, pady=(2, 0))
        self._tl_log = ctk.CTkTextbox(outer, height=52, font=ctk.CTkFont(size=11))
        self._tl_log.pack(fill="x", padx=12, pady=(2, 10))
        self._tl_log.configure(state="disabled")

        self._tl_set_tool("select")
        self._fx_refresh_params()
        self._tl_refresh_effect_list()
        self.after(250, self._tl_redraw)

    def _build_editor_tab(self, raw):
        tab = self._tab_content(raw)
        self._ed_src = None
        self._ed_busy = False
        self._ed_widgets = {}
        self._build_dest_row(tab)

        ctk.CTkLabel(tab, text="Arquivo para editar:", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=12, pady=(12, 2))
        file_row = ctk.CTkFrame(tab, fg_color="transparent")
        file_row.pack(fill="x", padx=12, pady=(0, 6))
        self._ed_file_var = ctk.StringVar(value="Nenhum arquivo escolhido")
        self._ed_file_lbl = ctk.CTkLabel(file_row, textvariable=self._ed_file_var,
                                         anchor="w", text_color="#999999")
        self._ed_file_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(file_row, text="Escolher…", width=100, command=self._ed_choose_file).pack(side="left")

        op_row = ctk.CTkFrame(tab, fg_color="transparent")
        op_row.pack(fill="x", padx=12, pady=(6, 0))
        ctk.CTkLabel(op_row, text="Operação:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8))
        self._ed_op = ctk.CTkOptionMenu(op_row, values=["—"], width=260,
                                        command=lambda _=None: self._ed_refresh_params())
        self._ed_op.pack(side="left")

        self._ed_param_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self._ed_param_frame.pack(fill="x", padx=12, pady=(10, 0))

        self._ed_btn = ctk.CTkButton(tab, text="✦   Aplicar edição", height=40,
                                     font=ctk.CTkFont(size=14, weight="bold"),
                                     command=self._ed_apply, state="disabled")
        self._ed_btn.pack(fill="x", padx=12, pady=(14, 6))

        self._ed_bar = ctk.CTkProgressBar(tab)
        self._ed_bar.set(0)
        self._ed_status = ctk.CTkLabel(tab, text="", font=ctk.CTkFont(size=11), text_color="#888888")
        self._ed_status.pack(anchor="w", padx=12)
        self._ed_log = ctk.CTkTextbox(tab, height=150, font=ctk.CTkFont(size=11))
        self._ed_log.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        self._ed_log.configure(state="disabled")

    def _ed_is_video(self):
        if not self._ed_src:
            return False
        return os.path.splitext(self._ed_src)[1].lower() in media_library.VIDEO_EXTS

    def _ed_choose_file(self):
        exts = media_library.AUDIO_EXTS | media_library.VIDEO_EXTS
        patterns = " ".join(f"*{e}" for e in sorted(exts))
        path = filedialog.askopenfilename(
            title="Escolha um áudio ou vídeo",
            initialdir=DOWNLOADS_FOLDER if os.path.isdir(DOWNLOADS_FOLDER) else None,
            filetypes=[("Mídia", patterns), ("Todos os arquivos", "*.*")])
        if not path:
            return
        self._ed_src = path
        self._ed_file_var.set(self._trim(os.path.basename(path), 70))
        self._ed_file_lbl.configure(text_color=("#202124", "#dddddd"))
        ops = self._ED_VIDEO_OPS if self._ed_is_video() else self._ED_AUDIO_OPS
        self._ed_op.configure(values=ops)
        self._ed_op.set(ops[0])
        self._ed_btn.configure(state="normal")
        self._ed_refresh_params()

    def _ed_refresh_params(self):
        for widget in self._ed_param_frame.winfo_children():
            widget.destroy()
        self._ed_widgets = {}
        op = self._ed_op.get()
        frame = self._ed_param_frame
        if op == "Cortar trecho":
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(anchor="w")
            for key, label in (("start", "Início"), ("end", "Fim")):
                ctk.CTkLabel(row, text=label).pack(side="left", padx=(0, 6))
                var = ctk.StringVar(value="00:00:00")
                entry = ctk.CTkEntry(row, width=90, textvariable=var, justify="center")
                entry.pack(side="left", padx=(0, 16))
                entry.bind("<KeyRelease>",
                           lambda e, en=entry, va=var: self._mask_time(e, en, va))
                self._ed_widgets[key] = var
            ctk.CTkLabel(frame, text="Use horas:minutos:segundos (00:00:00).",
                         font=ctk.CTkFont(size=11), text_color="#888888").pack(anchor="w", pady=(4, 0))
        elif op in ("Converter formato", "Extrair áudio"):
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(anchor="w")
            ctk.CTkLabel(row, text="Formato de saída:").pack(side="left", padx=(0, 8))
            menu = ctk.CTkOptionMenu(row, values=list(media_editor.AUDIO_EXPORT), width=140)
            menu.set("MP3")
            menu.pack(side="left")
            self._ed_widgets["format"] = menu
        elif op == "Ajustar volume":
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(anchor="w", fill="x")
            ctk.CTkLabel(row, text="Ganho:").pack(side="left", padx=(0, 8))
            value_lbl = ctk.CTkLabel(row, text="+0 dB", width=60)
            slider = ctk.CTkSlider(row, from_=-20, to=20, number_of_steps=40, width=260,
                                   command=lambda v: value_lbl.configure(text=f"{int(v):+d} dB"))
            slider.set(0)
            slider.pack(side="left", padx=(0, 10))
            value_lbl.pack(side="left")
            self._ed_widgets["db"] = slider
        elif op in ("Fade in/out", "Fade (vídeo)"):
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(anchor="w")
            for key, label in (("fin", "Fade in (s)"), ("fout", "Fade out (s)")):
                ctk.CTkLabel(row, text=label).pack(side="left", padx=(0, 6))
                var = ctk.StringVar(value="1")
                ctk.CTkEntry(row, width=60, textvariable=var, justify="center").pack(side="left", padx=(0, 16))
                self._ed_widgets[key] = var
        elif op == "Velocidade":
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(anchor="w")
            ctk.CTkLabel(row, text="Velocidade:").pack(side="left", padx=(0, 8))
            menu = ctk.CTkOptionMenu(row, values=["0.25x", "0.5x", "1.5x", "2x", "4x"], width=120)
            menu.set("2x")
            menu.pack(side="left")
            self._ed_widgets["speed"] = menu
        elif op == "Girar":
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(anchor="w")
            ctk.CTkLabel(row, text="Ângulo:").pack(side="left", padx=(0, 8))
            menu = ctk.CTkOptionMenu(row, values=["90°", "180°", "270°"], width=100)
            menu.set("90°")
            menu.pack(side="left")
            self._ed_widgets["rotate"] = menu
        elif op == "Espelhar":
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(anchor="w")
            ctk.CTkLabel(row, text="Eixo:").pack(side="left", padx=(0, 8))
            menu = ctk.CTkOptionMenu(row, values=["Horizontal", "Vertical"], width=140)
            menu.pack(side="left")
            self._ed_widgets["mirror"] = menu
        elif op == "Brilho/Contraste":
            for key, label in (("lum", "Brilho"), ("contrast", "Contraste")):
                row = ctk.CTkFrame(frame, fg_color="transparent")
                row.pack(anchor="w", fill="x", pady=2)
                ctk.CTkLabel(row, text=label, width=72, anchor="w").pack(side="left")
                value_lbl = ctk.CTkLabel(row, text="0", width=40)
                slider = ctk.CTkSlider(row, from_=-50, to=50, number_of_steps=100, width=240,
                                       command=lambda v, lbl=value_lbl: lbl.configure(text=f"{int(v)}"))
                slider.set(0)
                slider.pack(side="left", padx=(0, 10))
                value_lbl.pack(side="left")
                self._ed_widgets[key] = slider
        elif op == "Texto/Legenda":
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(anchor="w", fill="x")
            text_var = ctk.StringVar(value="")
            entry = ctk.CTkEntry(row, textvariable=text_var, width=320, placeholder_text="Digite o texto…")
            entry.pack(side="left", padx=(0, 10))
            self._ed_widgets["text"] = text_var
            row2 = ctk.CTkFrame(frame, fg_color="transparent")
            row2.pack(anchor="w", pady=(6, 0))
            ctk.CTkLabel(row2, text="Posição:").pack(side="left", padx=(0, 6))
            pos = ctk.CTkOptionMenu(row2, values=list(self._ED_POS), width=110)
            pos.set("Embaixo")
            pos.pack(side="left", padx=(0, 16))
            ctk.CTkLabel(row2, text="Cor:").pack(side="left", padx=(0, 6))
            color = ctk.CTkOptionMenu(row2, values=list(self._ED_COLOR), width=110)
            color.pack(side="left")
            self._ed_widgets["tpos"] = pos
            self._ed_widgets["tcolor"] = color
        else:  # Reverter, Preto e branco, Inverter cores, Normalizar volume, Remover áudio
            ctk.CTkLabel(frame, text="Sem parâmetros. Clique em Aplicar edição.",
                         font=ctk.CTkFont(size=11), text_color="#888888").pack(anchor="w")

    def _ed_apply(self):
        if self._ed_busy or not self._ed_src:
            return
        op = self._ed_op.get()
        try:
            params = self._ed_collect_params(op)
        except ValueError as exc:
            self._set_status(self._ed_status, f"✗ {exc}", "#e74c3c")
            return
        self._ed_busy = True
        self._ed_btn.configure(state="disabled", text="Processando…")
        self._ed_bar.pack(fill="x", padx=12, pady=(0, 2))
        self._ed_bar.configure(mode="indeterminate")
        self._ed_bar.start()
        self._set_status(self._ed_status, "Editando…", "#888888")
        self._ed_log_write(f"→ {op}: {os.path.basename(self._ed_src)}")
        threading.Thread(target=self._ed_run, args=(op, params), daemon=True).start()

    def _ed_collect_params(self, op):
        w = self._ed_widgets
        if op == "Cortar trecho":
            start = parse_clock(w["start"].get())
            end = parse_clock(w["end"].get())
            if end <= start:
                raise ValueError("O fim precisa ser maior que o início.")
            return {"start": start, "end": end}
        if op in ("Converter formato", "Extrair áudio"):
            return {"format": w["format"].get()}
        if op == "Ajustar volume":
            return {"db": int(w["db"].get())}
        if op in ("Fade in/out", "Fade (vídeo)"):
            try:
                return {"fin": float(w["fin"].get() or 0), "fout": float(w["fout"].get() or 0)}
            except ValueError:
                raise ValueError("Informe os segundos do fade com números.")
        if op == "Velocidade":
            return {"factor": float(w["speed"].get().rstrip("x"))}
        if op == "Girar":
            return {"degrees": int(w["rotate"].get().rstrip("°"))}
        if op == "Espelhar":
            return {"axis": "h" if w["mirror"].get() == "Horizontal" else "v"}
        if op == "Brilho/Contraste":
            return {"lum": int(w["lum"].get()), "contrast": int(w["contrast"].get())}
        if op == "Texto/Legenda":
            text = w["text"].get().strip()
            if not text:
                raise ValueError("Digite o texto da legenda.")
            return {"text": text, "position": self._ED_POS[w["tpos"].get()],
                    "color": self._ED_COLOR[w["tcolor"].get()]}
        return {}

    def _ed_run(self, op, params):
        src, out_dir = self._ed_src, DOWNLOADS_FOLDER
        try:
            media_editor.configure_ffmpeg(get_ffmpeg_path() or shutil.which("ffmpeg"))
            is_video = self._ed_is_video()
            if op == "Cortar trecho":
                out = (media_editor.video_trim if is_video else media_editor.audio_trim)(
                    src, params["start"], params["end"], out_dir)
            elif op == "Converter formato":
                out = media_editor.audio_convert(src, params["format"], out_dir)
            elif op == "Normalizar volume":
                out = media_editor.audio_normalize(src, out_dir)
            elif op == "Ajustar volume":
                out = media_editor.audio_gain(src, params["db"], out_dir)
            elif op == "Fade in/out":
                out = media_editor.audio_fade(src, params["fin"], params["fout"], out_dir)
            elif op == "Extrair áudio":
                out = media_editor.video_extract_audio(src, params["format"], out_dir)
            elif op == "Remover áudio":
                out = media_editor.video_mute(src, out_dir)
            elif op == "Velocidade":
                out = media_editor.video_speed(src, params["factor"], out_dir)
            elif op == "Reverter":
                out = media_editor.video_reverse(src, out_dir)
            elif op == "Girar":
                out = media_editor.video_rotate(src, params["degrees"], out_dir)
            elif op == "Espelhar":
                out = media_editor.video_mirror(src, params["axis"], out_dir)
            elif op == "Preto e branco":
                out = media_editor.video_grayscale(src, out_dir)
            elif op == "Inverter cores":
                out = media_editor.video_invert(src, out_dir)
            elif op == "Brilho/Contraste":
                out = media_editor.video_bright_contrast(src, params["lum"], params["contrast"], out_dir)
            elif op == "Fade (vídeo)":
                out = media_editor.video_fade(src, params["fin"], params["fout"], out_dir)
            elif op == "Texto/Legenda":
                out = media_editor.video_text(src, params["text"], params["position"], 48,
                                              params["color"], out_dir)
            else:
                raise ValueError("Operação desconhecida.")
            self.after(0, lambda: self._ed_finish(True, out))
        except Exception as exc:
            self.after(0, lambda exc=exc: self._ed_finish(False, str(exc)))

    def _ed_finish(self, ok, result):
        self._ed_busy = False
        self._ed_bar.stop()
        self._ed_bar.pack_forget()
        self._ed_btn.configure(state="normal", text="✦   Aplicar edição")
        if ok:
            self._ed_log_write(f"✓ Salvo: {os.path.basename(result)}")
            self._set_status(self._ed_status, "✓ Concluído! Veja na pasta de downloads.", "#2ecc71")
            if hasattr(self, "_lib_items"):
                self._scan_library()
        else:
            self._ed_log_write(f"✗ Erro: {result}")
            self._set_status(self._ed_status, f"✗ {result}", "#e74c3c")

    def _ed_log_write(self, msg):
        self._ed_log.configure(state="normal")
        self._ed_log.insert("end", msg + "\n")
        self._ed_log.see("end")
        self._ed_log.configure(state="disabled")

    # ── Cortar (preview VLC + in/out) ─────────────────────────────────────────

    def _build_cutter_tab(self, tab):
        self._cut_player = None
        self._cut_src = None
        self._cut_in = 0.0
        self._cut_out = 0.0
        self._cut_len = 0.0
        self._cut_busy = False
        self._cut_poll_active = False
        self._cut_preview_until = None
        self._build_dest_row(tab)
        self._cut_body = ctk.CTkFrame(tab, fg_color="transparent")
        self._cut_body.pack(fill="both", expand=True, padx=12, pady=(8, 10))
        self._cut_render()

    def _cut_render(self):
        for widget in self._cut_body.winfo_children():
            widget.destroy()
        vlc = media_library.load_vlc(_bin_dir()) if media_library.has_vlc(_bin_dir()) else None
        if vlc is None:
            box = ctk.CTkFrame(self._cut_body, fg_color="transparent")
            box.pack(expand=True)
            ctk.CTkLabel(box, text="✂  Cortar com preview",
                         font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(40, 8))
            ctk.CTkLabel(box, justify="center", text_color="#aaaaaa",
                         text="O preview usa o componente de vídeo (libVLC).\n"
                              "Instale-o na aba Biblioteca para habilitar esta ferramenta.").pack(pady=(0, 16))
            ctk.CTkButton(box, text="Ir para a Biblioteca",
                          command=lambda: self.tabview.set("  Biblioteca  ")).pack()
            return
        if self._cut_player is None:
            try:
                self._cut_player = media_library.MediaLibraryPlayer(vlc)
            except Exception as exc:
                ctk.CTkLabel(self._cut_body, text=f"Falha ao iniciar o player: {exc}",
                             text_color="#e74c3c").pack(pady=20)
                return
        self._build_cutter_ui(self._cut_body)
        if not self._cut_poll_active:
            self._cut_poll_active = True
            self.after(300, self._cut_poll)

    def _build_cutter_ui(self, parent):
        file_row = ctk.CTkFrame(parent, fg_color="transparent")
        file_row.pack(fill="x")
        self._cut_file_var = ctk.StringVar(value="Nenhum arquivo escolhido")
        ctk.CTkLabel(file_row, textvariable=self._cut_file_var, anchor="w",
                     text_color="#999999").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(file_row, text="Escolher…", width=100,
                      command=self._cut_choose_file).pack(side="left")

        self._cut_video = tk.Frame(parent, bg="black", height=300)
        self._cut_video.pack(fill="both", expand=True, pady=(8, 6))
        self._cut_video.pack_propagate(False)

        trow = ctk.CTkFrame(parent, fg_color="transparent")
        trow.pack(fill="x")
        self._cut_play_btn = ctk.CTkButton(trow, text="▶", width=56, command=self._cut_toggle)
        self._cut_play_btn.pack(side="left", padx=(0, 8))
        self._cut_elapsed = ctk.CTkLabel(trow, text="00:00", width=46, font=ctk.CTkFont(size=11))
        self._cut_elapsed.pack(side="left")
        self._cut_seek = ctk.CTkSlider(trow, from_=0, to=1000, command=self._cut_seek)
        self._cut_seek.set(0)
        self._cut_seek.pack(side="left", fill="x", expand=True, padx=6)
        self._cut_total = ctk.CTkLabel(trow, text="00:00", width=46, font=ctk.CTkFont(size=11))
        self._cut_total.pack(side="left")

        mrow = ctk.CTkFrame(parent, fg_color="transparent")
        mrow.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(mrow, text="⟦ Marcar início", width=120,
                      command=self._cut_mark_in).pack(side="left")
        self._cut_in_lbl = ctk.CTkLabel(mrow, text="início 00:00", width=90, font=ctk.CTkFont(size=11))
        self._cut_in_lbl.pack(side="left", padx=(6, 14))
        ctk.CTkButton(mrow, text="Marcar fim ⟧", width=120,
                      command=self._cut_mark_out).pack(side="left")
        self._cut_out_lbl = ctk.CTkLabel(mrow, text="fim 00:00", width=90, font=ctk.CTkFont(size=11))
        self._cut_out_lbl.pack(side="left", padx=(6, 14))
        ctk.CTkButton(mrow, text="▶ Prévia", width=80,
                      command=self._cut_preview).pack(side="left")
        self._cut_sel_lbl = ctk.CTkLabel(mrow, text="seleção —", font=ctk.CTkFont(size=11),
                                         text_color="#2ecc71")
        self._cut_sel_lbl.pack(side="right")

        self._cut_btn = ctk.CTkButton(parent, text="✂   Cortar e salvar", height=40,
                                      font=ctk.CTkFont(size=14, weight="bold"),
                                      command=self._cut_apply, state="disabled")
        self._cut_btn.pack(fill="x", pady=(12, 6))
        self._cut_bar = ctk.CTkProgressBar(parent)
        self._cut_bar.set(0)
        self._cut_status = ctk.CTkLabel(parent, text="", font=ctk.CTkFont(size=11), text_color="#888888")
        self._cut_status.pack(anchor="w")
        self.after(300, lambda: self._cut_player.set_output(self._cut_video.winfo_id()))

    def _cut_is_video(self):
        return self._cut_src and os.path.splitext(self._cut_src)[1].lower() in media_library.VIDEO_EXTS

    def _cut_choose_file(self):
        exts = media_library.AUDIO_EXTS | media_library.VIDEO_EXTS
        patterns = " ".join(f"*{e}" for e in sorted(exts))
        path = filedialog.askopenfilename(
            title="Escolha um áudio ou vídeo para cortar",
            initialdir=DOWNLOADS_FOLDER if os.path.isdir(DOWNLOADS_FOLDER) else None,
            filetypes=[("Mídia", patterns), ("Todos os arquivos", "*.*")])
        if not path:
            return
        self._cut_src = path
        self._cut_file_var.set(self._trim(os.path.basename(path), 70))
        self._cut_in, self._cut_out, self._cut_len = 0.0, 0.0, 0.0
        self._cut_in_lbl.configure(text="início 00:00")
        self._cut_out_lbl.configure(text="fim 00:00")
        self._cut_sel_lbl.configure(text="seleção —")
        try:
            self._cut_player.set_output(self._cut_video.winfo_id())
        except Exception:
            pass
        self._cut_player.load(path)
        self._cut_player.play()
        self._cut_player.set_volume(70)
        self._cut_play_btn.configure(text="⏸")
        self._cut_btn.configure(state="normal")
        self._set_status(self._cut_status, "Carregando preview…", "#888888")

    def _cut_toggle(self):
        if self._cut_src:
            self._cut_player.pause()

    def _cut_seek(self, value):
        if self._cut_src:
            self._cut_preview_until = None
            self._cut_player.set_position(value / 1000.0)

    def _cut_mark_in(self):
        if not self._cut_src:
            return
        self._cut_in = self._cut_player.get_time() / 1000.0
        self._cut_in_lbl.configure(text="início " + self._fmt_ms(self._cut_in * 1000))
        self._cut_update_sel()

    def _cut_mark_out(self):
        if not self._cut_src:
            return
        self._cut_out = self._cut_player.get_time() / 1000.0
        self._cut_out_lbl.configure(text="fim " + self._fmt_ms(self._cut_out * 1000))
        self._cut_update_sel()

    def _cut_update_sel(self):
        if self._cut_out > self._cut_in:
            self._cut_sel_lbl.configure(text="seleção " + self._fmt_ms((self._cut_out - self._cut_in) * 1000),
                                        text_color="#2ecc71")
        else:
            self._cut_sel_lbl.configure(text="fim deve ser após o início", text_color="#e74c3c")

    def _cut_preview(self):
        if self._cut_src and self._cut_out > self._cut_in and self._cut_len > 0:
            self._cut_player.set_position(self._cut_in / self._cut_len)
            self._cut_player.play()
            self._cut_play_btn.configure(text="⏸")
            self._cut_preview_until = self._cut_out

    def _cut_apply(self):
        if self._cut_busy or not self._cut_src:
            return
        if not (self._cut_out > self._cut_in >= 0):
            self._set_status(self._cut_status, "✗ Marque início e fim válidos (fim após início).", "#e74c3c")
            return
        self._cut_busy = True
        self._cut_preview_until = None
        self._cut_btn.configure(state="disabled", text="Cortando…")
        self._cut_bar.pack(fill="x", pady=(0, 2))
        self._cut_bar.configure(mode="indeterminate")
        self._cut_bar.start()
        self._set_status(self._cut_status, "Cortando…", "#888888")
        start, end = self._cut_in, self._cut_out
        threading.Thread(target=self._cut_run, args=(self._cut_src, start, end, self._cut_is_video()),
                         daemon=True).start()

    def _cut_run(self, src, start, end, is_video):
        try:
            media_editor.configure_ffmpeg(get_ffmpeg_path() or shutil.which("ffmpeg"))
            func = media_editor.video_trim if is_video else media_editor.audio_trim
            out = func(src, start, end, DOWNLOADS_FOLDER)
            self.after(0, lambda: self._cut_finish(True, out))
        except Exception as exc:
            self.after(0, lambda exc=exc: self._cut_finish(False, str(exc)))

    def _cut_finish(self, ok, result):
        self._cut_busy = False
        self._cut_bar.stop()
        self._cut_bar.pack_forget()
        self._cut_btn.configure(state="normal", text="✂   Cortar e salvar")
        if ok:
            self._set_status(self._cut_status, f"✓ Salvo: {os.path.basename(result)}", "#2ecc71")
            if hasattr(self, "_lib_items"):
                self._scan_library()
        else:
            self._set_status(self._cut_status, f"✗ {result}", "#e74c3c")

    def _cut_poll(self):
        try:
            player = self._cut_player
            if player is not None and self._cut_src:
                length = player.get_length()
                elapsed = player.get_time()
                if length > 0:
                    self._cut_len = length / 1000.0
                    self._cut_seek.set(min(1000, elapsed / length * 1000))
                    self._cut_elapsed.configure(text=self._fmt_ms(elapsed))
                    self._cut_total.configure(text=self._fmt_ms(length))
                    if self._cut_out <= 0:
                        self._cut_out = self._cut_len
                        self._cut_out_lbl.configure(text="fim " + self._fmt_ms(length))
                        self._cut_update_sel()
                self._cut_play_btn.configure(text="⏸" if player.is_playing() else "▶")
                if self._cut_preview_until is not None and elapsed / 1000.0 >= self._cut_preview_until:
                    if player.is_playing():
                        player.pause()
                    self._cut_preview_until = None
        except Exception:
            pass
        self.after(400, self._cut_poll)

    # ── Timeline (multitrack) ────────────────────────────────────────────────

    TL_RULER_H = 22
    TL_LANE_H = 54
    TL_HEADER_W = 94
    TL_EDGE_PX = 6
    TL_MIN_DUR = 0.15

    def _tl_build_canvas(self, tab):
        body = ctk.CTkFrame(tab, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(4, 4))
        canvas_h = self.TL_RULER_H + len(self._tl_tracks) * self.TL_LANE_H
        self._tl_header = tk.Canvas(body, width=self.TL_HEADER_W, height=canvas_h,
                                    bg="#1a1a2e", highlightthickness=0)
        self._tl_header.pack(side="left", fill="y")
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)
        self._tl_canvas = tk.Canvas(right, height=canvas_h, bg="#15152a", highlightthickness=0)
        self._tl_canvas.pack(fill="both", expand=True)
        hsb = ctk.CTkScrollbar(right, orientation="horizontal", command=self._tl_canvas.xview)
        hsb.pack(fill="x")
        self._tl_canvas.configure(xscrollcommand=hsb.set)
        self._tl_canvas.bind("<Button-1>", self._tl_on_press)
        self._tl_canvas.bind("<B1-Motion>", self._tl_on_motion)
        self._tl_canvas.bind("<ButtonRelease-1>", self._tl_on_release)
        self._tl_canvas.bind("<Motion>", self._tl_on_hover)
        self._tl_canvas.bind("<MouseWheel>", self._tl_on_wheel)
        self._tl_canvas.bind("<Control-MouseWheel>", self._tl_on_wheel_zoom)
        self._tl_canvas.bind("<Configure>", lambda _e: self._tl_redraw())

    # — modelo/consulta —
    def _tl_get(self, cid):
        return next((c for c in self._tl_clips if c["id"] == cid), None)

    def _tl_track_end(self, track):
        ends = [c["start"] + c["duration"] for c in self._tl_clips if c["track"] == track]
        return max(ends, default=0.0)

    def _tl_total(self):
        return max((c["start"] + c["duration"] for c in self._tl_clips), default=0.0)

    def _tl_ruler_step(self):
        raw = 70 / self._tl_pps
        for step in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600):
            if step >= raw:
                return step
        return 900

    @staticmethod
    def _tl_time_label(t):
        t = int(t)
        return f"{t // 60}:{t % 60:02d}"

    # — desenho —
    def _tl_redraw(self):
        cv, hv = self._tl_canvas, self._tl_header
        cv.delete("all")
        hv.delete("all")
        n = len(self._tl_tracks)
        height = self.TL_RULER_H + n * self.TL_LANE_H
        width = max(cv.winfo_width(), int((self._tl_total() + 12) * self._tl_pps))
        cv.configure(scrollregion=(0, 0, width, height))
        for i, tr in enumerate(self._tl_tracks):
            y0 = self.TL_RULER_H + i * self.TL_LANE_H
            y1 = y0 + self.TL_LANE_H
            bg = "#20203a" if i % 2 == 0 else "#191930"
            cv.create_rectangle(0, y0, width, y1, fill=bg, outline="#2e2e4a")
            hv.create_rectangle(0, y0, self.TL_HEADER_W, y1, fill="#26263f", outline="#2e2e4a")
            hv.create_text(8, (y0 + y1) / 2, anchor="w", text=tr["name"], fill="#cfd4ec", font=("", 9))
        cv.create_rectangle(0, 0, width, self.TL_RULER_H, fill="#2a2a40", outline="")
        hv.create_rectangle(0, 0, self.TL_HEADER_W, self.TL_RULER_H, fill="#2a2a40", outline="")
        step = self._tl_ruler_step()
        t = 0
        while t * self._tl_pps <= width:
            x = t * self._tl_pps
            cv.create_line(x, 0, x, height, fill="#30304d")
            cv.create_text(x + 3, 2, anchor="nw", text=self._tl_time_label(t), fill="#8890b5", font=("", 8))
            t += step
        for c in self._tl_clips:
            self._tl_draw_clip(c)
        px = self._tl_playhead * self._tl_pps
        cv.create_line(px, 0, px, height, fill="#ff5555", width=2)
        cv.create_polygon(px - 5, 0, px + 5, 0, px, 9, fill="#ff5555", outline="")

    def _tl_draw_clip(self, c):
        cv = self._tl_canvas
        x0 = c["start"] * self._tl_pps
        x1 = (c["start"] + c["duration"]) * self._tl_pps
        y0 = self.TL_RULER_H + c["track"] * self.TL_LANE_H + 4
        y1 = y0 + self.TL_LANE_H - 8
        fill = "#3b6fb0" if c["kind"] == "video" else "#2e8b57"
        selected = c["id"] == self._tl_sel
        outline = "#ffd54a" if selected else "#101a2c"
        tag = f"clip{c['id']}"
        c["rect"] = cv.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline,
                                        width=3 if selected else 1, tags=("clip", tag))
        max_chars = max(3, int((x1 - x0) / 7))
        cv.create_text(x0 + 6, (y0 + y1) / 2, anchor="w",
                       text=self._trim(c["name"], max_chars), fill="white",
                       font=("", 9), tags=("clip", tag))

    def _tl_reposition(self, c):
        cv = self._tl_canvas
        x0 = c["start"] * self._tl_pps
        x1 = (c["start"] + c["duration"]) * self._tl_pps
        y0 = self.TL_RULER_H + c["track"] * self.TL_LANE_H + 4
        y1 = y0 + self.TL_LANE_H - 8
        cv.coords(c["rect"], x0, y0, x1, y1)
        for item in cv.find_withtag(f"clip{c['id']}"):
            if item != c["rect"]:
                cv.coords(item, x0 + 6, (y0 + y1) / 2)

    def _tl_select(self, cid):
        self._tl_sel = cid
        self._tl_redraw()
        self._tl_refresh_effect_list()

    # — interação —
    def _tl_item_to_clip(self, cx, cy):
        items = self._tl_canvas.find_overlapping(cx - 1, cy - 1, cx + 1, cy + 1)
        for item in reversed(items):
            for tag in self._tl_canvas.gettags(item):
                if tag.startswith("clip") and tag[4:].isdigit():
                    return int(tag[4:])
        return None

    def _tl_edge_at(self, c, cx):
        x0 = c["start"] * self._tl_pps
        x1 = (c["start"] + c["duration"]) * self._tl_pps
        if abs(cx - x0) <= self.TL_EDGE_PX:
            return "trim-left"
        if abs(cx - x1) <= self.TL_EDGE_PX:
            return "trim-right"
        return "move"

    def _tl_on_press(self, event):
        cx = self._tl_canvas.canvasx(event.x)
        cy = self._tl_canvas.canvasy(event.y)
        if cy <= self.TL_RULER_H:  # régua → mover playhead
            self._tl_drag = {"mode": "playhead"}
            self._tl_set_playhead(cx / self._tl_pps)
            return
        cid = self._tl_item_to_clip(cx, cy)
        if cid is None:
            if self._tl_sel is not None:
                self._tl_select(None)
            return
        if self._tl_tool == "razor":
            self._tl_split(cid, cx / self._tl_pps)
            self._tl_set_tool("select")  # corte one-shot: volta a Selecionar
            return
        c = self._tl_get(cid)
        self._tl_drag = {"cid": cid, "cx": cx, "cy": cy, "mode": self._tl_edge_at(c, cx),
                         "start0": c["start"], "track0": c["track"],
                         "src_in0": c["src_in"], "duration0": c["duration"]}
        self._tl_select(cid)

    def _tl_on_motion(self, event):
        if not self._tl_drag:
            return
        cx = self._tl_canvas.canvasx(event.x)
        cy = self._tl_canvas.canvasy(event.y)
        d = self._tl_drag
        if d.get("mode") == "playhead":
            self._tl_set_playhead(cx / self._tl_pps)
            return
        c = self._tl_get(d["cid"])
        if not c:
            return
        dt = (cx - d["cx"]) / self._tl_pps
        if d["mode"] == "trim-left":
            right = d["start0"] + d["duration0"]
            lower = max(0.0, d["start0"] - d["src_in0"])        # limite da fonte (src_in >= 0)
            upper = right - self.TL_MIN_DUR
            new_left = max(lower, min(upper, d["start0"] + dt))
            c["start"] = new_left
            c["src_in"] = d["src_in0"] + (new_left - d["start0"])
            c["duration"] = right - new_left
        elif d["mode"] == "trim-right":
            src_len = c.get("src_len", d["duration0"] + d["src_in0"])
            max_dur = src_len - d["src_in0"]
            new_dur = max(self.TL_MIN_DUR, min(max_dur, d["duration0"] + dt))
            c["duration"] = new_dur
        else:
            c["start"] = max(0.0, d["start0"] + dt)
            lane = int((cy - self.TL_RULER_H) // self.TL_LANE_H)
            lane = max(0, min(len(self._tl_tracks) - 1, lane))
            if self._tl_tracks[lane]["kind"] == c["kind"]:
                c["track"] = lane
        self._tl_reposition(c)
        if d["mode"] != "move":
            self._set_status(self._tl_status,
                             f"Trecho: {c['duration']:.1f}s (início na fonte {c['src_in']:.1f}s)", "#888888")

    def _tl_on_hover(self, event):
        if self._tl_drag:
            return
        cx = self._tl_canvas.canvasx(event.x)
        cy = self._tl_canvas.canvasy(event.y)
        cid = self._tl_item_to_clip(cx, cy)
        cursor = ""
        if cid is not None and self._tl_edge_at(self._tl_get(cid), cx) != "move":
            cursor = "sb_h_double_arrow"
        if self._tl_canvas.cget("cursor") != cursor:
            self._tl_canvas.configure(cursor=cursor)

    def _tl_on_release(self, _event):
        if self._tl_drag and self._tl_drag.get("mode") != "playhead":
            c = self._tl_get(self._tl_drag.get("cid"))
            if c and self._tl_drag.get("mode", "move") == "move":
                self._tl_snap(c)
                self._tl_reposition(c)
            self._tl_redraw()
            self._tl_invalidate_preview()
        self._tl_drag = None

    def _tl_snap(self, c):
        if c["start"] < 0.3:
            c["start"] = 0.0
            return
        edges = [0.0]
        for other in self._tl_clips:
            if other["id"] != c["id"] and other["track"] == c["track"]:
                edges.append(other["start"] + other["duration"])
                edges.append(other["start"])
        for edge in edges:
            if abs(c["start"] - edge) * self._tl_pps < 9:
                c["start"] = max(0.0, edge)
                break

    def _tl_add(self, kind):
        exts = media_library.VIDEO_EXTS if kind == "video" else media_library.AUDIO_EXTS
        patterns = " ".join(f"*{e}" for e in sorted(exts))
        path = filedialog.askopenfilename(
            title=f"Escolha um {'vídeo' if kind == 'video' else 'áudio'}",
            initialdir=DOWNLOADS_FOLDER if os.path.isdir(DOWNLOADS_FOLDER) else None,
            filetypes=[("Mídia", patterns), ("Todos os arquivos", "*.*")])
        if not path:
            return
        self._set_status(self._tl_status, "Analisando duração…", "#888888")
        self.update_idletasks()
        _kind, duration = timeline_editor._probe_media(path)
        if duration <= 0:
            self._set_status(self._tl_status, "✗ Não consegui ler a duração deste arquivo.", "#e74c3c")
            return
        track = 0 if kind == "video" else 1
        clip = {"id": self._tl_next_id, "path": path, "kind": kind, "track": track,
                "start": self._tl_track_end(track), "duration": duration, "src_in": 0.0,
                "src_len": duration, "name": os.path.basename(path), "effects": []}
        self._tl_next_id += 1
        self._tl_clips.append(clip)
        self._tl_select(clip["id"])
        self._set_status(self._tl_status,
                         f"Adicionado: {self._trim(clip['name'], 42)} ({duration:.1f}s)", "#2ecc71")
        self._tl_invalidate_preview()

    def _tl_delete(self):
        if self._tl_sel is None:
            return
        self._tl_clips = [c for c in self._tl_clips if c["id"] != self._tl_sel]
        self._tl_sel = None
        self._tl_redraw()
        self._tl_refresh_effect_list()
        self._tl_invalidate_preview()

    def _tl_set_tool(self, tool):
        self._tl_tool = tool
        for name, btn in self._tool_btns.items():
            btn.configure(fg_color="#1f6aa5" if name == tool else "#333355")
        self._tl_canvas.configure(cursor="" if tool == "select" else "tcross")
        if tool == "razor" and hasattr(self, "_tl_status"):
            self._set_status(self._tl_status, "✂ Clique no clipe onde quer cortar.", "#888888")

    def _tl_split(self, cid, t_abs):
        c = self._tl_get(cid)
        if not c or not (c["start"] + 0.05 < t_abs < c["start"] + c["duration"] - 0.05):
            return
        left = t_abs - c["start"]
        import copy
        right = dict(c)
        right["id"] = self._tl_next_id
        self._tl_next_id += 1
        right["start"] = t_abs
        right["src_in"] = c["src_in"] + left
        right["duration"] = c["duration"] - left
        right["effects"] = copy.deepcopy(c.get("effects", []))
        c["duration"] = left
        self._tl_clips.append(right)
        self._tl_select(right["id"])
        self._tl_invalidate_preview()

    def _tl_set_playhead(self, t):
        self._tl_playhead = max(0.0, min(self._tl_total(), t))
        self._tl_redraw()
        self._pm_time.configure(text=f"{self._fmt_ms(self._tl_playhead * 1000)} / "
                                     f"{self._fmt_ms(self._tl_total() * 1000)}")
        self._tl_show_frame()

    def _tl_on_wheel(self, event):
        self._tl_canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _tl_on_wheel_zoom(self, event):
        t_cursor = self._tl_canvas.canvasx(event.x) / self._tl_pps
        self._tl_zoom(1.15 if event.delta > 0 else 1 / 1.15)
        parts = str(self._tl_canvas.cget("scrollregion")).split()
        width = float(parts[2]) if len(parts) == 4 else max(1, self._tl_canvas.winfo_width())
        target = (t_cursor * self._tl_pps - event.x) / max(1.0, width)
        self._tl_canvas.xview_moveto(max(0.0, min(1.0, target)))
        return "break"

    def _tl_zoom(self, factor):
        self._tl_pps = max(4.0, min(140.0, self._tl_pps * factor))
        self._tl_redraw()

    # — efeitos por clipe —
    def _fx_refresh_params(self):
        for w in self._fx_param_frame.winfo_children():
            w.destroy()
        self._fx_widgets = {}
        op = self._fx_menu.get()
        frame = self._fx_param_frame
        if op == "Velocidade":
            menu = ctk.CTkOptionMenu(frame, values=["0.25x", "0.5x", "1.5x", "2x", "4x"], width=90)
            menu.set("2x")
            menu.pack(side="left")
            self._fx_widgets["speed"] = menu
        elif op == "Girar":
            menu = ctk.CTkOptionMenu(frame, values=["90°", "180°", "270°"], width=80)
            menu.set("90°")
            menu.pack(side="left")
            self._fx_widgets["rotate"] = menu
        elif op == "Espelhar":
            menu = ctk.CTkOptionMenu(frame, values=["Horizontal", "Vertical"], width=120)
            menu.pack(side="left")
            self._fx_widgets["mirror"] = menu
        elif op == "Brilho/Contraste":
            for key, label in (("lum", "Brilho"), ("contrast", "Contraste")):
                ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
                var = ctk.StringVar(value="20")
                ctk.CTkEntry(frame, width=46, textvariable=var, justify="center").pack(side="left", padx=(0, 10))
                self._fx_widgets[key] = var
        elif op == "Fade":
            for key, label in (("fin", "In(s)"), ("fout", "Out(s)")):
                ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
                var = ctk.StringVar(value="1")
                ctk.CTkEntry(frame, width=46, textvariable=var, justify="center").pack(side="left", padx=(0, 10))
                self._fx_widgets[key] = var
        elif op == "Texto/Legenda":
            tvar = ctk.StringVar(value="")
            ctk.CTkEntry(frame, textvariable=tvar, width=150, placeholder_text="texto…").pack(side="left")
            pos = ctk.CTkOptionMenu(frame, values=list(self._ED_POS), width=90)
            pos.set("Embaixo")
            pos.pack(side="left", padx=(6, 0))
            color = ctk.CTkOptionMenu(frame, values=list(self._ED_COLOR), width=90)
            color.pack(side="left", padx=(6, 0))
            self._fx_widgets.update(text=tvar, tpos=pos, tcolor=color)

    def _fx_collect(self):
        op = self._fx_menu.get()
        w = self._fx_widgets
        if op == "Velocidade":
            return {"type": "speed", "factor": float(w["speed"].get().rstrip("x"))}
        if op == "Reverter":
            return {"type": "reverse"}
        if op == "Girar":
            return {"type": "rotate", "degrees": int(w["rotate"].get().rstrip("°"))}
        if op == "Espelhar":
            return {"type": "mirror", "axis": "h" if w["mirror"].get() == "Horizontal" else "v"}
        if op == "Preto e branco":
            return {"type": "grayscale"}
        if op == "Inverter cores":
            return {"type": "invert"}
        if op == "Brilho/Contraste":
            return {"type": "brightcontrast", "lum": int(w["lum"].get() or 0),
                    "contrast": int(w["contrast"].get() or 0)}
        if op == "Fade":
            return {"type": "fade", "fin": float(w["fin"].get() or 0), "fout": float(w["fout"].get() or 0)}
        if op == "Texto/Legenda":
            text = w["text"].get().strip()
            if not text:
                raise ValueError("Digite o texto da legenda.")
            return {"type": "text", "text": text, "position": self._ED_POS[w["tpos"].get()],
                    "color": self._ED_COLOR[w["tcolor"].get()]}
        return None

    def _tl_apply_effect(self):
        c = self._tl_get(self._tl_sel)
        if not c:
            self._set_status(self._tl_status, "✗ Selecione um clipe na timeline.", "#e74c3c")
            return
        if c["kind"] != "video":
            self._set_status(self._tl_status, "✗ Efeitos são para clipes de vídeo.", "#e74c3c")
            return
        try:
            effect = self._fx_collect()
        except (ValueError, KeyError) as exc:
            self._set_status(self._tl_status, f"✗ {exc}", "#e74c3c")
            return
        if effect:
            c.setdefault("effects", []).append(effect)
            self._tl_refresh_effect_list()
            self._tl_invalidate_preview()
            self._set_status(self._tl_status, f"Efeito aplicado: {self._fx_menu.get()}", "#2ecc71")

    def _tl_refresh_effect_list(self):
        for w in self._fx_list.winfo_children():
            w.destroy()
        c = self._tl_get(self._tl_sel)
        if not c:
            ctk.CTkLabel(self._fx_list, text="(nenhum clipe selecionado)",
                         text_color="#888888", font=ctk.CTkFont(size=11)).pack(anchor="w")
            return
        effects = c.get("effects", [])
        if not effects:
            ctk.CTkLabel(self._fx_list, text="(sem efeitos neste clipe)",
                         text_color="#888888", font=ctk.CTkFont(size=11)).pack(anchor="w")
            return
        for idx, ef in enumerate(effects):
            row = ctk.CTkFrame(self._fx_list, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkButton(row, text="✕", width=24, height=22, fg_color="#7a2e2e",
                          hover_color="#9b2321",
                          command=lambda i=idx: self._tl_remove_effect(i)).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(row, text=self._fx_describe(ef), anchor="w",
                         font=ctk.CTkFont(size=11)).pack(side="left")

    @staticmethod
    def _fx_describe(ef):
        t = ef.get("type")
        if t == "speed":
            return f"Velocidade {ef['factor']}x"
        if t == "rotate":
            return f"Girar {ef['degrees']}°"
        if t == "mirror":
            return "Espelhar " + ("horizontal" if ef.get("axis") == "h" else "vertical")
        if t == "brightcontrast":
            return f"Brilho {ef['lum']} / Contraste {ef['contrast']}"
        if t == "fade":
            return f"Fade in {ef.get('fin', 0)}s / out {ef.get('fout', 0)}s"
        if t == "text":
            return f"Texto: {ef['text'][:18]}"
        return {"reverse": "Reverter", "grayscale": "Preto e branco",
                "invert": "Inverter cores"}.get(t, t)

    def _tl_remove_effect(self, idx):
        c = self._tl_get(self._tl_sel)
        if c and 0 <= idx < len(c.get("effects", [])):
            c["effects"].pop(idx)
            self._tl_refresh_effect_list()
            self._tl_invalidate_preview()

    # — preview (Program Monitor) —
    def _tl_invalidate_preview(self):
        if self._tl_prev_after is not None:
            try:
                self.after_cancel(self._tl_prev_after)
            except Exception:
                pass
        self._tl_prev_after = self.after(450, self._tl_rebuild_preview)

    def _tl_rebuild_preview(self):
        self._tl_prev_after = None
        media_editor.configure_ffmpeg(get_ffmpeg_path() or shutil.which("ffmpeg"))
        try:
            self._tl_preview.rebuild(list(self._tl_clips))
        except Exception:
            pass
        self._tl_set_playhead(min(self._tl_playhead, self._tl_total()))

    def _tl_show_frame(self):
        img = self._tl_preview.frame_image(self._tl_playhead, self._PM_W, self._PM_H)
        if img is None:
            self._pm_label.configure(image="", text="(sem vídeo)")
            self._pm_imgref = None
            return
        from PIL import ImageTk
        self._pm_imgref = ImageTk.PhotoImage(img)
        self._pm_label.configure(image=self._pm_imgref, text="")

    def _tl_play_toggle(self):
        if self._tl_total() <= 0:
            return
        self._tl_playing = not self._tl_playing
        self._pm_play.configure(text="⏸" if self._tl_playing else "▶")
        if self._tl_playing:
            if self._tl_playhead >= self._tl_total() - 0.05:
                self._tl_playhead = 0.0
            self._tl_play_step()

    def _tl_play_step(self):
        if not self._tl_playing:
            return
        if self._tl_playhead >= self._tl_total() - 0.05:
            self._tl_playing = False
            self._pm_play.configure(text="▶")
            return
        self._tl_set_playhead(self._tl_playhead + 0.2)
        self.after(120, self._tl_play_step)

    def _tl_on_wheel(self, event):
        self._tl_canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _tl_on_wheel_zoom(self, event):
        t_cursor = self._tl_canvas.canvasx(event.x) / self._tl_pps
        self._tl_zoom(1.15 if event.delta > 0 else 1 / 1.15)
        parts = str(self._tl_canvas.cget("scrollregion")).split()
        width = float(parts[2]) if len(parts) == 4 else max(1, self._tl_canvas.winfo_width())
        target = (t_cursor * self._tl_pps - event.x) / max(1.0, width)
        self._tl_canvas.xview_moveto(max(0.0, min(1.0, target)))
        return "break"

    def _tl_zoom(self, factor):
        self._tl_pps = max(4.0, min(140.0, self._tl_pps * factor))
        self._tl_redraw()

    # — render —
    def _tl_render(self):
        if self._tl_busy:
            return
        if not any(c["kind"] == "video" for c in self._tl_clips):
            self._set_status(self._tl_status, "✗ Adicione ao menos um clipe de vídeo.", "#e74c3c")
            return
        model = [{"path": c["path"], "kind": c["kind"], "start": c["start"],
                  "duration": c["duration"], "src_in": c["src_in"],
                  "effects": c.get("effects", [])} for c in self._tl_clips]
        base = os.path.join(DOWNLOADS_FOLDER, "montagem_timeline")
        out = base + ".mp4"
        i = 2
        while os.path.exists(out):
            out = f"{base}_{i}.mp4"
            i += 1
        self._tl_busy = True
        self._tl_render_btn.configure(state="disabled", text="Renderizando…")
        self._tl_bar.pack(fill="x", padx=12, pady=(0, 2))
        self._tl_bar.configure(mode="indeterminate")
        self._tl_bar.start()
        self._set_status(self._tl_status, "Renderizando… (pode levar um tempo)", "#888888")
        self._tl_log_write(f"→ Renderizando {len(model)} clipe(s)…")
        threading.Thread(target=self._tl_render_run, args=(model, out), daemon=True).start()

    def _tl_render_run(self, model, out):
        try:
            media_editor.configure_ffmpeg(get_ffmpeg_path() or shutil.which("ffmpeg"))
            timeline_editor.render_timeline(model, out, log=lambda m: self.after(0, lambda: self._tl_log_write(m)))
            self.after(0, lambda: self._tl_render_finish(True, out))
        except Exception as exc:
            self.after(0, lambda exc=exc: self._tl_render_finish(False, str(exc)))

    def _tl_render_finish(self, ok, result):
        self._tl_busy = False
        self._tl_bar.stop()
        self._tl_bar.pack_forget()
        self._tl_render_btn.configure(state="normal", text="⬇ Exportar MP4")
        if ok:
            self._tl_log_write(f"✓ Salvo: {os.path.basename(result)}")
            self._set_status(self._tl_status, "✓ Renderizado! Veja na pasta de downloads.", "#2ecc71")
            if hasattr(self, "_lib_items"):
                self._scan_library()
        else:
            self._tl_log_write(f"✗ Erro: {result}")
            self._set_status(self._tl_status, f"✗ {result}", "#e74c3c")

    def _tl_log_write(self, msg):
        self._tl_log.configure(state="normal")
        self._tl_log.insert("end", msg + "\n")
        self._tl_log.see("end")
        self._tl_log.configure(state="disabled")

    # ── YouTube tab ────────────────────────────────────────────────────────

    def _build_youtube_tab(self):
        tab = self._tab_content(self.tabview.tab("  YouTube  "))

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
            entry.bind("<KeyRelease>",
                       lambda e, en=entry, va=variable: self._mask_time(e, en, va))
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
        tab = self._tab_content(self.tabview.tab("  YT Music  "))

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
        tab = self._tab_content(self.tabview.tab("  Spotify  "))

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
        tab = self._tab_content(self.tabview.tab("  Redes Sociais  "))

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
