import json
from pathlib import Path
import unittest
from audio_options import audio_options, audio_selector, combined_selector, audio_suffix

class AudioTests(unittest.TestCase):
    def test_original_before_dub_and_numeric_quality(self):
        def f(fid,lang,abr,original=False):
            return dict(format_id=fid,language=lang,abr=abr,acodec='opus',vcodec='none',ext='webm',language_preference=10 if original else -1)
        formats=[f('low','pt-BR',48,True),f('english','en-US',160),f('high','pt-BR',135,True)]
        choices=audio_options(formats)
        self.assertEqual(list(choices.values()),['high','low','english'])
        self.assertIn('Português (Brasil) · original · 135 kbps',next(iter(choices)))
        self.assertEqual(audio_selector('english'),'english')
        self.assertEqual(combined_selector('video','english'),'video+english')
        self.assertNotEqual(audio_suffix(formats,'english'),audio_suffix(formats,'high'))
    def test_duplicates_and_no_language(self):
        f=dict(language=None,abr=128,acodec='aac',vcodec='none',ext='m4a')
        choices=audio_options([dict(f,format_id='a'),dict(f,format_id='b')])
        self.assertEqual(len(choices),2)
        self.assertTrue(all('original' not in label for label in choices))
if __name__=='__main__':unittest.main(verbosity=2)
