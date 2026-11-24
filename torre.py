"""
TORRE DE CONTROLE
Vigia os canais escolhidos (Twitch, Kick, YouTube), registra quem está ao vivo e quantos espectadores,
detecta sinais de momento forte (salto de espectadores e explosão do chat na Twitch) e dispara
a gravação + corte automático (ao_vivo.py) para as lives mais assistidas.
Veja tudo no painel:  streamlit run painel.py  (aba "Torre").

Uso:
  python torre.py                 # monitora e grava (até 'gravar_no_maximo' lives ao mesmo tempo)
  python torre.py --sem-gravar    # só monitora (não grava nada)
  python torre.py --uma-vez       # faz uma checagem e sai (bom para testar a configuração)
"""
import argparse
import json
import re
import subprocess
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

import chat as chat_mod
import clipador as c
import sinal_parar
import torre_db as db

RAIZ = Path(__file__).parent
CONFIG = RAIZ / "canais.json"
LOGS = RAIZ / "logs"
OFFLINE = {"ao_vivo": False, "espectadores": 0, "jogo": "", "titulo": "", "url": "", "iniciada_em": ""}

PADRAO = {
    "intervalo_seg": 120,
    "intervalo_youtube_seg": 300,
    "gravar_no_maximo": 2,
    "chat": {"twitch": True, "kick": True, "youtube": True},
    "twitch": {"client_id": "", "client_secret": ""},
    "kick": {"client_id": "", "client_secret": ""},
    "ao_vivo_extra": ["--sem-horizontal"],
    "deteccao": {"min_espectadores": 100, "salto_espectadores": 0.30, "min_salto_absoluto": 150,
                 "chat_multiplicador": 3.0, "chat_min_por_min": 30, "cooldown_seg": 600},
    "canais": [],
}


def carregar_config(caminho):
    if not caminho.exists():
        sys.exit(f"Falta o {caminho.name}. Copie o canais.exemplo.json para canais.json e edite a lista de canais.")
    usuario = json.loads(caminho.read_text(encoding="utf-8"))
    cfg = json.loads(json.dumps(PADRAO))
    for k, v in usuario.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    if not cfg["canais"]:
        sys.exit("A lista 'canais' está vazia no canais.json.")
    return cfg


# ----------------------------------------------------------------------------- checagem de lives
class Token:
    """Token de aplicativo (client credentials), renovado automaticamente."""

    def __init__(self, url, client_id, client_secret):
        self.url, self.cid, self.secret = url, client_id, client_secret
        self.valor, self.expira = None, 0

    def get(self):
        if not self.valor or time.time() > self.expira - 300:
            r = requests.post(self.url, data={"grant_type": "client_credentials",
                                               "client_id": self.cid, "client_secret": self.secret}, timeout=20)
            r.raise_for_status()
            d = r.json()
            self.valor = d["access_token"]
            self.expira = time.time() + int(d.get("expires_in", 3600))
        return self.valor


def ytdlp_checar(url):
    """Pergunta ao yt-dlp se o link está ao vivo (não exige conta nem chave de API)."""
    try:
        r = subprocess.run([sys.executable, "-m", "yt_dlp", "-J", "--no-playlist", "--skip-download",
                            "--no-warnings", "--socket-timeout", "15"] + c.args_js() + [url],
                           capture_output=True, text=True, timeout=90)
        if r.returncode != 0 or not r.stdout.strip():
            return dict(OFFLINE)
        d = json.loads(r.stdout)
    except Exception:
        return dict(OFFLINE)
    if not d.get("is_live"):
        return dict(OFFLINE)
    cats = d.get("categories") or []
    return {"ao_vivo": True,
            "espectadores": int(d.get("concurrent_view_count") or d.get("view_count") or 0),
            "jogo": cats[0] if cats else "", "titulo": d.get("title") or "",
            "url": d.get("webpage_url") or url, "iniciada_em": str(d.get("release_timestamp") or "")}


def url_do_canal(plataforma, ident):
    if plataforma == "twitch":
        return f"https://www.twitch.tv/{ident}"
    if plataforma == "kick":
        return f"https://kick.com/{ident}"
    if ident.startswith("UC"):
        return f"https://www.youtube.com/channel/{ident}/live"
    return f"https://www.youtube.com/{ident if ident.startswith('@') else '@' + ident}/live"


def checador_twitch(cfg, base="https://api.twitch.tv/helix", url_token="https://id.twitch.tv/oauth2/token"):
    tok = Token(url_token, cfg["twitch"]["client_id"], cfg["twitch"]["client_secret"])
    usa_api = bool(cfg["twitch"]["client_id"] and cfg["twitch"]["client_secret"])

    def checar(ids):
        if not usa_api:
            with ThreadPoolExecutor(4) as ex:
                return dict(zip(ids, ex.map(lambda i: ytdlp_checar(url_do_canal("twitch", i)), ids)))
        achados = {}
        for i in range(0, len(ids), 100):
            lote = ids[i:i + 100]
            r = requests.get(f"{base}/streams", timeout=20,
                             headers={"Client-Id": cfg["twitch"]["client_id"], "Authorization": f"Bearer {tok.get()}"},
                             params=[("user_login", x) for x in lote] + [("first", 100)])
            r.raise_for_status()
            for s in r.json().get("data", []):
                if s.get("type") == "live":
                    achados[s["user_login"].lower()] = {
                        "ao_vivo": True, "espectadores": int(s.get("viewer_count") or 0),
                        "jogo": s.get("game_name", ""), "titulo": s.get("title", ""),
                        "url": url_do_canal("twitch", s["user_login"]), "iniciada_em": s.get("started_at", "")}
        return {x: achados.get(x.lower(), dict(OFFLINE)) for x in ids}
    return checar


def checador_kick(cfg, base="https://api.kick.com/public/v1", url_token="https://id.kick.com/oauth/token"):
    tok = Token(url_token, cfg["kick"]["client_id"], cfg["kick"]["client_secret"])
    usa_api = bool(cfg["kick"]["client_id"] and cfg["kick"]["client_secret"])

    def checar(ids):
        if not usa_api:
            with ThreadPoolExecutor(4) as ex:
                return dict(zip(ids, ex.map(lambda i: ytdlp_checar(url_do_canal("kick", i)), ids)))
        achados = {}
        for i in range(0, len(ids), 50):
            lote = ids[i:i + 50]
            r = requests.get(f"{base}/channels", timeout=20,
                             headers={"Authorization": f"Bearer {tok.get()}"},
                             params=[("slug", x) for x in lote])
            r.raise_for_status()
            for ch in r.json().get("data", []):
                st = ch.get("stream") or {}
                if st.get("is_live"):
                    achados[ch["slug"].lower()] = {
                        "ao_vivo": True, "espectadores": int(st.get("viewer_count") or 0),
                        "jogo": (ch.get("category") or {}).get("name", ""), "titulo": ch.get("stream_title", ""),
                        "url": url_do_canal("kick", ch["slug"]), "iniciada_em": st.get("start_time", "")}
        return {x: achados.get(x.lower(), dict(OFFLINE)) for x in ids}
    return checar


def checador_youtube(cfg):
    """YouTube via yt-dlp (sem gastar a cota da API). Checa menos vezes, porque é mais lento."""
    cache = {"ts": 0, "res": {}}

    def checar(ids):
        if time.time() - cache["ts"] < cfg["intervalo_youtube_seg"] and set(ids) <= set(cache["res"]):
            return {i: cache["res"][i] for i in ids}
        with ThreadPoolExecutor(4) as ex:
            res = dict(zip(ids, ex.map(lambda i: ytdlp_checar(url_do_canal("youtube", i)), ids)))
        cache.update(ts=time.time(), res=res)
        return res
    return checar


# ----------------------------------------------------------------------------- a Torre
class Torre:
    def __init__(self, cfg, gravar=True, usar_chat=True, checadores=None, lancar=None, caminho_config=None):
        self.cfg, self.gravar = cfg, gravar
        self.caminho = Path(caminho_config) if caminho_config else None
        self.mtime = self.caminho.stat().st_mtime if self.caminho and self.caminho.exists() else None
        self.checadores_padrao = checadores is None
        self.checadores = checadores or {"twitch": checador_twitch(cfg), "kick": checador_kick(cfg),
                                         "youtube": checador_youtube(cfg)}
        self.lancar = lancar or self._lancar_real
        self.hist, self.cool = {}, {}
        self.gravando, self.fim_gravacao = {}, {}
        self.nomes = {(x["plataforma"], x["id"].lower()): x for x in cfg["canais"]}
        self.chat = None
        plats = [p for p, ativo in cfg["chat"].items()
                 if ativo and any(x["plataforma"] == p for x in cfg["canais"])]
        if usar_chat and plats:
            d = cfg["deteccao"]
            self.chat = chat_mod.MonitorChat(self._pico_chat, plataformas=plats, multiplicador=d["chat_multiplicador"],
                                             min_por_min=d["chat_min_por_min"], ao_minuto=db.add_chat_minuto)

    def _recarregar_se_mudou(self):
        """Se você editou o canais.json (pelo painel ou à mão), a Torre passa a usar a lista nova sem reiniciar."""
        if not self.caminho:
            return
        try:
            m = self.caminho.stat().st_mtime
        except OSError:
            return
        if m == self.mtime:
            return
        self.mtime = m
        try:
            novo = carregar_config(self.caminho)
        except SystemExit as e:
            print(f"   (aviso) canais.json inválido, mantendo a lista anterior: {e}")
            return
        except Exception as e:
            print(f"   (aviso) não consegui ler o canais.json, mantendo a lista anterior: {e}")
            return
        self.cfg = novo
        self.nomes = {(x["plataforma"], x["id"].lower()): x for x in novo["canais"]}
        if self.checadores_padrao:
            self.checadores = {"twitch": checador_twitch(novo), "kick": checador_kick(novo), "youtube": checador_youtube(novo)}
        print(f"   ↻ canais.json atualizado: {len(novo['canais'])} canais")

    # --- sinais
    def _em_cooldown(self, chave):
        agora = time.time()
        if agora - self.cool.get(chave, 0) < self.cfg["deteccao"]["cooldown_seg"]:
            return True
        self.cool[chave] = agora
        return False

    def _pico_chat(self, plataforma, canal, taxa, base):
        if self._em_cooldown(("chat", plataforma, canal.lower())):
            return
        nota = taxa / max(base, 1.0)
        db.add_momento(plataforma, canal, "chat", nota)
        print(f"   💬 chat explodiu em {canal} ({plataforma}): {taxa:.0f} msg/min (normal ~{base:.0f}) -> sinal registrado")

    def _checar_espectadores(self, chave, info):
        h = self.hist.setdefault(chave, deque(maxlen=10))
        if not info["ao_vivo"]:
            h.clear()
            return
        d = self.cfg["deteccao"]
        if h:
            ant = h[-1]
            atual = info["espectadores"]
            if (ant >= d["min_espectadores"] and atual >= ant * (1 + d["salto_espectadores"])
                    and atual - ant >= d["min_salto_absoluto"] and not self._em_cooldown(("esp",) + chave)):
                db.add_momento(chave[0], chave[1], "espectadores", atual / ant)
                print(f"   📈 salto de espectadores em {chave[1]}: {ant} -> {atual} -> sinal registrado")
        h.append(info["espectadores"])

    # --- gravação
    def _lancar_real(self, ch, info):
        LOGS.mkdir(exist_ok=True)
        log = open(LOGS / f"ao_vivo_{ch['plataforma']}_{re.sub(r'[^A-Za-z0-9]', '', ch['id'])}.log", "a", encoding="utf-8")
        cmd = [sys.executable, str(RAIZ / "ao_vivo.py"), "--url", info["url"] or url_do_canal(ch["plataforma"], ch["id"]),
               "--credito", ch.get("nome", ch["id"]), "--torre-plataforma", ch["plataforma"],
               "--torre-canal", ch["id"]] + list(self.cfg["ao_vivo_extra"])
        import tarefas
        return subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(RAIZ), env=tarefas.env_utf8())

    def _gerenciar_gravacoes(self, infos):
        for chave, p in list(self.gravando.items()):
            if p.poll() is not None:
                del self.gravando[chave]
                self.fim_gravacao[chave] = time.time()
                print(f"   ⏹ gravação de {chave[1]} terminou (código {p.returncode})")
        if not self.gravar:
            return
        livres = self.cfg["gravar_no_maximo"] - len(self.gravando)
        if livres <= 0:
            return
        candidatos = []
        for chave, info in infos.items():
            ch = self.nomes[chave]
            if (info["ao_vivo"] and ch.get("gravar", True) and chave not in self.gravando
                    and time.time() - self.fim_gravacao.get(chave, 0) > 90):
                candidatos.append((info["espectadores"], chave, ch, info))
        for _, chave, ch, info in sorted(candidatos, key=lambda x: -x[0])[:livres]:
            self.gravando[chave] = self.lancar(ch, info)
            print(f"   🎧 gravando {ch.get('nome', ch['id'])} ({info['espectadores']} espectadores)")

    # --- ciclo principal
    def ciclo(self):
        self._recarregar_se_mudou()
        por_plat = {}
        for ch in self.cfg["canais"]:
            por_plat.setdefault(ch["plataforma"], []).append(ch["id"])

        def tarefa(item):
            plat, ids = item
            try:
                return plat, self.checadores[plat](ids)
            except Exception as e:
                print(f"   (aviso) falha ao checar {plat}: {e}")
                return plat, None

        with ThreadPoolExecutor(3) as ex:
            resultados = dict(ex.map(tarefa, por_plat.items()))

        infos = {}
        for ch in self.cfg["canais"]:
            chave = (ch["plataforma"], ch["id"].lower())
            res = resultados.get(ch["plataforma"])
            if res is None:                    # falhou: mantém o que já sabíamos
                continue
            infos[chave] = res.get(ch["id"], res.get(ch["id"].lower(), dict(OFFLINE)))

        if self.chat:
            self.chat.definir({k: i for k, i in infos.items() if i["ao_vivo"]})
        for chave, info in infos.items():
            self._checar_espectadores(chave, info)
        self._gerenciar_gravacoes(infos)

        for chave, info in infos.items():
            ch = self.nomes[chave]
            status = "🎧 Ouvindo" if chave in self.gravando else ("📡 Ao vivo" if info["ao_vivo"] else "⚫ Offline")
            chat = self.chat.taxa(chave[0], chave[1]) if self.chat else None
            db.set_canal(chave[0], ch["id"], ch.get("nome", ch["id"]), info, status, chat)
            db.add_amostra(chave[0], ch["id"], info, chat)
        db.sincronizar_canais([(x["plataforma"], x["id"]) for x in self.cfg["canais"]])
        db.set_estado("ultimo_ciclo", time.time())
        if self.chat:
            db.set_estado("chat_status", json.dumps(self.chat.resumo(), ensure_ascii=False))

        vivos = [(i["espectadores"], self.nomes[k].get("nome", k[1]), k[0]) for k, i in infos.items() if i["ao_vivo"]]
        print(f"[{time.strftime('%H:%M:%S')}] {len(vivos)}/{len(infos)} ao vivo | "
              f"{sum(v[0] for v in vivos)} espectadores | gravando {len(self.gravando)}")
        for esp, nome, plat in sorted(vivos, reverse=True)[:8]:
            print(f"     {nome:<20} {plat:<8} {esp:>7}")

    def encerrar(self):
        """Pede às gravações para terminarem (elas finalizam os cortes da fila) e espera."""
        for p in self.gravando.values():
            if p.poll() is None:
                sinal_parar.pedir(p.pid)
        ultimo_aviso = 0
        while True:
            vivas = [p for p in self.gravando.values() if p.poll() is None]
            if not vivas:
                return
            if time.time() - ultimo_aviso > 30:
                print(f"   aguardando {len(vivas)} gravação(ões) terminarem de renderizar os cortes... "
                      f"(use o botão Forçar no painel para encerrar na hora)")
                ultimo_aviso = time.time()
            try:
                time.sleep(2)
            except KeyboardInterrupt:
                for p in vivas:
                    p.kill()
                return


def limpar_gravacoes_antigas(horas=24):
    limite = time.time() - horas * 3600
    for f in c.TRABALHO.glob("live_*"):
        try:
            if f.is_file() and f.stat().st_mtime < limite:
                f.unlink()
        except OSError:
            pass


def _sinais():
    """No Windows, o botão Parar do painel envia Ctrl+Break: trata como Ctrl+C (parada com calma)."""
    import signal
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--sem-gravar", action="store_true", help="só monitora, não grava nem corta")
    ap.add_argument("--sem-chat", action="store_true", help="não lê o chat da Twitch")
    ap.add_argument("--uma-vez", action="store_true", help="faz uma checagem e sai")
    a = ap.parse_args()
    _sinais()
    sinal_parar.limpar()
    sinal_parar.limpar_antigos()

    cfg = carregar_config(Path(a.config))
    db.limpar()
    torre = Torre(cfg, gravar=not a.sem_gravar, usar_chat=not a.sem_chat, caminho_config=a.config)
    print(f"Torre de Controle iniciada: {len(cfg['canais'])} canais, checagem a cada {cfg['intervalo_seg']}s. "
          f"Ctrl+C para parar.\n")
    ultima_limpeza = 0
    try:
        while True:
            torre.ciclo()
            if a.uma_vez:
                break
            if time.time() - ultima_limpeza > 3600:
                limpar_gravacoes_antigas()
                ultima_limpeza = time.time()
            sinal_parar.dormir(cfg["intervalo_seg"])
    except KeyboardInterrupt:
        print("\nParando a Torre. Aguardando as gravações em andamento terminarem de renderizar...")
    torre.encerrar()
    sinal_parar.limpar()
    print("Torre encerrada.")


if __name__ == "__main__":
    main()
