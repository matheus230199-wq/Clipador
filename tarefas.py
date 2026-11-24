"""Gerenciador de tarefas em segundo plano: o painel liga/desliga os programas por botões, sem digitar comandos."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

import sinal_parar

RAIZ = Path(__file__).parent
LOGS = RAIZ / "logs"
ARQ = RAIZ / "tarefas.json"
HISTORICO = 40


def _ler():
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except Exception:
        return []


def _salvar(lista):
    ARQ.write_text(json.dumps(lista[-HISTORICO:], ensure_ascii=False, indent=1), encoding="utf-8")


def _viva(t):
    try:
        p = psutil.Process(t["pid"])
        return (p.is_running() and p.status() != psutil.STATUS_ZOMBIE
                and abs(p.create_time() - t["criado_proc"]) < 2)
    except Exception:
        return False


def env_utf8():
    """Evita erro de acentos/emojis quando a saída vai para um arquivo de log no Windows."""
    return dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def iniciar(tipo, titulo, args):
    """Roda 'python <args>' em segundo plano. Retorna o dicionário da tarefa."""
    LOGS.mkdir(exist_ok=True)
    tid = f"{time.strftime('%Y%m%d_%H%M%S')}_{tipo}"
    log = LOGS / f"{tid}.log"
    f = open(log, "w", encoding="utf-8")
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP     # permite parar com Ctrl+Break
    else:
        kw["start_new_session"] = True
    p = subprocess.Popen([sys.executable, "-u", *args], stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         cwd=str(RAIZ), env=env_utf8(), **kw)
    t = {"id": tid, "tipo": tipo, "titulo": titulo, "pid": p.pid, "criado_proc": psutil.Process(p.pid).create_time(),
         "inicio": time.time(), "log": str(log), "parando": False}
    lista = _ler()
    lista.append(t)
    _salvar(lista)
    return t


def listar(tipos=None):
    """Tarefas mais recentes primeiro, cada uma com 'ativa' (True/False)."""
    out = []
    for t in reversed(_ler()):
        if tipos and t["tipo"] not in tipos:
            continue
        out.append(dict(t, ativa=_viva(t)))
    return out


def ativa(tipo):
    for t in listar([tipo]):
        if t["ativa"]:
            return t
    return None


def ler_log(t, linhas=14):
    try:
        txt = Path(t["log"]).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    # barras de progresso usam \r: mantém só a última versão de cada linha
    partes = [l.split("\r")[-1] for l in txt.splitlines()]
    return "\n".join(partes[-linhas:])


def parar(tid):
    """Pede para a tarefa terminar com calma (ela finaliza o que estiver renderizando).
    Usa dois meios ao mesmo tempo: um arquivo de pedido (confiável em qualquer sistema) e o sinal do Windows/Linux."""
    lista = _ler()
    for t in lista:
        if t["id"] == tid and _viva(t):
            sinal_parar.pedir(t["pid"])
            try:
                if os.name == "nt":
                    os.kill(t["pid"], signal.CTRL_BREAK_EVENT)
                else:
                    os.kill(t["pid"], signal.SIGINT)
            except Exception:
                pass
            t["parando"] = True
    _salvar(lista)


def forcar(tid):
    """Encerra na hora (e tudo o que ela abriu, como o ffmpeg)."""
    for t in _ler():
        if t["id"] == tid and _viva(t):
            try:
                p = psutil.Process(t["pid"])
                for filho in p.children(recursive=True):
                    filho.kill()
                p.kill()
            except Exception:
                pass


def limpar_logs(dias=7):
    """Apaga logs de tarefas com mais de N dias."""
    limite = time.time() - dias * 86400
    for f in LOGS.glob("*.log") if LOGS.exists() else []:
        try:
            if f.stat().st_mtime < limite:
                f.unlink()
        except OSError:
            pass
