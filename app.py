import customtkinter as ctk
import threading
import yt_dlp
import subprocess
import os
import sys
import shutil
import urllib.request
import zipfile
import tempfile
from pathlib import Path

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DOWNLOADS_FOLDER = str(Path.home() / "Downloads")
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


class DownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Mota's Downloader")
        self.geometry("760x680")
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

        self._yt_formats     = {}    # format_id -> format dict (from yt-dlp)
        self._yt_info        = None  # full info dict
        self._yt_is_playlist = False # True when analyzed URL is a playlist

        self._build_youtube_tab()
        self._build_ytmusic_tab()
        self._build_spotify_tab()

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

    @property
    def _fg_text(self):
        return "#111111" if not self._is_dark else "#ffffff"

    # ── Helpers ────────────────────────────────────────────────────────────

    def _open_downloads(self):
        os.startfile(DOWNLOADS_FOLDER)

    def _log(self, box, msg):
        box.configure(state="normal")
        box.insert("end", msg + "\n")
        box.see("end")
        box.configure(state="disabled")

    def _set_status(self, label, text, color="active"):
        if color == "active":
            color = self._fg_text
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
        ctk.CTkLabel(scroll, text="Baixe vídeos e áudios do YouTube, YouTube Music e Spotify.",
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
        line("5. Clique em ⬇ Baixar.")
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

        # ── Geral ─────────────────────────────────────────────────────────
        section("⚙  Geral", "#888888")
        line("📁  Downloads — abre a pasta de destino (padrão: C:/Users/.../Downloads).")
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
                self.after(0, lambda: self._set_status(
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
        self.yt_vq = ctk.CTkOptionMenu(self._vq_frame, values=["—"], width=200)
        self.yt_vq.pack(side="left")

        self._aq_frame = ctk.CTkFrame(self._yt_qual_row, fg_color="transparent")
        self._aq_frame.pack(side="left")
        ctk.CTkLabel(self._aq_frame, text="Qualidade áudio:").pack(side="left", padx=(0, 6))
        self.yt_aq = ctk.CTkOptionMenu(self._aq_frame, values=["—"], width=180)
        self.yt_aq.pack(side="left")

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

        self.yt_log = ctk.CTkTextbox(tab, width=720, height=130,
                                      font=ctk.CTkFont(size=10, family="Consolas"))
        self.yt_log.pack(padx=12, pady=6)
        self.yt_log.configure(state="disabled")

    # ── Análise ────────────────────────────────────────────────────────────

    def _start_analyze(self):
        url = self.yt_url.get().strip()
        if not url:
            self._set_status(self.yt_status, "⚠  Cole um link válido.", "orange")
            return

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
                self._yt_audio_opts = {k: audio_opts[k] for k in sorted(audio_opts, key=sort_lbl, reverse=True)}

                title    = info.get("title", "")
                duration = info.get("duration_string", "")
                uploader = info.get("uploader", "")

                self.after(0, lambda: self._update_ui_after_analyze(
                    title, uploader, duration))

        except Exception as exc:
            self.after(0, lambda: self._analyze_error(str(exc)))

    def _update_ui_after_analyze(self, title, uploader, duration, count=0):
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

        self._on_yt_type_change(self.yt_type.get())
        self._yt_opts_frame.pack(fill="x", padx=12, pady=4)
        self.yt_btn.configure(state="normal")
        self._set_status(self.yt_status, "✓  Análise concluída. Configure e clique em Baixar.", "#2ecc71")

    def _analyze_error(self, msg):
        self.yt_analyze_btn.configure(state="normal", text="🔍  Analisar")
        self._set_status(self.yt_status, f"✗  {msg[:80]}", "#e74c3c")
        self._log(self.yt_log, f"ERRO na análise: {msg}\n")

    def _on_yt_type_change(self, value):
        ff = has_ffmpeg()
        is_pl = getattr(self, "_yt_is_playlist", False)

        for w in self._yt_qual_row.winfo_children():
            w.pack_forget()

        audio_labels = list(self._yt_audio_opts.keys()) if hasattr(self, "_yt_audio_opts") and self._yt_audio_opts \
                       else ["320 kbps", "256 kbps", "192 kbps", "128 kbps"]

        if value == "Só Áudio":
            self.yt_aq.configure(values=audio_labels)
            self.yt_aq.set(audio_labels[0])
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
                self.yt_aq.set(audio_labels[0])
                self._aq_frame.pack(side="left")

    # ── Download ───────────────────────────────────────────────────────────

    def _start_yt_download(self):
        url = self.yt_url.get().strip()
        if not url:
            return
        self.yt_btn.configure(state="disabled", text="Baixando…")
        self.yt_analyze_btn.configure(state="disabled")
        self.yt_bar.set(0)
        self._set_status(self.yt_status, "Iniciando download…")
        threading.Thread(target=self._dl_yt, args=(url,), daemon=True).start()

    def _dl_yt(self, url):
        dl_type  = self.yt_type.get()
        vq_label = self.yt_vq.get()
        aq_label = self.yt_aq.get()
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
                    ydl_opts["format"] = "bestaudio/best"
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
                        ydl_opts["format"] = f"{video_fid}+{audio_fid}" if (video_fid and audio_fid) \
                                             else "bestvideo+bestaudio/best"
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

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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
            self.yt_btn.configure(state="normal", text="⬇   Baixar")
            self.yt_analyze_btn.configure(state="normal")

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
            self.after(0, lambda: self._ytm_analyze_error(str(exc)))

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
            if do_meta:
                postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})
            if do_thumb:
                postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
        else:
            self._log(self.ytm_log, "⚠  Sem ffmpeg — baixando no formato original (sem conversão).\n")

        if postprocessors:
            ydl_opts["postprocessors"] = postprocessors

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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


if __name__ == "__main__":
    app = DownloaderApp()
    app.mainloop()
