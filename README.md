# Mota's Downloader

> *"Depois de sofrer muito com malwares infectando o PC do meu pai — que tem a tendência de baixar qualquer coisa que aparece na tela — resolvi desenvolver esse singelo aplicativo. Ele faz tudo o que ele precisa relacionado a downloads de mídias que, convenhamos, ele não deveria eticamente fazer. Mas ei, pelo menos agora o antivírus para de chorar."*
>
> — Tarcísio, filho sofrido e desenvolvedor por necessidade

---

## O que é isso?

**Mota's Downloader** é um aplicativo Windows com interface gráfica para baixar vídeos e áudios de plataformas populares, de forma simples, rápida e sem precisar instalar nada extra.

### O que você pode baixar

| Plataforma | O que suporta |
|---|---|
| **YouTube** | Vídeos (até 4K), playlists, áudio em MP3 |
| **YouTube Music** | Músicas e playlists com metadados e capa do álbum |
| **Spotify** | Músicas, álbuns e playlists completas em MP3 |

---

## Funcionalidades

- 🔍 **Análise de formatos** — antes de baixar, o app inspeciona os streams reais disponíveis e popula os dropdowns com as opções exatas do vídeo/música
- 📋 **Suporte a playlists** — detecta automaticamente e organiza os downloads em subpastas
- 🎵 **Conversão de áudio** — MP3, M4A, WAV, FLAC com qualidade configurável (128k–320k)
- 🖼️ **Metadados e capa** — embute título, artista, álbum e thumbnail nos arquivos de áudio
- ⬇️ **Auto-instalação do ffmpeg** — se o ffmpeg não for encontrado, o app baixa e instala automaticamente com um clique
- 🌙 **Tema claro e escuro** — porque ninguém merece queimar os olhos às 3 da manhã
- 📁 **Abre a pasta Downloads** com um clique

---

## Tecnologias utilizadas

| Componente | Tecnologia |
|---|---|
| Interface gráfica | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) |
| Download YouTube | [yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| Download Spotify | [spotdl](https://github.com/spotDL/spotify-downloader) |
| Processamento de áudio/vídeo | [FFmpeg](https://ffmpeg.org) |
| Empacotamento | [PyInstaller](https://pyinstaller.org) |
| Linguagem | Python 3.x |
| Instalador Windows | [Inno Setup](https://jrsoftware.org/isinfo.php) |

---

## Download

👉 **[Baixar a última versão (MediaDownloader_Setup.exe)](../../releases/latest)**

> O instalador já inclui tudo que precisa. Basta instalar e usar.

---

## Como usar

1. **Cole o link** (YouTube, YouTube Music ou Spotify)
2. **Clique em Analisar** (YouTube e YT Music) para ver os formatos disponíveis
3. **Configure** resolução, formato e qualidade
4. **Clique em Baixar**

Consulte o botão **`?`** dentro do app para instruções detalhadas de cada aba.

---

## Licença e uso

Este software é disponibilizado **gratuitamente para uso pessoal**.

**Não é permitido o uso para fins comerciais.**
Quem fizer isso... bem, o capeta vai visitar mais cedo ou mais tarde. Você foi avisado. 😈

---

*Feito com ☕, paciência e muito amor filial.*
