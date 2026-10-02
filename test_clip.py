import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from clip_media import ClipMediaPP, clock, validate_range
from yt_dlp import YoutubeDL
from yt_dlp.postprocessor.ffmpeg import FFmpegExtractAudioPP
from music_metadata import MusicMetadataPP
from mutagen.id3 import ID3

BIN=Path(__file__).resolve().parent/'bin'

class ClipTests(unittest.TestCase):
    def test_validation(self):
        self.assertEqual(validate_range('00:00:30','00:02:10',269),(30,130))
        self.assertEqual(clock(3661),'01:01:01')
        for a,b,d in [('00:00:10','00:00:10',20),('00:00:11','00:00:10',20),
            ('00:00:00','00:00:21',20),('00:60:00','01:01:00',4000),
            ('1:00','00:01:01',80),('-1:00:00','00:01:00',80),('00:00:00','00:00:01',None)]:
            with self.assertRaises(ValueError): validate_range(a,b,d)

    def test_video_audio_and_tags(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            src=folder/'source.mp4'
            subprocess.run([str(BIN/'ffmpeg.exe'),'-v','error','-f','lavfi','-i',
                'testsrc2=size=320x240:rate=25:duration=4','-f','lavfi','-i',
                'sine=frequency=440:duration=4','-c:v','libopenh264','-b:v','500k',
                '-c:a','aac',str(src)],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
            for mode in ('both','video','audio'):
                path=folder/(mode+'.mp4');path.write_bytes(src.read_bytes())
                if mode=='video':
                    silent=folder/'silent.mp4'
                    subprocess.run([str(BIN/'ffmpeg.exe'),'-v','error','-i',str(path),'-an','-c:v','copy',str(silent)],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
                    path=silent
                with YoutubeDL({'quiet':True,'ffmpeg_location':str(BIN)}) as ydl:
                    pp=ClipMediaPP(ydl,1,3,str(BIN/'ffmpeg.exe'),audio_only=mode=='audio')
                    _, info=pp.run({'filepath':str(path),'ext':'mp4','title':'Teste',
                        'track':'Canção','artists':['Artista'],'album':'Teste','release_year':2001})
                    if mode=='audio':
                        _,info=FFmpegExtractAudioPP(ydl,preferredcodec='mp3',preferredquality='192').run(info)
                        MusicMetadataPP(ydl,artwork=False).run(info)
                        self.assertEqual(str(ID3(info['filepath'])['TIT2']),'Canção')
                    raw=subprocess.check_output([str(BIN/'ffprobe.exe'),'-v','error','-show_format','-show_streams','-of','json',info['filepath']],creationflags=subprocess.CREATE_NO_WINDOW)
                    data=json.loads(raw)
                    self.assertAlmostEqual(float(data['format']['duration']),2,delta=.1)
                    kinds={s['codec_type'] for s in data['streams']}
                    self.assertEqual(kinds,{'audio'} if mode=='audio' else {'video'} if mode=='video' else {'video','audio'})
                    if mode!='audio': self.assertEqual(data['streams'][0]['codec_name'],'h264')

if __name__=='__main__': unittest.main(verbosity=2)
