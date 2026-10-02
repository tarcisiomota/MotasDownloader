import functools
import http.server
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from PIL import Image
from yt_dlp import YoutubeDL
from clip_media import ClipMediaPP
from subtitles import subtitle_choices, read_cues, write_ass

BIN=Path(__file__).resolve().parent/'bin'
FLAGS=subprocess.CREATE_NO_WINDOW

class SubtitleTests(unittest.TestCase):
    def test_priority(self):
        f=lambda name:[{'ext':'json3','name':name}]
        choices=subtitle_choices({'subtitles':{'en':f('English'),'pt':f('Português'),'pt-BR':f('Português Brasil')},'automatic_captions':{'pt':f('Português'),'en':f('English'),'live_chat':f('Chat')}})
        self.assertEqual([(c['code'],c['automatic']) for c in choices], [('pt-BR',False),('pt',False),('pt',True),('en',False),('en',True)])

    def test_normalize_and_safe_styles(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'captions.vtt'
            path.write_text('WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nOlá\n\n00:00:02.000 --> 00:00:04.000\nOlá mundo\n\n00:00:03.000 --> 00:00:05.000\nOlá mundo\n',encoding='utf-8')
            cues=read_cues(path)
            self.assertEqual(cues,[[1,2,'Olá'],[2,5,'Olá mundo']])
            write_ass(path,cues,1920,1080,'Grande','Amarela')
            text=path.read_text(encoding='utf-8')
            self.assertIn('&H0000FFFF',text)
            self.assertIn('Arial,60',text)

    def test_download_burn_and_trim(self):
        with tempfile.TemporaryDirectory(prefix='motas teste ç ') as directory:
            root=Path(directory)
            subprocess.run([str(BIN/'ffmpeg.exe'),'-v','error','-f','lavfi','-i','color=black:s=640x360:d=4:r=25','-c:v','libopenh264',str(root/'input.mp4')],check=True,creationflags=FLAGS)
            (root/'sub.json3').write_text(json.dumps({'events':[{'tStartMs':2000,'dDurationMs':1000,'segs':[{'utf8':'Olá mundo'}]}]}),encoding='utf-8')
            class Handler(http.server.SimpleHTTPRequestHandler):
                def log_message(self,*args):pass
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(root)))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url=f'http://127.0.0.1:{server.server_port}'
            try:
                for color,selection,automatic in [('Branca',(0,None),False),('Amarela',(1,4),True)]:
                    with YoutubeDL({'quiet':True,'noprogress':True,'outtmpl':str(root/(color+'.%(ext)s')),'writesubtitles':not automatic,'writeautomaticsub':automatic,'subtitleslangs':['pt'],'subtitlesformat':'json3','ffmpeg_location':str(BIN)}) as ydl:
                        ydl.add_post_processor(ClipMediaPP(ydl,*selection,str(BIN/'ffmpeg.exe'),subtitles={'code':'pt','size':'Automático','color':color}))
                        ydl.process_ie_result({'id':color,'title':'Teste','url':url+'/input.mp4','ext':'mp4','extractor':'test',('automatic_captions' if automatic else 'subtitles'):{'pt':[{'ext':'json3','url':url+'/sub.json3'}]}},download=True)
                    def pixels(at):
                        png=root/'frame.png'
                        subprocess.run([str(BIN/'ffmpeg.exe'),'-v','error','-y','-ss',str(at),'-i',str(root/(color+'.mp4')),'-frames:v','1',str(png)],check=True,creationflags=FLAGS)
                        return list(Image.open(png).convert('RGB').getdata())
                    self.assertFalse(any(r>100 or g>100 or b>100 for r,g,b in pixels(.5)))
                    painted=pixels(2.5 if selection[1] is None else 1.5)
                    if color=='Amarela':self.assertTrue(any(r>150 and g>150 and b<80 for r,g,b in painted))
                    else:self.assertTrue(any(min(r,g,b)>180 for r,g,b in painted))
            finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
