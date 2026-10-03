"""Edição simples de áudio (PyDub) e vídeo (MoviePy) usando o FFmpeg empacotado.

Todas as funções recebem o caminho do ffmpeg (bin/ffmpeg.exe) e gravam o
resultado ao lado do arquivo-fonte (ou em out_dir), com um sufixo descritivo.
"""
import os
from pathlib import Path

AUDIO_EXPORT = {  # rótulo -> (extensão, formato pydub)
    "MP3": (".mp3", "mp3"),
    "WAV": (".wav", "wav"),
    "FLAC": (".flac", "flac"),
    "OGG": (".ogg", "ogg"),
}

_EXT_FMT = {".mp3": "mp3", ".wav": "wav", ".flac": "flac", ".ogg": "ogg",
            ".m4a": "ipod", ".aac": "adts", ".opus": "opus", ".wma": "asf"}

_configured = False


def configure_ffmpeg(ffmpeg_path):
    """Aponta PyDub, MoviePy e imageio-ffmpeg para o ffmpeg empacotado."""
    global _configured
    if not ffmpeg_path:
        return
    ffmpeg_path = str(ffmpeg_path)
    ffdir = os.path.dirname(ffmpeg_path)
    ffprobe = os.path.join(ffdir, "ffprobe.exe")
    os.environ["FFMPEG_BINARY"] = ffmpeg_path
    os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_path
    # PyDub procura "ffprobe"/"ffmpeg" pelo nome no PATH; garante que bin/ esteja lá.
    if ffdir and ffdir not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = ffdir + os.pathsep + os.environ.get("PATH", "")
    from pydub import AudioSegment
    AudioSegment.converter = ffmpeg_path
    AudioSegment.ffmpeg = ffmpeg_path
    if os.path.exists(ffprobe):
        AudioSegment.ffprobe = ffprobe
    _configured = True


def _dest(src, suffix, out_dir=None, new_ext=None):
    p = Path(src)
    ext = new_ext if new_ext else p.suffix
    folder = Path(out_dir) if out_dir else p.parent
    return str(folder / (p.stem + suffix + ext))


def _fmt_for_ext(ext):
    return _EXT_FMT.get(ext.lower(), "mp3")


# ── Áudio (PyDub) ────────────────────────────────────────────────────────────

def _load_audio(src):
    from pydub import AudioSegment
    return AudioSegment.from_file(src)


def audio_trim(src, start_s, end_s, out_dir=None):
    seg = _load_audio(src)[int(start_s * 1000):int(end_s * 1000)]
    ext = Path(src).suffix
    out = _dest(src, "_corte", out_dir, ext)
    seg.export(out, format=_fmt_for_ext(ext))
    return out


def audio_gain(src, db, out_dir=None):
    seg = _load_audio(src) + float(db)
    ext = Path(src).suffix
    out = _dest(src, f"_vol{int(db):+d}dB", out_dir, ext)
    seg.export(out, format=_fmt_for_ext(ext))
    return out


def audio_fade(src, fade_in_s, fade_out_s, out_dir=None):
    seg = _load_audio(src)
    if fade_in_s > 0:
        seg = seg.fade_in(int(fade_in_s * 1000))
    if fade_out_s > 0:
        seg = seg.fade_out(int(fade_out_s * 1000))
    ext = Path(src).suffix
    out = _dest(src, "_fade", out_dir, ext)
    seg.export(out, format=_fmt_for_ext(ext))
    return out


def audio_normalize(src, out_dir=None):
    from pydub.effects import normalize
    seg = normalize(_load_audio(src))
    ext = Path(src).suffix
    out = _dest(src, "_normalizado", out_dir, ext)
    seg.export(out, format=_fmt_for_ext(ext))
    return out


def audio_convert(src, target_label, out_dir=None):
    ext, fmt = AUDIO_EXPORT[target_label]
    seg = _load_audio(src)
    out = _dest(src, "", out_dir, ext)
    if os.path.abspath(out) == os.path.abspath(src):
        out = _dest(src, "_convertido", out_dir, ext)
    seg.export(out, format=fmt)
    return out


# ── Vídeo (MoviePy) ──────────────────────────────────────────────────────────

def video_trim(src, start_s, end_s, out_dir=None):
    from moviepy import VideoFileClip
    out = _dest(src, "_corte", out_dir, ".mp4")
    clip = VideoFileClip(src)
    try:
        sub = clip.subclipped(float(start_s), float(end_s))
        sub.write_videofile(out, codec="libx264", audio_codec="aac", logger=None)
    finally:
        clip.close()
    return out


def video_extract_audio(src, target_label="MP3", out_dir=None):
    from moviepy import VideoFileClip
    ext, _fmt = AUDIO_EXPORT[target_label]
    out = _dest(src, "", out_dir, ext)
    if os.path.abspath(out) == os.path.abspath(src):
        out = _dest(src, "_audio", out_dir, ext)
    clip = VideoFileClip(src)
    try:
        if clip.audio is None:
            raise ValueError("Este vídeo não tem faixa de áudio.")
        clip.audio.write_audiofile(out, logger=None)
    finally:
        clip.close()
    return out


def video_mute(src, out_dir=None):
    from moviepy import VideoFileClip
    out = _dest(src, "_sem_audio", out_dir, ".mp4")
    clip = VideoFileClip(src)
    try:
        clip.without_audio().write_videofile(out, codec="libx264", logger=None)
    finally:
        clip.close()
    return out


# ── Efeitos de vídeo (MoviePy fx) ─────────────────────────────────────────────

def _default_font():
    windir = os.environ.get("WINDIR", "C:/Windows")
    for name in ("arial.ttf", "segoeui.ttf", "calibri.ttf", "verdana.ttf", "tahoma.ttf"):
        path = os.path.join(windir, "Fonts", name)
        if os.path.exists(path):
            return path
    return None


def _apply_video(src, effects, suffix, out_dir):
    from moviepy import VideoFileClip
    out = _dest(src, suffix, out_dir, ".mp4")
    clip = VideoFileClip(src)
    try:
        clip.with_effects(effects).write_videofile(out, codec="libx264",
                                                   audio_codec="aac", logger=None)
    finally:
        clip.close()
    return out


def video_speed(src, factor, out_dir=None):
    import moviepy.video.fx as vfx
    factor = float(factor)
    label = str(factor).rstrip("0").rstrip(".") if "." in str(factor) else str(factor)
    return _apply_video(src, [vfx.MultiplySpeed(factor=factor)], f"_{label}x", out_dir)


def video_reverse(src, out_dir=None):
    import moviepy.video.fx as vfx
    return _apply_video(src, [vfx.TimeMirror()], "_reverso", out_dir)


def video_rotate(src, degrees, out_dir=None):
    import moviepy.video.fx as vfx
    return _apply_video(src, [vfx.Rotate(float(degrees))], f"_girado{int(degrees)}", out_dir)


def video_mirror(src, axis, out_dir=None):
    import moviepy.video.fx as vfx
    effect = vfx.MirrorX() if axis == "h" else vfx.MirrorY()
    return _apply_video(src, [effect], "_espelhado", out_dir)


def video_grayscale(src, out_dir=None):
    import moviepy.video.fx as vfx
    return _apply_video(src, [vfx.BlackAndWhite()], "_pb", out_dir)


def video_invert(src, out_dir=None):
    import moviepy.video.fx as vfx
    return _apply_video(src, [vfx.InvertColors()], "_invertido", out_dir)


def video_bright_contrast(src, lum, contrast, out_dir=None):
    import moviepy.video.fx as vfx
    return _apply_video(src, [vfx.LumContrast(lum=float(lum), contrast=float(contrast))],
                        "_ajuste", out_dir)


def video_fade(src, fade_in_s, fade_out_s, out_dir=None):
    import moviepy.video.fx as vfx
    effects = []
    if fade_in_s > 0:
        effects.append(vfx.FadeIn(float(fade_in_s)))
    if fade_out_s > 0:
        effects.append(vfx.FadeOut(float(fade_out_s)))
    if not effects:
        raise ValueError("Informe fade in e/ou fade out em segundos.")
    return _apply_video(src, effects, "_fade", out_dir)


def video_text(src, text, position="bottom", font_size=48, color="white", out_dir=None):
    from moviepy import VideoFileClip, TextClip, CompositeVideoClip
    if not text.strip():
        raise ValueError("Digite o texto da legenda.")
    out = _dest(src, "_texto", out_dir, ".mp4")
    clip = VideoFileClip(src)
    try:
        txt = TextClip(font=_default_font(), text=text, font_size=int(font_size),
                       color=color, stroke_color="black", stroke_width=2)
        txt = txt.with_duration(clip.duration)
        if position == "top":
            txt = txt.with_position(("center", 30))
        elif position == "center":
            txt = txt.with_position("center")
        else:
            txt = txt.with_position(("center", clip.h - txt.h - 30))
        CompositeVideoClip([clip, txt]).write_videofile(out, codec="libx264",
                                                        audio_codec="aac", logger=None)
    finally:
        clip.close()
    return out
