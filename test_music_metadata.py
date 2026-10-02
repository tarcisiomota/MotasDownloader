import functools
import http.server
import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from PIL import Image
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from mutagen.wave import WAVE
import yt_dlp
from music_metadata import resolve_music_tags, MusicMetadataPP, write_music_tags, read_cover

BASE = Path(__file__).resolve().parent
FFMPEG = BASE / 'bin' / 'ffmpeg.exe'


class MetadataRules(unittest.TestCase):
    def test_native_priority_and_release_year(self):
        tags, source = resolve_music_tags({'track':'Canção', 'artists':['Ana','José'],
            'album':'Disco', 'release_date':'19970512', 'upload_date':'20260909',
            'uploader':'Canal', 'description':'Artista: Outro\nAno: 2020'})
        self.assertEqual(tags,dict(title='Canção',artist='Ana; José',album='Disco',year='1997'))
        self.assertEqual(source['artist'], 'dados musicais do link')

    def test_missing_data_does_not_guess(self):
        tags,_ = resolve_music_tags({'title':'Nome - Ao vivo 2026 (Official)',
            'uploader':'Canal aleatório', 'creator':'Outro canal', 'upload_date':'20260909',
            'description':'Filmado em 2026. Conheça nosso álbum! ℗ 2020 gravadora'})
        self.assertEqual(tags, dict(title='Nome - Ao vivo 2026 (Official)',artist='',album='',year=''))

    def test_explicit_description_and_accents(self):
        tags,_ = resolve_music_tags({'title':'Vídeo', 'description':
            'Música: Canção\nArtista: João\nÁlbum: Estações\nReleased on: 2001-02-03'})
        self.assertEqual(tags,dict(title='Canção',artist='João',album='Estações',year='2001'))

    def test_ambiguous_descriptions_are_not_guessed(self):
        tags,_ = resolve_music_tags({'title':'Coletânea','description':
            'Artista: Ana\nArtista: Bia\nÁlbum: Um\nÁlbum: Dois\nAno: 2000\nAno: 2001'})
        self.assertEqual(tags,dict(title='Coletânea',artist='',album='',year=''))

    def test_invalid_dates_and_unlabelled_title(self):
        tags,_ = resolve_music_tags({'title':'Artista - Música', 'release_date':'20260230',
            'description':'Released on: 2026-99-99\nYear: 20xx'})
        self.assertEqual(tags['year'],'')
        self.assertEqual(tags['artist'],'')


class MediaPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='motas-tags-', dir=BASE)
        cls.root = Path(cls.temp.name)
        subprocess.run([str(FFMPEG),'-v','error','-f','lavfi','-i',
            'sine=frequency=440:duration=0.15',str(cls.root/'tone.wav')],check=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
        Image.new('RGB',(320,180),(45,120,200)).save(cls.root/'cover.webp')
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args): pass
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(cls.root)))
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()

    def test_download_convert_embed_all_formats(self):
        for ext in ('mp3','m4a','flac','wav'):
            with self.subTest(format=ext):
                directory = self.root/ext
                opts = {'quiet':True,'noprogress':True,'ffmpeg_location':str(FFMPEG.parent),
                    'outtmpl':str(directory/'%(id)s.%(ext)s'),'writethumbnail':True,
                    'postprocessors':[{'key':'FFmpegExtractAudio','preferredcodec':ext}]}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.add_post_processor(MusicMetadataPP(ydl))
                    # A playlist proves that tags cannot leak between tracks.
                    entries = [dict(id='first',title='Video first',track='Canção',artists=['João'],
                        album='Estações',release_year=1999),dict(id='second',title='Vídeo sem créditos')]
                    for entry in entries:
                        entry.update(url=self.url+'/tone.wav',ext='wav',uploader='Canal errado',
                            upload_date='20260909',extractor='test',webpage_url='https://youtube.com/watch?v=test',
                            thumbnails=[{'url':self.url+'/cover.webp','id':'0'}])
                    ydl.process_ie_result({'_type':'playlist','id':'playlist','title':'Test',
                        'extractor':'test','extractor_key':'Test','entries':entries},download=True)
                first, second = directory/f'first.{ext}', directory/f'second.{ext}'
                self.assertTrue(first.exists())
                if ext in ('mp3','wav'):
                    a = ID3(first) if ext == 'mp3' else WAVE(first).tags
                    b = ID3(second) if ext == 'mp3' else WAVE(second).tags
                    self.assertEqual(str(a['TIT2']),'Canção')
                    self.assertEqual(str(a['TPE1']),'João')
                    self.assertEqual(str(a['TALB']),'Estações')
                    self.assertEqual(str(a['TDRC']),'1999')
                    self.assertEqual(a.version[1],3)
                    self.assertEqual(a.getall('APIC')[0].mime,'image/jpeg')
                    self.assertEqual(str(b['TIT2']),'Vídeo sem créditos')
                    self.assertNotIn('TPE1',b)
                    self.assertNotIn('TALB',b)
                    self.assertNotIn('TDRC',b)
                elif ext == 'm4a':
                    a,b = MP4(first),MP4(second)
                    self.assertEqual(a['\xa9nam'],['Canção'])
                    self.assertEqual(a['\xa9ART'],['João'])
                    self.assertEqual(a['\xa9alb'],['Estações'])
                    self.assertEqual(a['\xa9day'],['1999'])
                    self.assertTrue(a['covr'])
                    self.assertNotIn('\xa9ART',b)
                    self.assertNotIn('\xa9day',b)
                else:
                    a,b = FLAC(first),FLAC(second)
                    self.assertEqual(a['title'],['Canção'])
                    self.assertEqual(a['artist'],['João'])
                    self.assertEqual(a['album'],['Estações'])
                    self.assertEqual(a['date'],['1999'])
                    self.assertEqual(a.pictures[0].mime,'image/jpeg')
                    self.assertNotIn('artist',b)
                    self.assertNotIn('date',b)
                self.assertEqual(list(directory.glob('*.webp')),[])

    def test_missing_image_and_metadata_checkbox(self):
        filename = self.root/'switches.wav'
        filename.write_bytes((self.root/'tone.wav').read_bytes())
        original = dict(title='Original',artist='Ana',album='Um',year='2000')
        write_music_tags(filename,original)
        pp = MusicMetadataPP(metadata=False,artwork=True)
        pp.run(dict(filepath=str(filename), title='Outro', thumbnails=[]))
        self.assertEqual(str(WAVE(filename).tags['TIT2']),'Original')
        pp = MusicMetadataPP(metadata=True,artwork=False)
        pp.run(dict(filepath=str(filename), title='Novo',uploader='Canal',upload_date='20260909'))
        tags = WAVE(filename).tags
        self.assertEqual(str(tags['TIT2']),'Novo')
        self.assertNotIn('TPE1',tags)
        self.assertNotIn('TDRC',tags)
        self.assertFalse(tags.getall('APIC'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
