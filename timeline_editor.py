"""Render e preview de uma timeline multitrack (vídeo + áudio) com MoviePy.

Cada clipe é um dict: {path, kind('video'|'audio'), start, duration, src_in, effects}.
`effects` é uma lista de descritores, ex.: {"type":"speed","factor":2.0},
{"type":"grayscale"}, {"type":"text","text":"Oi","position":"bottom","color":"white"}.
"""
from pathlib import Path


def _probe_media(path):
    """Retorna (kind, duration_segundos) de um arquivo."""
    import media_library
    ext = Path(path).suffix.lower()
    kind = "video" if ext in media_library.VIDEO_EXTS else "audio"
    duration = 0.0
    try:
        from moviepy import VideoFileClip, AudioFileClip
        clip = (VideoFileClip(path) if kind == "video" else AudioFileClip(path))
        try:
            duration = float(clip.duration or 0.0)
        finally:
            clip.close()
    except Exception:
        duration = 0.0
    return kind, duration


def _video_effects(effects):
    """Converte descritores em (lista de fx do MoviePy, lista de descritores de texto)."""
    import moviepy.video.fx as vfx
    objs, texts = [], []
    for ef in effects or []:
        kind = ef.get("type")
        if kind == "speed":
            objs.append(vfx.MultiplySpeed(factor=float(ef["factor"])))
        elif kind == "reverse":
            objs.append(vfx.TimeMirror())
        elif kind == "rotate":
            objs.append(vfx.Rotate(float(ef["degrees"])))
        elif kind == "mirror":
            objs.append(vfx.MirrorX() if ef.get("axis") == "h" else vfx.MirrorY())
        elif kind == "grayscale":
            objs.append(vfx.BlackAndWhite())
        elif kind == "invert":
            objs.append(vfx.InvertColors())
        elif kind == "brightcontrast":
            objs.append(vfx.LumContrast(lum=float(ef["lum"]), contrast=float(ef["contrast"])))
        elif kind == "fade":
            if float(ef.get("fin", 0)) > 0:
                objs.append(vfx.FadeIn(float(ef["fin"])))
            if float(ef.get("fout", 0)) > 0:
                objs.append(vfx.FadeOut(float(ef["fout"])))
        elif kind == "text":
            texts.append(ef)
    return objs, texts


def _apply_text(seg, spec):
    from moviepy import TextClip, CompositeVideoClip
    import media_editor
    txt = TextClip(font=media_editor._default_font(), text=spec["text"],
                   font_size=int(spec.get("font_size", 48)), color=spec.get("color", "white"),
                   stroke_color="black", stroke_width=2).with_duration(seg.duration)
    pos = spec.get("position", "bottom")
    if pos == "top":
        txt = txt.with_position(("center", 30))
    elif pos == "center":
        txt = txt.with_position("center")
    else:
        txt = txt.with_position(("center", seg.h - txt.h - 30))
    return CompositeVideoClip([seg, txt]).with_duration(seg.duration)


def _make_segment(clip):
    """Abre a fonte e devolve (base_aberta, segmento_posicionado, kind)."""
    from moviepy import VideoFileClip, AudioFileClip
    src_in = float(clip.get("src_in", 0.0))
    start = float(clip.get("start", 0.0))
    duration = clip.get("duration")
    if clip["kind"] == "video":
        base = VideoFileClip(clip["path"])
        seg = base.subclipped(src_in, src_in + duration) if duration else base
        objs, texts = _video_effects(clip.get("effects"))
        if objs:
            seg = seg.with_effects(objs)
        for spec in texts:
            seg = _apply_text(seg, spec)
        return base, seg.with_start(start), "video"
    base = AudioFileClip(clip["path"])
    seg = base.subclipped(src_in, src_in + duration) if duration else base
    return base, seg.with_start(start), "audio"


def build_composite(clips):
    """Monta o CompositeVideoClip final. Devolve (final, abertos, duração, tamanho, fps)."""
    from moviepy import CompositeVideoClip, CompositeAudioClip
    if not any(c["kind"] == "video" for c in clips):
        raise ValueError("Adicione pelo menos um clipe de vídeo na trilha de vídeo.")
    opened, video_segs, audio_segs = [], [], []
    base_for_seg = []
    for clip in clips:
        base, seg, kind = _make_segment(clip)
        opened.append(base)
        if kind == "video":
            video_segs.append(seg)
            base_for_seg.append(base)
        else:
            audio_segs.append(seg)
    size = max((v.size for v in video_segs), key=lambda s: s[0] * s[1])
    total = max((s.start + s.duration for s in video_segs + audio_segs), default=0.0)
    fps = next((getattr(b, "fps", None) for b in base_for_seg if getattr(b, "fps", None)), 24)
    final = CompositeVideoClip(video_segs, size=size).with_duration(total)
    audios = []
    if final.audio is not None:
        audios.append(final.audio)
    audios.extend(audio_segs)
    if audios:
        final = final.with_audio(CompositeAudioClip(audios))
    return final, opened, total, size, fps


def render_timeline(clips, out_path, fps=None, log=None):
    if log:
        log(f"Compondo {len(clips)} clipe(s)…")
    final, opened, total, _size, src_fps = build_composite(clips)
    try:
        final.write_videofile(out_path, codec="libx264", audio_codec="aac",
                              fps=fps or src_fps or 24, logger=None)
    finally:
        for clip in opened:
            try:
                clip.close()
            except Exception:
                pass
    return out_path


class TimelinePreview:
    """Mantém o composite aberto para extrair o quadro no playhead (preview scrub)."""

    def __init__(self):
        self._final = None
        self._opened = []
        self.duration = 0.0
        self.size = (0, 0)

    def rebuild(self, clips):
        self.close()
        try:
            self._final, self._opened, self.duration, self.size, _fps = build_composite(clips)
        except Exception:
            self._final, self.duration = None, 0.0

    def frame_image(self, t, max_w=480, max_h=270):
        if self._final is None or self.duration <= 0:
            return None
        from PIL import Image
        t = max(0.0, min(self.duration - 0.05, float(t)))
        try:
            arr = self._final.get_frame(t)
        except Exception:
            return None
        img = Image.fromarray(arr)
        img.thumbnail((max_w, max_h))
        return img

    def close(self):
        for clip in self._opened:
            try:
                clip.close()
            except Exception:
                pass
        self._opened = []
        self._final = None
