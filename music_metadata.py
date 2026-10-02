"""Deterministic music tags from the supplied video's metadata and description."""
import io
import re
import unicodedata
from datetime import date
from pathlib import Path

from PIL import Image
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TALB, TDRC, APIC
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE
from yt_dlp.postprocessor.common import PostProcessor


def clean(value):
    return re.sub(r'\s+', ' ', value).strip() if isinstance(value, str) else ''


def year(value):
    text = str(value or '').strip()
    if re.fullmatch(r'\d{4}', text):
        number = int(text)
        return text if 1000 <= number <= 2999 else ''
    if re.fullmatch(r'\d{8}|\d{4}-\d{2}-\d{2}', text):
        digits = text.replace('-', '')
        try:
            date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
            return year(digits[:4])
        except ValueError:
            pass
    return ''


LABELS = {
    'title': 'title', 'song': 'title', 'track': 'title', 'titulo': 'title',
    'musica': 'title', 'faixa': 'title',
    'artist': 'artist', 'artists': 'artist', 'artista': 'artist', 'artistas': 'artist',
    'album': 'album',
    'year': 'year', 'ano': 'year', 'release year': 'year',
    'released on': 'year', 'release date': 'year', 'data de lancamento': 'year',
    'ano de lancamento': 'year',
}


def resolve_music_tags(info):
    """No uploader/upload_date fallbacks, title splitting or external lookup."""
    description = info.get('description') or ''
    candidates = {key: set() for key in ('title', 'artist', 'album', 'year')}
    for line in description.splitlines():
        match = re.fullmatch(r'\s*([^:\n]{1,40})\s*:\s*(\S.*?)\s*', line)
        if not match:
            continue
        label = ''.join(c for c in unicodedata.normalize('NFKD', match[1].lower())
                        if not unicodedata.combining(c)).strip()
        key = LABELS.get(label)
        if key:
            value = year(match[2]) if key == 'year' else clean(match[2])
            if value:
                candidates[key].add(value)
    explicit = {key: next(iter(values)) for key, values in candidates.items() if len(values) == 1}
    artists = info.get('artists')
    if isinstance(artists, (list, tuple)):
        artist = '; '.join(dict.fromkeys(clean(a) for a in artists if clean(a)))
    else:
        artist = ''
    native = {
        'title': clean(info.get('track')),
        'artist': artist or clean(info.get('artist')),
        'album': clean(info.get('album')),
        'year': year(info.get('release_date')) or year(info.get('release_year')),
    }
    tags, sources = {}, {}
    for key in candidates:
        if native[key]:
            tags[key], sources[key] = native[key], 'dados musicais do link'
        elif explicit.get(key):
            tags[key], sources[key] = explicit[key], 'campo explícito da descrição'
        else:
            tags[key] = ''
    if not tags['title']:
        tags['title'] = clean(info.get('title'))
        if tags['title']:
            sources['title'] = 'título do vídeo'
    return tags, sources


def read_cover(info):
    """Use only an image already downloaded by yt-dlp from this video's page."""
    for item in reversed(info.get('thumbnails') or []):
        filename = item.get('filepath')
        if not filename or not Path(filename).is_file():
            continue
        with Image.open(filename) as original:
            image = original.convert('RGB')
            image.thumbnail((1600, 1600))
            stream = io.BytesIO()
            image.save(stream, format='JPEG', quality=92)
            return stream.getvalue(), image.width, image.height, filename
    return None


def write_music_tags(filename, tags, cover=None, metadata=True):
    """MP3/WAV use ID3v2.3; M4A/FLAC use their native metadata formats."""
    ext = Path(filename).suffix.lower()
    if ext in ('.mp3', '.wav'):
        wave = WAVE(filename) if ext == '.wav' else None
        if wave is not None:
            if wave.tags is None:
                wave.add_tags()
            target = wave.tags
        else:
            try:
                target = ID3(filename)
            except ID3NoHeaderError:
                target = ID3()
        if metadata:
            # Remove inherited fields that can otherwise claim upload/channel data.
            for key in ('TIT2', 'TPE1', 'TPE2', 'TALB', 'TDRC', 'TYER', 'TDAT', 'TIME', 'TDOR', 'TORY'):
                target.delall(key)
            for key, frame in [('title', TIT2), ('artist', TPE1), ('album', TALB), ('year', TDRC)]:
                if tags[key]:
                    target.add(frame(encoding=1, text=[tags[key]]))
        if cover:
            target.delall('APIC')
            target.add(APIC(encoding=1, mime='image/jpeg', type=3, desc='Capa', data=cover[0]))
        if wave is not None:
            wave.save(v2_version=3)
        else:
            target.save(filename, v2_version=3)
    elif ext == '.m4a':
        target = MP4(filename)
        if target.tags is None:
            target.add_tags()
        if metadata:
            for key in ('\xa9nam', '\xa9ART', 'aART', '\xa9alb', '\xa9day'):
                target.tags.pop(key, None)
            for key, atom in [('title', '\xa9nam'), ('artist', '\xa9ART'), ('album', '\xa9alb'), ('year', '\xa9day')]:
                if tags[key]:
                    target[atom] = [tags[key]]
        if cover:
            target['covr'] = [MP4Cover(cover[0], imageformat=MP4Cover.FORMAT_JPEG)]
        target.save()
    elif ext == '.flac':
        target = FLAC(filename)
        if metadata:
            for key in ('title', 'artist', 'albumartist', 'album_artist', 'album', 'date', 'year', 'originaldate', 'originalyear'):
                target.pop(key, None)
            for key, tag in [('title', 'title'), ('artist', 'artist'), ('album', 'album'), ('year', 'date')]:
                if tags[key]:
                    target[tag] = [tags[key]]
        if cover:
            picture = Picture()
            picture.type, picture.mime, picture.desc = 3, 'image/jpeg', 'Capa'
            picture.data, picture.width, picture.height = cover[:3]
            picture.depth = 24
            target.clear_pictures()
            target.add_picture(picture)
        target.save()
    else:
        raise ValueError(f'Formato de metadados não suportado: {ext}')


class MusicMetadataPP(PostProcessor):
    def __init__(self, downloader=None, metadata=True, artwork=True, log=None):
        super().__init__(downloader)
        self.metadata, self.artwork, self.log = metadata, artwork, log

    def run(self, info):
        tags, sources = resolve_music_tags(info)
        cover = None
        if self.artwork:
            try:
                cover = read_cover(info)
            except Exception as exc:
                if self.log:
                    self.log(f'⚠ Imagem não incorporada: {exc}')
        write_music_tags(info['filepath'], tags, cover, self.metadata)
        if self.log:
            if self.metadata:
                labels = {'title': 'Música', 'artist': 'Artista', 'album': 'Álbum', 'year': 'Ano'}
                for key, label in labels.items():
                    self.log(f'{label}: {tags[key]} ({sources[key]})' if tags[key]
                             else f'{label}: não informado no link; campo vazio.')
            if self.artwork:
                self.log('✓ Imagem do link incorporada.' if cover else 'Imagem não disponível no link.')
        # Let yt-dlp remove its downloaded sidecar after embedding.
        return ([cover[3]] if cover else []), info
