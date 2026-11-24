"""Pedido de parada por arquivo: funciona em qualquer sistema, sem depender de sinais do Windows."""
import os
import time
from pathlib import Path

PASTA = Path(__file__).parent / "parar"


def _arquivo(pid):
    return PASTA / f"{pid}.flag"


def pedir(pid):
    """Pede para o processo <pid> terminar com calma."""
    PASTA.mkdir(exist_ok=True)
    _arquivo(pid).write_text(str(time.time()))


def pedido():
    """O processo atual foi mandado parar?"""
    return _arquivo(os.getpid()).exists()


def limpar():
    """Remove o pedido do processo atual (chamar ao iniciar e ao terminar)."""
    try:
        _arquivo(os.getpid()).unlink()
    except OSError:
        pass


def limpar_antigos(horas=24):
    """Apaga pedidos esquecidos de processos que já não existem."""
    if not PASTA.exists():
        return
    limite = time.time() - horas * 3600
    for f in PASTA.glob("*.flag"):
        try:
            if f.stat().st_mtime < limite:
                f.unlink()
        except OSError:
            pass


def dormir(segundos):
    """Dorme em passos de 1 s e interrompe (como Ctrl+C) assim que houver pedido de parada."""
    fim = time.time() + segundos
    while True:
        if pedido():
            raise KeyboardInterrupt
        restante = fim - time.time()
        if restante <= 0:
            return
        time.sleep(min(1.0, restante))
