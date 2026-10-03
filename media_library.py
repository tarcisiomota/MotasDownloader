"""Biblioteca e player de mídia (áudio e vídeo) sobre o libVLC.

O libVLC não acompanha o python-vlc: ele é baixado sob demanda para bin/vlc,
espelhando o mesmo padrão usado para o ffmpeg em app.py.
"""
import os
import shutil
import zipfile
import urllib.request

VLC_VERSION = "3.0.21"
VLC_URL = (f"https://download.videolan.org/pub/videolan/vlc/{VLC_VERSION}"
           f"/win64/vlc-{VLC_VERSION}-win64.zip")

AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".m4v", ".wmv", ".ts"}
MEDIA_EXTS = AUDIO_EXTS | VIDEO_EXTS


def vlc_dir(bin_dir):
    return os.path.join(bin_dir, "vlc")


def has_vlc(bin_dir):
    return os.path.exists(os.path.join(vlc_dir(bin_dir), "libvlc.dll"))


def load_vlc(bin_dir):
    """Prepara os caminhos do libVLC e retorna o módulo vlc (ou None se indisponível)."""
    vdir = vlc_dir(bin_dir)
    dll = os.path.join(vdir, "libvlc.dll")
    if os.path.exists(dll):
        # Overrides documentados do python-vlc + resolução do libvlccore.dll.
        os.environ["PYTHON_VLC_LIB_PATH"] = dll
        os.environ["PYTHON_VLC_MODULE_PATH"] = os.path.join(vdir, "plugins")
        try:
            os.add_dll_directory(vdir)
        except Exception:
            os.environ["PATH"] = vdir + os.pathsep + os.environ.get("PATH", "")
    try:
        import vlc
        return vlc
    except Exception:
        return None


def download_vlc(bin_dir, progress_cb=None):
    """Baixa o libVLC win64 e extrai libvlc.dll, libvlccore.dll e plugins/ para bin/vlc."""
    vdir = vlc_dir(bin_dir)
    os.makedirs(vdir, exist_ok=True)
    zip_path = os.path.join(vdir, "_vlc_dl.zip")

    def _reporthook(count, block, total):
        if total > 0 and progress_cb:
            pct = min(count * block / total, 1.0)
            progress_cb(pct * 0.7, f"Baixando componente de vídeo… {int(pct*100)}%")

    if progress_cb:
        progress_cb(0, "Iniciando download do componente de vídeo…")
    urllib.request.urlretrieve(VLC_URL, zip_path, _reporthook)

    if progress_cb:
        progress_cb(0.72, "Extraindo componente de vídeo…")
    with zipfile.ZipFile(zip_path, "r") as z:
        members = [n for n in z.namelist() if not n.endswith("/")]
        total = len(members) or 1
        for i, name in enumerate(members):
            rel = name.split("/", 1)[1] if "/" in name else name  # tira "vlc-x.y.z/"
            low = rel.lower()
            keep_license = low in ("copying.txt", "copying", "copying.lib", "authors.txt",
                                   "news.txt", "readme.txt")
            if low in ("libvlc.dll", "libvlccore.dll") or low.startswith("plugins/") or keep_license:
                dest = os.path.join(vdir, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with z.open(name) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            if progress_cb and i % 60 == 0:
                progress_cb(0.72 + 0.27 * (i / total), "Extraindo componente de vídeo…")

    os.remove(zip_path)
    if progress_cb:
        progress_cb(1.0, "Componente de vídeo instalado!")


def _read_meta(path, is_video, filename):
    title = os.path.splitext(filename)[0]
    artist, duration = "", 0
    if not is_video:
        try:
            from mutagen import File as MutagenFile
            mf = MutagenFile(path, easy=True)
            if mf is not None:
                if mf.tags:
                    title = (mf.tags.get("title") or [title])[0] or title
                    artist = (mf.tags.get("artist") or [""])[0] or ""
                if mf.info and getattr(mf.info, "length", 0):
                    duration = int(mf.info.length)
        except Exception:
            pass
    return title, artist, duration


def scan_library(folder):
    """Varre a pasta (recursivamente) e retorna a lista de mídias encontradas."""
    items = []
    if not folder or not os.path.isdir(folder):
        return items
    for root, _dirs, files in os.walk(folder):
        for filename in sorted(files, key=str.lower):
            ext = os.path.splitext(filename)[1].lower()
            if ext not in MEDIA_EXTS:
                continue
            path = os.path.join(root, filename)
            is_video = ext in VIDEO_EXTS
            title, artist, duration = _read_meta(path, is_video, filename)
            items.append({
                "path": path, "name": filename, "is_video": is_video,
                "title": title, "artist": artist, "duration": duration,
            })
    items.sort(key=lambda it: it["name"].lower())
    return items


class MediaLibraryPlayer:
    """Wrapper enxuto sobre o python-vlc com saída de vídeo embutível (set_hwnd)."""

    def __init__(self, vlc_module):
        self._vlc = vlc_module
        self._instance = vlc_module.Instance("--quiet", "--no-video-title-show")
        self._player = self._instance.media_player_new()
        self.current_path = None

    def set_output(self, hwnd):
        try:
            self._player.set_hwnd(int(hwnd))
        except Exception:
            pass

    def load(self, path):
        media = self._instance.media_new(path)
        self._player.set_media(media)
        self.current_path = path

    def play(self):
        self._player.play()

    def pause(self):
        self._player.pause()  # alterna play/pause

    def stop(self):
        self._player.stop()

    def is_playing(self):
        return bool(self._player.is_playing())

    def get_state(self):
        return str(self._player.get_state())

    def get_length(self):
        return max(0, self._player.get_length())  # ms

    def get_time(self):
        return max(0, self._player.get_time())  # ms

    def get_position(self):
        return self._player.get_position()  # 0.0–1.0

    def set_position(self, frac):
        self._player.set_position(max(0.0, min(1.0, frac)))

    def set_volume(self, vol):
        self._player.audio_set_volume(int(max(0, min(100, vol))))

    def release(self):
        try:
            self._player.stop()
            self._player.release()
            self._instance.release()
        except Exception:
            pass
