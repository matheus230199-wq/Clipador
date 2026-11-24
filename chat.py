"""
LEITURA DE CHAT - Twitch, Kick e YouTube, num único monitor.

Cada plataforma tem o seu leitor (só leitura, sem login):
  - Twitch : IRC por WebSocket (conexão anônima)
  - Kick   : Pusher WebSocket do chat público (precisa descobrir o 'chatroom' do canal)
  - YouTube: chat ao vivo do vídeo, consultado a cada poucos segundos (sem gastar a cota da API)

O monitor conta as mensagens, calcula mensagens/min, compara com o "normal" de cada canal e avisa quando o chat explode.
Também guarda o total por minuto (para a próxima etapa: usar o chat na nota dos cortes).

Teste rápido de cada plataforma, sem ligar o sistema todo:
  python chat.py --testar twitch:gaules kick:xqc "youtube:https://www.youtube.com/watch?v=ID_DA_LIVE" --segundos 40
"""
import argparse
import asyncio
import json
import random
import re
import statistics
import threading
import time
from collections import deque
from urllib.parse import parse_qs, urlparse

import requests

TWITCH_URL = "wss://irc-ws.chat.twitch.tv:443"
KICK_URL = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false"
YOUTUBE_BASE = "https://www.youtube.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")


# ----------------------------------------------------------------------------- utilidades
def resolver_chatroom_kick(slug):
    """Descobre o ID da sala de chat de um canal da Kick. A Kick protege essa consulta;
    com 'pip install curl_cffi' a chance de funcionar é bem maior."""
    url = f"https://kick.com/api/v2/channels/{slug}"
    cab = {"User-Agent": UA, "Accept": "application/json"}
    try:
        from curl_cffi import requests as cr
        r = cr.get(url, impersonate="chrome", timeout=20, headers=cab)
    except ImportError:
        r = requests.get(url, headers=cab, timeout=20)
    r.raise_for_status()
    return str(r.json()["chatroom"]["id"])


def id_video_youtube(url):
    """Extrai o ID do vídeo de links watch?v=, youtu.be/ e /live/ID."""
    u = urlparse(url or "")
    if "v" in parse_qs(u.query):
        return parse_qs(u.query)["v"][0]
    partes = [p for p in u.path.split("/") if p]
    if u.netloc.endswith("youtu.be") and partes:
        return partes[0]
    if len(partes) >= 2 and partes[0] in ("live", "shorts", "embed"):
        return partes[1]
    return None


def contar_mensagens_youtube(resposta):
    """Conta as mensagens novas numa resposta do chat do YouTube e devolve (qtd, proxima_continuacao, espera_seg)."""
    cc = (resposta.get("continuationContents") or {}).get("liveChatContinuation") or {}
    qtd = 0
    for acao in cc.get("actions", []):
        item = ((acao.get("addChatItemAction") or {}).get("item")) or {}
        if any(k in item for k in ("liveChatTextMessageRenderer", "liveChatPaidMessageRenderer",
                                   "liveChatMembershipItemRenderer", "liveChatPaidStickerRenderer")):
            qtd += 1
    cont, espera = None, 3.0
    for c in cc.get("continuations", []):
        for chave in ("invalidationContinuationData", "timedContinuationData", "reloadContinuationData"):
            if chave in c:
                cont = c[chave].get("continuation")
                espera = (c[chave].get("timeoutMs") or 3000) / 1000
    return qtd, cont, max(1.0, min(espera, 10.0))


# ----------------------------------------------------------------------------- monitor
class MonitorChat:
    def __init__(self, ao_pico, plataformas=("twitch", "kick", "youtube"), bucket=5.0, min_hist=24,
                 multiplicador=3.0, min_por_min=30, ao_minuto=None, twitch_url=TWITCH_URL, kick_url=KICK_URL,
                 resolver_kick=resolver_chatroom_kick, yt_base=YOUTUBE_BASE):
        self.ao_pico, self.ao_minuto = ao_pico, ao_minuto
        self.plataformas = set(plataformas)
        self.bucket, self.min_hist, self.mult, self.min_por_min = bucket, min_hist, multiplicador, min_por_min
        self.twitch_url, self.kick_url, self.resolver_kick, self.yt_base = twitch_url, kick_url, resolver_kick, yt_base
        self.lock = threading.Lock()
        self.ativos = {}                       # (plataforma, canal) -> info do canal ao vivo
        self.contagem, self.minuto, self.total = {}, {}, {}
        self.hist, self.taxas = {}, {}
        self.status = {p: "aguardando" for p in self.plataformas}
        self.ok = set()                        # chaves cujo chat está realmente chegando
        self.salas_kick, self.tentativa_kick = {}, {}
        self._yt = {}                          # chave -> (thread, evento_parar)
        threading.Thread(target=self._fechador, daemon=True).start()
        if "twitch" in self.plataformas:
            threading.Thread(target=lambda: asyncio.run(self._twitch()), daemon=True).start()
        if "kick" in self.plataformas:
            threading.Thread(target=lambda: asyncio.run(self._kick()), daemon=True).start()

    # --- interface
    def definir(self, ativos):
        """ativos: {(plataforma, canal): info} apenas dos canais AO VIVO."""
        self.ativos = {k: v for k, v in ativos.items() if k[0] in self.plataformas}
        self._gerir_youtube()

    def taxa(self, plataforma, canal):
        chave = (plataforma, canal.lower())
        return self.taxas.get(chave) if chave in self.ok else None

    def resumo(self):
        return dict(self.status)

    def _contar(self, chave, n=1):
        with self.lock:
            self.contagem[chave] = self.contagem.get(chave, 0) + n
            self.total[chave] = self.total.get(chave, 0) + n
        self.ok.add(chave)

    # --- cálculo de taxa e picos
    def _fechador(self):
        escala = 60.0 / self.bucket
        inicio_min = time.time()
        while True:
            time.sleep(self.bucket)
            with self.lock:
                cont, self.contagem = self.contagem, {}
            for chave in list(self.ativos):
                n = cont.get(chave, 0)
                self.minuto[chave] = self.minuto.get(chave, 0) + n
                h = self.hist.setdefault(chave, deque(maxlen=400))
                h.append(n)
                if len(h) >= self.min_hist and chave in self.ok:
                    lista = list(h)
                    recente = sum(lista[-4:]) / 4 * escala
                    base = statistics.median(lista[:-4][-130:]) * escala
                    self.taxas[chave] = round(recente, 1)
                    if recente >= max(self.min_por_min, self.mult * max(base, 1.0)):
                        try:
                            self.ao_pico(chave[0], chave[1], recente, base)
                        except Exception:
                            pass
            for chave in list(self.hist):
                if chave not in self.ativos:
                    self.hist.pop(chave, None)
                    self.taxas.pop(chave, None)
                    self.minuto.pop(chave, None)
            if time.time() - inicio_min >= 60:
                if self.ao_minuto:
                    for chave, n in list(self.minuto.items()):
                        try:
                            self.ao_minuto(chave[0], chave[1], time.time(), n)
                        except Exception:
                            pass
                self.minuto = {k: 0 for k in self.minuto}
                inicio_min = time.time()

    # --- Twitch (IRC)
    async def _twitch(self):
        import websockets
        while True:
            try:
                async with websockets.connect(self.twitch_url) as ws:
                    await ws.send("PASS SCHMOOPIIE")
                    await ws.send(f"NICK justinfan{random.randint(10000, 99999)}")
                    self.status["twitch"] = "conectado"
                    entrou = set()
                    while True:
                        desejados = {c for (p, c) in self.ativos if p == "twitch"}
                        for ch in desejados - entrou:
                            await ws.send(f"JOIN #{ch}")
                            entrou.add(ch)
                        for ch in entrou - desejados:
                            await ws.send(f"PART #{ch}")
                            entrou.discard(ch)
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=0.2)
                        except asyncio.TimeoutError:
                            continue
                        for linha in msg.split("\r\n"):
                            if linha.startswith("PING"):
                                await ws.send("PONG :tmi.twitch.tv")
                            elif "PRIVMSG #" in linha:
                                canal = linha.split("PRIVMSG #", 1)[1].split(" ", 1)[0].lower()
                                self._contar(("twitch", canal))
            except Exception as e:
                self.status["twitch"] = f"reconectando ({type(e).__name__})"
                await asyncio.sleep(5)

    # --- Kick (Pusher)
    async def _kick(self):
        import websockets
        while True:
            try:
                async with websockets.connect(self.kick_url) as ws:
                    self.status["kick"] = "conectado"
                    inscritos = {}                      # id da sala -> slug
                    while True:
                        desejados = {c for (p, c) in self.ativos if p == "kick"}
                        agora = time.time()
                        for slug in desejados:
                            sala = self.salas_kick.get(slug)
                            if sala is None and agora - self.tentativa_kick.get(slug, 0) > 300:
                                self.tentativa_kick[slug] = agora
                                try:
                                    sala = await asyncio.to_thread(self.resolver_kick, slug)
                                    self.salas_kick[slug] = sala
                                except Exception as e:
                                    self.status["kick"] = f"sem acesso à sala de {slug} ({type(e).__name__}) - tente: pip install curl_cffi"
                            if sala and sala not in inscritos:
                                await ws.send(json.dumps({"event": "pusher:subscribe",
                                                          "data": {"auth": "", "channel": f"chatrooms.{sala}.v2"}}))
                                inscritos[sala] = slug
                        for sala, slug in list(inscritos.items()):
                            if slug not in desejados:
                                await ws.send(json.dumps({"event": "pusher:unsubscribe",
                                                          "data": {"channel": f"chatrooms.{sala}.v2"}}))
                                del inscritos[sala]
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        except asyncio.TimeoutError:
                            continue
                        try:
                            d = json.loads(msg)
                        except ValueError:
                            continue
                        ev = d.get("event", "")
                        if ev == "pusher:ping":
                            await ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                        elif ev.endswith("ChatMessageEvent"):
                            m = re.search(r"chatrooms\.(\d+)", d.get("channel", ""))
                            slug = inscritos.get(m.group(1)) if m else None
                            if slug:
                                self._contar(("kick", slug))
            except Exception as e:
                self.status["kick"] = f"reconectando ({type(e).__name__})"
                await asyncio.sleep(5)

    # --- YouTube (consulta periódica do chat ao vivo)
    def _gerir_youtube(self):
        if "youtube" not in self.plataformas:
            return
        for chave, info in self.ativos.items():
            if chave[0] == "youtube" and chave not in self._yt:
                parar = threading.Event()
                t = threading.Thread(target=self._ler_youtube, args=(chave, info.get("url"), parar), daemon=True)
                self._yt[chave] = (t, parar)
                t.start()
        for chave in list(self._yt):
            if chave not in self.ativos:
                self._yt.pop(chave)[1].set()

    def _ler_youtube(self, chave, url, parar):
        vid = id_video_youtube(url)
        if not vid:
            self.status["youtube"] = f"sem ID de vídeo para {chave[1]}"
            return
        sess = requests.Session()
        sess.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
        falhas = 0
        cont = chave_api = versao = None
        while not parar.is_set():
            try:
                if not cont:
                    html = sess.get(f"{self.yt_base}/live_chat?is_popout=1&v={vid}", timeout=20).text
                    m_key = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
                    m_ver = re.search(r'"INNERTUBE_CONTEXT_CLIENT_VERSION":"([^"]+)"', html)
                    m_dat = re.search(r'(?:window\["ytInitialData"\]|var ytInitialData)\s*=\s*(\{.*?\});\s*</script>', html, re.S)
                    if not (m_key and m_ver and m_dat):
                        raise RuntimeError("chat do YouTube indisponível para este vídeo")
                    chave_api, versao = m_key.group(1), m_ver.group(1)
                    dados = json.loads(m_dat.group(1))
                    conts = dados["contents"]["liveChatRenderer"]["continuations"][0]
                    d = next(iter(conts.values()))
                    cont = d["continuation"]
                r = sess.post(f"{self.yt_base}/youtubei/v1/live_chat/get_live_chat?key={chave_api}&prettyPrint=false",
                              json={"context": {"client": {"clientName": "WEB", "clientVersion": versao}},
                                    "continuation": cont}, timeout=20)
                r.raise_for_status()
                qtd, cont, espera = contar_mensagens_youtube(r.json())
                self.ok.add(chave)
                self.status["youtube"] = "conectado"
                if qtd:
                    self._contar(chave, qtd)
                falhas = 0
                parar.wait(espera)
            except Exception as e:
                falhas += 1
                cont = None
                self.status["youtube"] = f"falha em {chave[1]}: {e}"[:140]
                if falhas > 6:
                    return
                parar.wait(min(5 * falhas, 30))


# ----------------------------------------------------------------------------- teste por linha de comando
def main():
    ap = argparse.ArgumentParser(description="Testa a leitura de chat de cada plataforma.")
    ap.add_argument("--testar", nargs="+", required=True,
                    help="itens no formato plataforma:canal  (YouTube: youtube:LINK_DA_LIVE)")
    ap.add_argument("--segundos", type=int, default=40)
    a = ap.parse_args()

    ativos = {}
    for item in a.testar:
        plat, _, resto = item.partition(":")
        plat = plat.lower()
        if plat not in ("twitch", "kick", "youtube") or not resto:
            raise SystemExit(f"Formato inválido: {item}. Use twitch:canal, kick:canal ou youtube:LINK")
        if plat == "youtube":
            ativos[(plat, resto)] = {"url": resto}
        else:
            ativos[(plat, resto.lower())] = {"url": ""}

    mon = MonitorChat(ao_pico=lambda *args: None)
    mon.definir(ativos)
    print(f"Lendo o chat por {a.segundos} segundos...\n")
    for i in range(a.segundos):
        time.sleep(1)
        if i % 10 == 9:
            print(f"  {i + 1}s - " + " | ".join(f"{p}:{c[:28]}={mon.total.get((p, c), 0)}" for (p, c) in ativos))
    print("\nRESULTADO")
    for chave in ativos:
        n = mon.total.get(chave, 0)
        print(f"  {'OK  ' if n else 'FALHOU'} {chave[0]}:{chave[1][:50]} -> {n} mensagens em {a.segundos}s")
    print("\nStatus por plataforma:", json.dumps(mon.resumo(), ensure_ascii=False))
    print("Dica: se deu 0 mensagens, confira se a live está ao vivo e tem chat ativo.")


if __name__ == "__main__":
    main()
