# Dependências

Os pacotes de terceiros não estão incorporados a este arquivo de fontes; são instalados ou baixados durante a compilação. Preserve suas licenças se redistribuir os binários.

- [Python](https://www.python.org/) — PSF License.
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — MIT.
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — Unlicense (dependências com outras licenças).
- [spotDL](https://github.com/spotDL/spotify-downloader) — MIT.
- [Mutagen](https://github.com/quodlibet/mutagen) — GPL v2 ou posterior.
- [Pillow](https://github.com/python-pillow/Pillow) — HPND.
- [FFmpeg](https://ffmpeg.org/) — o script seleciona o build win64-lgpl de [BtbN](https://github.com/BtbN/FFmpeg-Builds).
- [Deno](https://github.com/denoland/deno) — MIT, com componentes de terceiros.
- [PyInstaller](https://pyinstaller.org/) — GPL com exceção para distribuição do bootloader.
- [python-vlc](https://github.com/oaubert/python-vlc) — LGPL v2.1 ou posterior (bindings do libVLC).
- [VLC / libVLC](https://www.videolan.org/vlc/) — LGPL v2.1 ou posterior. Usado na aba Biblioteca
  para reprodução de áudio e vídeo; o runtime (libvlc.dll, libvlccore.dll e `plugins/`) é baixado
  sob demanda de [download.videolan.org](https://download.videolan.org/pub/videolan/vlc/) para
  `bin/vlc`, junto com o respectivo arquivo de licença (`COPYING.LIB`).
- [MoviePy](https://github.com/Zulko/moviepy) — MIT. Edição de vídeo na aba Editar (usa o FFmpeg).
- [PyDub](https://github.com/jiaaro/pydub) — MIT. Edição de áudio na aba Editar (usa o FFmpeg).
  Em Python 3.13+ depende de [audioop-lts](https://github.com/AWhetter/audioop-lts) (Apache-2.0 / PSF).
- [NumPy](https://github.com/numpy/numpy) — BSD-3-Clause (dependência do MoviePy).
- [imageio](https://github.com/imageio/imageio) / [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg)
  — BSD-2-Clause (dependências do MoviePy; apontadas para o FFmpeg empacotado via `IMAGEIO_FFMPEG_EXE`).

As versões Python utilizadas estão em `requirements-lock.txt`. A relação acima resume as dependências principais; consulte também os metadados e as licenças de todas as dependências transitivas.
