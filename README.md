# Mota's Downloader — portátil v4.3

Aplicativo Windows para YouTube, YouTube Music e Spotify, com metadados musicais automáticos sem IA. Esta é uma adaptação do [projeto de Tarcísio Mota](https://github.com/tarcisiomota/MotasDownloader). Preserve a licença e os créditos originais ao publicar uma cópia.

## Funcionalidades

- Vídeo, somente vídeo ou somente áudio; suporte a playlists.
- Downloads de YouTube, YouTube Music, Spotify e redes sociais (TikTok, Twitter/X, Instagram, Facebook).
- Conversão para MP3, M4A, WAV e FLAC.
- Tags musicais e imagem do próprio link. Prioridade para campos musicais; depois, campos explícitos da descrição. Sem informação confiável, artista, álbum e ano ficam vazios.
- MP3/WAV usam ID3v2.3; M4A/FLAC usam seus formatos nativos.
- Spotify usa spotDL para localizar o áudio no YouTube/YouTube Music; não inclui o aplicativo Spotify.
- **Biblioteca**: player de áudio e vídeo embutido (libVLC) com lista e playlist.
- **Editar Vídeo**: editor em linha do tempo (timeline) com trilhas de vídeo/áudio, ferramenta de corte (razor), playhead com preview por quadro (Program Monitor) e efeitos por clipe (velocidade, reverter, girar, espelhar, preto e branco, inverter cores, brilho/contraste, fade e texto/legenda). Exporta a sequência em MP4.
- Seletor de pasta de download com a escolha salva entre sessões.
- Versão compilada guarda downloads e dados na própria pasta.

## Novidades até a v4.3

- Recorte com início e fim para vídeos individuais, com ou sem áudio.
- Legendas do link gravadas na imagem; português prioritário, preferindo o autor.
- Tamanho automático ou ajustável; texto branco/amarelo com contorno preto.
- Idioma, qualidade e codec no seletor de áudio; prioridade para a faixa original.
- Temas claro/escuro e menu Colar nas caixas de URL.
- Recorte e legendas recodificam o vídeo para MP4 H.264; o arquivo inteiro é baixado antes.

## Novidades do pós-v4.3

- Aba **Biblioteca** com player de áudio/vídeo (libVLC baixado sob demanda).
- Aba **Editar Vídeo** no estilo editor profissional: timeline multitrack, corte, playhead com Program Monitor (preview por quadro) e efeitos aplicados por clipe via MoviePy; exportação em MP4.
- Seletor de pasta de download (botão "Alterar…") com persistência.
- Máscara de tempo nos campos de recorte (digite só números: 012345 → 01:23:45).

## Compilar no Windows

Use Python **3.12 x64**, com Tcl/Tk, e acesso à internet. Na pasta do projeto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe build.py
```

O script baixa FFmpeg/FFprobe e Deno de suas releases oficiais, confere os hashes SHA-256 publicados, roda os testes, compila os executáveis e gera `dist/MotasDownloader-Portable.zip`. Python só é necessário no computador que compila; o usuário final extrai o ZIP e abre `MotasDownloader.exe`.

Os pacotes Python estão fixados em `requirements-lock.txt`. Os binários externos usam a release mais recente: suas versões e hashes são registrados em `.build-cache/`. Isso não garante reprodução byte a byte do pacote original. Para usar binários previamente obtidos em `bin/`, execute `build.py --skip-download`.

## Executar pelo código-fonte

```powershell
.\.venv\Scripts\python.exe build.py --prepare-only
.\.venv\Scripts\python.exe portable_main.py
```

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

Prepare `bin/ffmpeg.exe` antes dos testes. Eles usam áudio sintético, imagens geradas e um servidor HTTP local, sem contas pessoais. Verificam conversão, tags, capas, playlists, campos ausentes, acentos e prioridade das fontes.

## Publicar no GitHub

Publique o conteúdo desta pasta. Não inclua ambientes virtuais, downloads, dados de execução ou caches. O `.gitignore` cobre esses arquivos. Para distribuir executáveis, gere o pacote separadamente e mantenha as licenças das dependências.

Este arquivo de fontes não contém ferramentas instaladas ou binários de terceiros: elas são obtidas durante a compilação. Não exige tokens GitHub, Spotify nem dados pessoais do responsável pelo repositório para compilar. Limitações das plataformas podem afetar o funcionamento online.

## Licença

O projeto original permite uso e distribuição pessoais e não comerciais. Consulte `LICENSE.txt`; esta adaptação não altera suas condições. Dependências possuem licenças próprias, descritas em `THIRD-PARTY.md`.

## Validação desta entrega

Testes locais de metadados, áudio, recorte e legendas com conteúdo sintético.
As consultas e downloads online dependem das plataformas; HTTP 403 pode ocorrer.
O script de build foi adaptado e verificado sintaticamente; uma compilação
completa a partir deste ZIP em uma máquina limpa não foi repetida.
