"""Offline diagnostic for the packaged dependencies, invoked explicitly."""
import json
import subprocess
import tempfile
from pathlib import Path
from PIL import Image
from mutagen.id3 import ID3
from music_metadata import MusicMetadataPP

def run(root):
    with tempfile.TemporaryDirectory(prefix='tags-') as tmp:
        tmp = Path(tmp)
        audio, artwork = tmp / 'teste.mp3', tmp / 'imagem.webp'
        subprocess.run([str(root/'bin'/'ffmpeg.exe'), '-v', 'error', '-f', 'lavfi',
            '-i', 'sine=frequency=440:duration=0.1', str(audio)],check=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
        Image.new('RGB',(64,64),(40,140,220)).save(artwork)
        MusicMetadataPP().run({'filepath':str(audio), 'title':'Título do vídeo',
            'description':'Música: Canção\nArtista: João\nÁlbum: Estações\nAno: 1999',
            'upload_date':'20260909', 'uploader':'Canal',
            'thumbnails':[{'filepath':str(artwork)}]})
        tags = ID3(audio)
        assert tags.version[1] == 3
        assert str(tags['TIT2']) == 'Canção'
        assert str(tags['TPE1']) == 'João'
        assert str(tags['TALB']) == 'Estações'
        assert str(tags['TDRC']) == '1999'
        assert tags.getall('APIC')[0].data.startswith(b'\xff\xd8')
        print(json.dumps({'ok':True,'id3':'2.3','title':str(tags['TIT2']),
            'artist':str(tags['TPE1']),'year':str(tags['TDRC']),'artwork':True},ensure_ascii=True))
