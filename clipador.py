"""
Clipador GTA VI - Etapa 1 (MVP)
Link/arquivo de live -> picos de empolgação -> cortes verticais de 30s com legenda
-> pasta clips/pendentes (para aprovar no painel).

Uso:
  python clipador.py --url "https://..." --credito "NomeDoStreamer"
  python clipador.py --arquivo live.mp4 --credito "NomeDoStreamer" --quantidade 8
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).parent
TRABALHO = RAIZ / "work"
PENDENTES = RAIZ / "clips" / "pendentes"
DURACAO = 30          # duração de cada corte (segundos)
ANTES_PICO = 20       # segundos antes do pico dentro do corte (o pico fica perto do fim = gancho + clímax)
ESPACO_MINIMO = 60    # distância mínima entre dois cortes (segundos)


def executar(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def args_js():
    """YouTube exige um 'motor' de JavaScript para o yt-dlp. Usa Deno (padrão) ou, se só houver Node, ativa o Node."""
    if shutil.which("deno"):
        return []
    if shutil.which("node"):
        return ["--js-runtimes", "node"]
    print("AVISO: nenhum motor de JavaScript (Deno ou Node) encontrado. Links do YouTube podem falhar.\n"
          "       Instale o Deno no PowerShell:  winget install --id=DenoLand.Deno   (depois feche e abra o PowerShell)")
    return []


# --------------------------------------------------------------------------
# 1) DOWNLOAD
# --------------------------------------------------------------------------
def baixar(url, minutos_live=None):
    TRABALHO.mkdir(exist_ok=True)
    modelo = str(TRABALHO / "%(id)s.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b",   # 720p economiza disco e CPU
        "--merge-output-format", "mp4",
        "-o", modelo,
        "--print", "after_move:filepath", "--no-simulate",
        "--no-playlist",
    ] + args_js()
    if minutos_live:
        # Live em andamento: grava do início por N minutos e depois processa o que foi gravado
        cmd += ["--live-from-start", "--hls-use-mpegts"]
        antes = set(TRABALHO.glob("*"))
        proc = subprocess.Popen(cmd + [url])
        try:
            proc.wait(timeout=minutos_live * 60)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait()
        novos = [p for p in TRABALHO.glob("*") if p not in antes and p.suffix in (".part", ".mp4", ".ts", ".mkv")]
        if not novos:
            sys.exit("Não consegui gravar a live. Confira o link.")
        return max(novos, key=lambda p: p.stat().st_mtime)

    saida = subprocess.run(cmd + [url], check=True, capture_output=True, text=True).stdout.strip().splitlines()
    return Path(saida[-1])


# --------------------------------------------------------------------------
# 2) DETECÇÃO DE PICOS (áudio)
# --------------------------------------------------------------------------
def extrair_audio(video):
    wav = TRABALHO / "audio.wav"
    executar(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
              "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(wav)])
    return wav


def energia_por_segundo(wav_path):
    """RMS (volume) de cada segundo do áudio, lendo em blocos para poupar RAM."""
    valores = []
    with wave.open(str(wav_path), "rb") as w:
        taxa = w.getframerate()
        while True:
            bloco = w.readframes(taxa * 60)
            if not bloco:
                break
            x = np.frombuffer(bloco, dtype=np.int16).astype(np.float32)
            n = len(x) // taxa
            if n == 0:
                break
            x = x[: n * taxa].reshape(n, taxa)
            valores.extend(np.sqrt((x ** 2).mean(axis=1)).tolist())
    return np.array(valores, dtype=np.float32)


def z(v):
    return (v - v.mean()) / (v.std() + 1e-6)


def achar_momentos(rms, quantidade):
    """Nota = volume alto (suavizado) + subida repentina (grito, explosão, reação)."""
    suave = np.convolve(rms, np.ones(3) / 3, mode="same")
    subida = np.maximum(np.diff(suave, prepend=suave[0]), 0)
    nota = z(suave) + 0.6 * z(subida)

    ordem = np.argsort(nota)[::-1]
    escolhidos = []
    for i in ordem:
        if i < ANTES_PICO or i > len(rms) - (DURACAO - ANTES_PICO):
            continue
        if all(abs(i - j) >= ESPACO_MINIMO for j, _ in escolhidos):
            escolhidos.append((int(i), float(nota[i])))
        if len(escolhidos) >= quantidade:
            break
    return escolhidos


# --------------------------------------------------------------------------
# 3) LEGENDAS (opcional, faster-whisper)
# --------------------------------------------------------------------------
def tempo_ass(s):
    h, resto = divmod(s, 3600)
    m, seg = divmod(resto, 60)
    return f"{int(h)}:{int(m):02d}:{seg:05.2f}"


def transcrever(video, inicio, idioma, modelo):
    """Retorna lista de (inicio, fim, palavra) relativa ao início do corte."""
    wav = TRABALHO / f"trecho_{os.getpid()}.wav"
    executar(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(inicio), "-t", str(DURACAO),
              "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    segs, _ = modelo.transcribe(str(wav), language=idioma, word_timestamps=True, vad_filter=True)
    palavras = []
    for s in segs:
        for p in (s.words or []):
            palavras.append((p.start, p.end, p.word.strip()))
    return palavras


def limpar_ass(texto):
    """Remove caracteres que o formato de legenda (ASS) interpreta como comandos."""
    return str(texto).replace("{", "(").replace("}", ")").replace("\\", "").replace("\n", " ").strip()


def montar_ass(palavras, credito, caminho):
    cab = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
        "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        "Style: Legenda,Arial,84,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,6,2,2,60,60,520,1\n"
        "Style: Credito,Arial,46,&H0000E5FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,4,1,8,40,40,110,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    linhas = []
    if credito:
        linhas.append(f"Dialogue: 0,{tempo_ass(0)},{tempo_ass(DURACAO)},Credito,,0,0,0,,Via {limpar_ass(credito)}")
    # grupos de 3 palavras, em maiúsculas
    for i in range(0, len(palavras), 3):
        g = palavras[i:i + 3]
        texto = limpar_ass(" ".join(p[2] for p in g)).upper()
        fim = g[-1][1] if i + 3 >= len(palavras) else palavras[i + 3][0]
        linhas.append(f"Dialogue: 0,{tempo_ass(g[0][0])},{tempo_ass(fim)},Legenda,,0,0,0,,{texto}")
    caminho.write_text(cab + "\n".join(linhas) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# 4) RENDERIZAÇÃO
# --------------------------------------------------------------------------
def renderizar(video, inicio, pasta, tem_ass, horizontal):
    filtro = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bgb];"
        "[fg]scale=1080:-2[fgs];"
        "[bgb][fgs]overlay=(W-w)/2:(H-h)/2"
    )
    if tem_ass:
        filtro += ",ass=legenda.ass"          # roda dentro da pasta do corte (evita problema de caminho no Windows)
    filtro += "[v]"
    executar([
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", str(inicio), "-t", str(DURACAO), "-i", str(Path(video).resolve()),
        "-filter_complex", filtro, "-map", "[v]", "-map", "0:a?",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-r", "30", "-movflags", "+faststart",
        "video.mp4",
    ], cwd=pasta)

    if horizontal:   # versão 16:9 sem legenda, usada para montar o compilado
        executar([
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(inicio), "-t", str(DURACAO), "-i", str(Path(video).resolve()),
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
            "horizontal.mp4",
        ], cwd=pasta)


def gerar_corte(video, inicio, nota, nome_pasta, credito, fonte, modelo, idioma, horizontal):
    """Cria um corte completo em clips/pendentes/<nome_pasta> (vídeo vertical, legenda, meta.json)."""
    pasta = PENDENTES / nome_pasta
    pasta.mkdir(parents=True, exist_ok=True)

    palavras = []
    if modelo:
        try:
            palavras = transcrever(video, inicio, idioma, modelo)
        except Exception as e:
            print(f"      transcrição falhou: {e}")
    tem_ass = bool(palavras) or bool(credito)
    if tem_ass:
        montar_ass(palavras, credito, pasta / "legenda.ass")

    renderizar(video, inicio, pasta, tem_ass, horizontal)

    titulo = " ".join(p[2] for p in palavras[:8]).strip()
    if not titulo:   # sem transcrição: título-modelo (edite no painel antes de aprovar)
        titulo = f"{credito} no lançamento do GTA 6 🔥" if credito else "Momento insano no GTA 6 🔥"
    meta = {
        "titulo": titulo,
        "credito": credito,
        "fonte": fonte,
        "inicio_seg": inicio,
        "duracao": DURACAO,
        "nota": round(float(nota), 2),
        "hashtags": "#GTA6 #GTAVI #shorts",
    }
    (pasta / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return pasta


# --------------------------------------------------------------------------
# PRINCIPAL
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--url", help="link da live (YouTube, Twitch ou Kick)")
    g.add_argument("--arquivo", help="vídeo já baixado")
    ap.add_argument("--credito", default="", help="nome do streamer (aparece no vídeo e na descrição)")
    ap.add_argument("--quantidade", type=int, default=10, help="quantos cortes gerar")
    ap.add_argument("--minutos-live", type=int, help="se a live estiver ao vivo: grava N minutos e processa")
    ap.add_argument("--idioma", default=None, help="idioma da fala (pt, en...). Vazio = detectar")
    ap.add_argument("--sem-legenda", action="store_true", help="pula a transcrição (bem mais rápido)")
    ap.add_argument("--sem-horizontal", action="store_true", help="não gera versão 16:9 para o compilado")
    a = ap.parse_args()

    TRABALHO.mkdir(exist_ok=True)
    PENDENTES.mkdir(parents=True, exist_ok=True)

    video = Path(a.arquivo) if a.arquivo else baixar(a.url, a.minutos_live)
    print(f"[1/4] Vídeo: {video}")

    print("[2/4] Analisando o áudio para achar os momentos mais intensos...")
    rms = energia_por_segundo(extrair_audio(video))
    momentos = achar_momentos(rms, a.quantidade)
    if not momentos:
        sys.exit("Nenhum momento encontrado (vídeo muito curto?).")
    print(f"      {len(momentos)} momentos encontrados.")

    modelo = None
    if not a.sem_legenda:
        try:
            from faster_whisper import WhisperModel
            print("[3/4] Carregando modelo de transcrição (a 1ª vez baixa ~150 MB)...")
            modelo = WhisperModel("base", device="cpu", compute_type="int8")
        except Exception as e:
            print(f"      Sem legenda ({e}). Seguindo sem transcrição.")

    print("[4/4] Renderizando os cortes...")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for n, (seg_pico, nota) in enumerate(sorted(momentos, key=lambda m: m[0]), 1):
        inicio = max(0, seg_pico - ANTES_PICO)
        gerar_corte(video, inicio, nota, f"{stamp}_{n:02d}", a.credito, a.url or str(a.arquivo),
                    modelo, a.idioma, not a.sem_horizontal)
        print(f"      corte {n}/{len(momentos)} pronto")

    print("\nPronto! Abra o painel para aprovar:  streamlit run painel.py")


if __name__ == "__main__":
    main()
