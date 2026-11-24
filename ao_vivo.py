"""
Clipador AO VIVO: grava a live enquanto ela acontece, vigia o áudio e vai gerando
cortes de 30s em clips/pendentes ASSIM QUE aparece um momento forte (atraso de ~1-2 min).

Uso:
  python ao_vivo.py --url "https://..." --credito "NomeDoStreamer"
  Ctrl+C para parar (ele termina de renderizar o que estiver na fila).

Ajuste fino:
  --limiar 4.0    nota mínima para virar corte (menor = mais cortes, maior = só os mais fortes)
  --max-por-hora 12
Aviso: grava a live em work\\live_*.ts (~2 GB por hora em 720p). Apague depois de usar.
"""
import argparse
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

import clipador as c
import sinal_parar

MARGEM = 20        # só analisa até (gravado - MARGEM) para o corte ter o "depois" do pico
ESPACO = 60        # segundos mínimos entre dois cortes


def pegar_urls(url, exigir=True):
    """Pede ao yt-dlp o endereço direto do stream (YouTube, Twitch e Kick).
    Tenta vários seletores de formato, porque cada plataforma/live oferece formatos diferentes."""
    seletores = [
        "bv*[height<=720]+ba/b[height<=720]",   # vídeo (até 720p) + áudio, juntos ou separados
        "bv*+ba/b",                              # qualquer qualidade
        "best",
        None,                                    # deixa o yt-dlp escolher sozinho
    ]
    ultimo_erro = ""
    for sel in seletores:
        cmd = [sys.executable, "-m", "yt_dlp", "-g", "--no-playlist"] + c.args_js()
        if sel:
            cmd += ["-f", sel]
        r = subprocess.run(cmd + [url], capture_output=True, text=True)
        urls = [l.strip() for l in r.stdout.splitlines() if l.strip().startswith("http")]
        if urls:
            return urls[:2]
        ultimo_erro = r.stderr[-600:]

    # Nada funcionou: mostra ao usuário o que o yt-dlp enxerga nesse link
    lista = subprocess.run([sys.executable, "-m", "yt_dlp", "-F", "--no-playlist"] + c.args_js() + [url],
                           capture_output=True, text=True)
    dica = ""
    if "JavaScript runtime" in ultimo_erro:
        dica = ("\nSOLUÇÃO: instale o Deno (winget install --id=DenoLand.Deno), feche e abra o PowerShell e rode "
                "pip install -U \"yt-dlp[default]\"")
    mensagem = ("Não consegui obter o stream desse link.\n\nErro do yt-dlp:\n" + ultimo_erro +
             "\n\nFormatos que o yt-dlp enxerga (copie isto se precisar de ajuda):\n" +
             (lista.stdout[-1500:] or lista.stderr[-800:]) + dica +
             "\n\nConfira: a live está AO VIVO agora (não é estreia agendada nem live já encerrada)? "
             "Abre no navegador sem login? Se a live já acabou, use o clipador.py --url.")
    if exigir:
        sys.exit(mensagem)
    print(mensagem[:900])
    return None


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")


class Gravador:
    """Grava a live em um único .ts (formato que pode ser lido enquanto ainda é gravado).

    Métodos: 'ffmpeg' (endereço direto), 'ffmpeg+cabecalhos' (imitando um navegador) e 'ytdlp' (o próprio yt-dlp baixa).
    O tempo gravado vem do progresso do ffmpeg; se ele não informar, estimamos pelo relógio enquanto o arquivo cresce."""

    def __init__(self, destino, urls=None, fonte_teste=None, sem_progresso=False, metodo="ffmpeg", pagina=""):
        self.destino = Path(destino)
        self.metodo = metodo
        self._prog = 0.0
        self._fim_progresso = False
        self._inicio_dados = None
        self._tam, self._t_tam = 0, time.time()
        self.arq_erro = self.destino.with_suffix(".err.txt")
        self._f_erro = open(self.arq_erro, "w", encoding="utf-8", errors="replace")
        usa_progresso = metodo != "ytdlp" and not sem_progresso
        if metodo == "ytdlp":
            cmd = [sys.executable, "-u", "-m", "yt_dlp", "-q", "--no-warnings", "--no-playlist", "--no-part",
                   "--force-overwrites", "--hls-use-mpegts", "-f", "best[height<=720]/b[height<=720]/best"]
            cmd += c.args_js() + ["-o", str(destino), pagina]
        else:
            cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "warning"]
            if usa_progresso:
                cmd += ["-progress", "pipe:1", "-nostats"]
            if fonte_teste:                         # simula uma live a partir de um arquivo
                cmd += ["-re", "-i", str(fonte_teste), "-map", "0"]
            else:
                cab = []
                if metodo == "ffmpeg+cabecalhos":
                    origem = "https://" + (urlparse(pagina).netloc or "www.twitch.tv")
                    cab = ["-user_agent", UA, "-headers", f"Referer: {origem}/\r\nOrigin: {origem}\r\n"]
                # (sem -reconnect: em streams HLS ele faz o ffmpeg reconectar em loop no fim de cada trecho)
                cmd += cab + ["-i", urls[0]]
                if len(urls) > 1:
                    cmd += cab + ["-i", urls[1], "-map", "0:v:0", "-map", "1:a:0"]
            cmd += ["-c", "copy", "-f", "mpegts", str(destino)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stderr=self._f_erro,
                                     stdout=subprocess.PIPE if usa_progresso else subprocess.DEVNULL,
                                     text=True, encoding="utf-8", errors="replace")
        if usa_progresso:
            threading.Thread(target=self._ler_progresso, daemon=True).start()

    def _ler_progresso(self):
        try:
            for linha in self.proc.stdout:
                if linha.startswith(("out_time_us=", "out_time_ms=")):
                    try:
                        self._prog = max(self._prog, int(linha.split("=")[1]) / 1_000_000)
                    except ValueError:
                        pass
        except Exception:
            pass
        self._fim_progresso = True

    def _tamanho(self):
        try:
            return self.destino.stat().st_size
        except OSError:
            return 0

    @property
    def terminou(self):
        return self.proc.poll() is not None

    @property
    def gravado(self):
        if self._prog > 0:
            return self._prog
        if self._tamanho() > 0:                 # sem progresso do ffmpeg: estima pelo relógio desde o 1º dado
            if self._inicio_dados is None:
                self._inicio_dados = time.time()
            return time.time() - self._inicio_dados
        return 0.0

    def mb(self):
        return self._tamanho() / 1_048_576

    def aguardar_dados(self, limite=45, minimo=200_000):
        """Espera o arquivo começar a crescer de verdade. False se o método falhou."""
        fim = time.time() + limite
        while time.time() < fim:
            if self._tamanho() >= minimo:
                return True
            if self.proc.poll() is not None:
                return self._tamanho() >= minimo
            time.sleep(1)
        return self._tamanho() >= minimo

    def mensagens_erro(self, linhas=6):
        try:
            self._f_erro.flush()
            txt = self.arq_erro.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        except OSError:
            return ""
        return "\n".join("      " + l[:200] for l in txt[-linhas:])

    def estagnado(self, segundos):
        """True se o arquivo não cresce há 'segundos' (stream caiu ou travou)."""
        tam, agora = self._tamanho(), time.time()
        if tam > self._tam:
            self._tam, self._t_tam = tam, agora
            return False
        return agora - self._t_tam >= segundos

    def parar(self):
        if self.proc.poll() is None:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        try:
            self._f_erro.close()
        except OSError:
            pass


def iniciar_gravacao(a, video, tentativas=None):
    """Tenta cada método de captura até um deles começar a gravar de verdade (e diz qual funcionou)."""
    if a.fonte_teste and tentativas is None:
        return Gravador(video, fonte_teste=a.fonte_teste, sem_progresso=a.teste_sem_progresso)
    if tentativas is None:
        cache = {}

        def urls():
            if "u" not in cache:
                cache["u"] = pegar_urls(a.url, exigir=False)
            return cache["u"]

        def ffmpeg(metodo):
            def criar():
                u = urls()
                if not u:
                    raise RuntimeError("não consegui obter o endereço direto do stream")
                return Gravador(video, u, metodo=metodo, pagina=a.url)
            return criar

        todos = {"ytdlp": ("yt-dlp (baixa a live direto)", lambda: Gravador(video, metodo="ytdlp", pagina=a.url)),
                 "ffmpeg": ("ffmpeg direto", ffmpeg("ffmpeg")),
                 "ffmpeg+cabecalhos": ("ffmpeg imitando um navegador", ffmpeg("ffmpeg+cabecalhos"))}
        ordem = {"auto": ["ytdlp", "ffmpeg", "ffmpeg+cabecalhos"], "ytdlp": ["ytdlp"],
                 "ffmpeg": ["ffmpeg", "ffmpeg+cabecalhos"]}[a.metodo]
        tentativas = [todos[k] for k in ordem]
    for nome, criar in tentativas:
        print(f"Tentando gravar com o método: {nome} ...", flush=True)
        try:
            rec = criar()
        except Exception as e:
            print(f"✘ {nome} indisponível: {e}", flush=True)
            continue
        if rec.aguardar_dados(45):
            print(f"✔ Gravando com: {nome}", flush=True)
            return rec
        erros = rec.mensagens_erro()
        print(f"✘ {nome} não conseguiu gravar." + (f" Mensagens do programa:\n{erros}" if erros else " (sem mensagens)"), flush=True)
        rec.parar()
        try:
            video.unlink()
        except OSError:
            pass
    sys.exit("ERRO: nenhum método conseguiu gravar essa live. Veja as mensagens acima (e me envie, se precisar).")


def notas(rms):
    """Nota de cada segundo: volume (vs. o normal DESTA live) + subida repentina."""
    suave = np.convolve(rms, np.ones(3) / 3, mode="same")
    med = np.median(suave)
    desv = max(1.4826 * np.median(np.abs(suave - med)), 0.05 * med, 1e-3)
    subida = np.maximum(np.diff(suave, prepend=suave[0]), 0)
    zd = (subida - subida.mean()) / (subida.std() + 1e-6)
    return (suave - med) / desv + 0.6 * zd


def _torre(acao, a, nome, valor=None):
    """Avisa a Torre de Controle (banco de dados) sobre o andamento. Falhas aqui nunca param a gravação."""
    if not getattr(a, "torre_canal", None):
        return
    try:
        import torre_db as db
        if acao == "novo":
            db.add_momento(a.torre_plataforma or "", a.torre_canal, "áudio", valor, nome, "renderizando")
        elif acao == "status":
            db.set_status_momento(nome, valor)
    except Exception as e:
        print(f"(aviso) Torre indisponível: {e}")


def trabalhador(fila, video, a, modelo):
    while True:
        item = fila.get()
        if item is None:
            return
        inicio, nota, nome = item
        try:
            c.gerar_corte(video, inicio, nota, nome, a.credito, a.url or "teste",
                          modelo, a.idioma, not a.sem_horizontal)
            print(f"   ✔ corte pronto: {nome} (nota {nota:.1f}) -> abra o painel para aprovar")
            _torre("status", a, nome, "pendente")
        except Exception as e:
            print(f"   ✘ falha ao renderizar {nome}: {e}")
            _torre("status", a, nome, "erro")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--fonte-teste", help="(teste) simula uma live a partir de um arquivo de vídeo")
    ap.add_argument("--credito", default="")
    ap.add_argument("--limiar", type=float, default=4.0)
    ap.add_argument("--intervalo", type=int, default=30, help="de quantos em quantos segundos analisar")
    ap.add_argument("--aquecimento", type=int, default=180, help="segundos de live antes de começar a cortar")
    ap.add_argument("--max-por-hora", type=int, default=12)
    ap.add_argument("--com-legenda", action="store_true", help="transcreve cada corte (pesado no seu PC)")
    ap.add_argument("--idioma", default=None)
    ap.add_argument("--sem-horizontal", action="store_true")
    ap.add_argument("--garantir", type=int, default=10,
                    help="minutos: se nenhum corte sair nesse tempo, corta o melhor momento mesmo abaixo do limiar (0 = desliga)")
    ap.add_argument("--metodo", choices=["auto", "ytdlp", "ffmpeg"], default="auto",
                    help="como gravar: auto (tenta todos), ytdlp ou ffmpeg")
    ap.add_argument("--so-testar", action="store_true", help="só testa se a gravação funciona (uns 60 s) e sai")
    ap.add_argument("--teste-sem-progresso", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--manter-gravacao", action="store_true", help="não apaga o arquivo gravado no final")
    ap.add_argument("--torre-plataforma", default="", help="(uso interno da Torre)")
    ap.add_argument("--torre-canal", default="", help="(uso interno da Torre)")
    a = ap.parse_args()
    import signal
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    if not (a.url or a.fonte_teste):
        sys.exit("Informe --url (ou --fonte-teste para testar).")
    sinal_parar.limpar()

    c.TRABALHO.mkdir(exist_ok=True)
    c.PENDENTES.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    tag = re.sub(r"[^A-Za-z0-9]", "", a.torre_canal or "")[:20]
    video = c.TRABALHO / f"live_{stamp}_{os.getpid()}.ts"

    modelo = None
    if a.com_legenda:
        try:
            from faster_whisper import WhisperModel
            modelo = WhisperModel("base", device="cpu", compute_type="int8")
        except Exception as e:
            print(f"Sem legenda ({e}).")

    print(f"Gravando a live em {video.name}. Primeiros {a.aquecimento}s só para aprender o 'volume normal'.", flush=True)
    print("Pressione Ctrl+C para parar.\n", flush=True)
    try:
        rec = iniciar_gravacao(a, video)
    except KeyboardInterrupt:
        sinal_parar.limpar()
        return
    if a.so_testar:
        print("\nTESTE OK: a gravação desta live funciona. Encerrando o teste.", flush=True)
        rec.parar()
        for f in (video, rec.arq_erro):
            try:
                f.unlink()
            except OSError:
                pass
        sinal_parar.limpar()
        return

    fila = queue.Queue()
    worker = threading.Thread(target=trabalhador, args=(fila, video, a, modelo))
    worker.start()

    rms_hist = np.zeros(0, dtype=np.float32)
    analisados_ate = 0
    escolhidos = []          # segundos dos picos já usados
    n = 0
    ultimo_corte_rec = a.aquecimento      # segundo da gravação do último corte (para o "corte garantido")
    ultimo_sinal_id = 0
    erro_final = False
    if a.torre_canal:
        try:
            import torre_db as tdb
            r = tdb.consultar("SELECT COALESCE(MAX(id), 0) AS m FROM momentos")
            ultimo_sinal_id = r[0]["m"] if r else 0     # ignora sinais antigos
        except Exception:
            tdb = None
    else:
        tdb = None

    def agora_rec():
        return f"[{int(rec.gravado) // 60:02d}:{int(rec.gravado) % 60:02d}]"

    def criar_corte(i, v, origem):
        nonlocal n, ultimo_corte_rec
        escolhidos.append(i)
        ultimo_corte_rec = max(ultimo_corte_rec, i)
        n += 1
        nome = f"live{stamp}{tag}_{n:03d}"
        print(f"{agora_rec()} {origem} em {i // 60:02d}:{i % 60:02d} (nota {v:.1f}) -> renderizando")
        fila.put((max(0, i - c.ANTES_PICO), v, nome))
        return nome

    try:
        while True:
            sinal_parar.dormir(a.intervalo)
            final = rec.terminou
            if not final and rec.estagnado(120):
                print("\nERRO: a gravação parou de crescer há 2 minutos (a live caiu ou o stream travou). Encerrando.")
                erro_final = True
                break
            hi = int(rec.gravado - (0 if final else MARGEM))

            # --- cortes disparados pela explosão do chat (sinais registrados pela Torre)
            if tdb is not None:
                try:
                    novos = tdb.consultar(
                        "SELECT id, ts, nota FROM momentos WHERE plataforma=? AND lower(canal)=? AND origem='chat' "
                        "AND pasta IS NULL AND id>? ORDER BY id", (a.torre_plataforma, a.torre_canal.lower(), ultimo_sinal_id))
                except Exception:
                    novos = []
                for sig in novos:
                    ultimo_sinal_id = max(ultimo_sinal_id, sig["id"])
                    i = int(rec.gravado - (time.time() - sig["ts"]) - 8)     # o chat reage uns segundos depois do lance
                    recentes = [t for t in escolhidos if t > i - 3600]
                    if (i >= c.ANTES_PICO and len(recentes) < a.max_por_hora
                            and all(abs(i - t) >= ESPACO for t in escolhidos)):
                        nome = criar_corte(i, sig["nota"], "💬 chat explodiu")
                        try:
                            tdb.set_pasta_momento(sig["id"], nome)
                        except Exception:
                            pass

            if hi - analisados_ate >= 10:
                a0 = max(0, analisados_ate - 3)
                wav = c.TRABALHO / f"ao_vivo_{os.getpid()}.wav"
                try:
                    c.executar(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(a0), "-t", str(hi - a0),
                                "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
                    novo = c.energia_por_segundo(wav)
                except Exception as e:
                    print(f"(aviso) falha lendo o áudio: {e}")
                    novo = np.zeros(0, dtype=np.float32)
                if len(novo):
                    fim_idx = a0 + len(novo)
                    if fim_idx > len(rms_hist):
                        rms_hist = np.concatenate([rms_hist, np.zeros(fim_idx - len(rms_hist), dtype=np.float32)])
                    rms_hist[a0:fim_idx] = novo

                    if len(rms_hist) >= a.aquecimento:
                        nota = notas(rms_hist)
                        lo = max(analisados_ate, c.ANTES_PICO)
                        regiao = [(i, nota[i]) for i in range(lo, min(hi, len(nota)))]
                        regiao.sort(key=lambda x: -x[1])
                        melhor = regiao[0][1] if regiao else 0
                        achou = 0
                        for i, v in regiao:
                            if v < a.limiar:
                                break
                            recentes = [t for t in escolhidos if t > i - 3600]
                            if len(recentes) >= a.max_por_hora:
                                break
                            if all(abs(i - t) >= ESPACO for t in escolhidos):
                                nome = criar_corte(i, v, "🔥 momento forte")
                                _torre("novo", a, nome, v)
                                achou += 1
                        # corte garantido: nada saiu por muito tempo -> pega o melhor momento da janela, mesmo abaixo do limiar
                        if (not achou and a.garantir > 0 and hi - ultimo_corte_rec >= a.garantir * 60):
                            de = max(c.ANTES_PICO, ultimo_corte_rec + 5)
                            cand = sorted(((i, nota[i]) for i in range(de, min(hi, len(nota)))), key=lambda x: -x[1])
                            for i, v in cand:
                                if v < 0.5:
                                    break
                                if all(abs(i - t) >= ESPACO for t in escolhidos):
                                    nome = criar_corte(i, v, "⭐ corte garantido (melhor momento da janela)")
                                    _torre("novo", a, nome, v)
                                    achou += 1
                                    break
                        if not achou:
                            if melhor >= a.limiar:
                                print(f"{agora_rec()} momento forte ignorado (perto de outro corte ou limite por hora atingido)")
                            else:
                                print(f"{agora_rec()} sem momento forte (maior nota {melhor:.1f}, limiar {a.limiar}) "
                                      f"| gravação: {rec.mb():.0f} MB")
                    else:
                        print(f"{agora_rec()} aprendendo o volume normal da live... | gravação: {rec.mb():.0f} MB")
                analisados_ate = hi
            else:
                print(f"{agora_rec()} gravando... {rec.mb():.0f} MB")
            if final:
                if rec.gravado < 5 and rec.proc.returncode not in (0, None):
                    print("\nERRO: não consegui gravar a live (o endereço do stream pode ter expirado ou a live acabou).")
                else:
                    print("\nA live terminou.")
                break
    except KeyboardInterrupt:
        print("\nParando a gravação...")
    finally:
        rec.parar()
        fila.put(None)
    print("Terminando de renderizar os cortes que estão na fila (aguarde)...")
    worker.join()
    if a.torre_canal and not a.manter_gravacao:        # gravada pela Torre: libera o disco (o SSD é pequeno)
        try:
            video.unlink()
        except OSError:
            pass
    sinal_parar.limpar()
    try:
        rec.arq_erro.unlink()
    except OSError:
        pass
    print(f"\nPronto. {n} corte(s) gerado(s). Abra o painel:  streamlit run painel.py")
    if erro_final:
        sys.exit(3)


if __name__ == "__main__":
    main()
