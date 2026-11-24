"""CENTRAL DO CLIPADOR - tudo por cliques: novo corte, Torre de Controle, aprovação, publicação e compilado."""
import importlib.util
import json
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import estilo
import sinal_parar
import tarefas

RAIZ = Path(__file__).parent
CLIPS = RAIZ / "clips"
PEND, APROV, REJ = CLIPS / "pendentes", CLIPS / "aprovados", CLIPS / "rejeitados"
COMPILADOS = RAIZ / "compilados"
CANAIS, CANAIS_EX = RAIZ / "canais.json", RAIZ / "canais.exemplo.json"
IG_CFG = RAIZ / "instagram_config.json"
for p in (PEND, APROV, REJ):
    p.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="Clipador GTA VI", page_icon="🎬", layout="wide")
estilo.aplicar()
tarefas.limpar_logs()
sinal_parar.limpar_antigos()


def limpar_orfaos():
    """Apaga pastas de cortes que ficaram pela metade (renderização interrompida) há mais de 1 hora."""
    for d in PEND.iterdir():
        try:
            if d.is_dir() and not (d / "meta.json").exists() and time.time() - d.stat().st_mtime > 3600:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


limpar_orfaos()


# =============================================================== utilidades
def ler(caminho):
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def salvar(caminho, dados):
    Path(caminho).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def aprovados():
    return sorted(APROV.glob("*/meta.json"))


def abrir_pasta(caminho):
    Path(caminho).mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(caminho))  # noqa
    else:
        st.info(f"Pasta: {caminho}")


def legenda_tiktok(meta):
    partes = [meta["titulo"]]
    if meta.get("credito"):
        partes.append(f"Corte da live de {meta['credito']} 🎮")
    tags = meta.get("hashtags", "#GTA6 #GTAVI").replace("#shorts", "").strip()
    partes.append(f"{tags} #fyp #gaming")
    return "\n".join(partes)


def canais_estado():
    """Lê o canais.json sem derrubar o painel. Retorna (dados, erro): dados=None se não existe ou está com erro."""
    if not CANAIS.exists():
        return None, None
    try:
        return ler(CANAIS), None
    except ValueError as e:                      # erro de digitação no arquivo
        return None, e


def canais_ok():
    dados, _ = canais_estado()
    return bool(dados and dados.get("canais"))


def config_canais():
    dados, _ = canais_estado()
    base = dados if dados is not None else ler(CANAIS_EX)
    if dados is None:
        base["canais"] = []
    base.setdefault("chat", {"twitch": True, "kick": True, "youtube": True})
    base.setdefault("twitch", {"client_id": "", "client_secret": ""})
    base.setdefault("kick", {"client_id": "", "client_secret": ""})
    return base


def reparar_json(texto):
    """Conserta os erros de digitação mais comuns: vírgula esquecida entre linhas e vírgula sobrando antes de } ou ]."""
    linhas = texto.splitlines()
    novas = []
    for i, ln in enumerate(linhas):
        atual = ln.rstrip()
        prox = next((l.strip() for l in linhas[i + 1:] if l.strip()), "")
        if atual.strip() and prox and re.search(r'("|\d|true|false|null|\}|\])$', atual.strip()) and re.match(r'^[\{\["]', prox):
            atual += ","
        novas.append(atual)
    return re.sub(r",(\s*[}\]])", r"\1", "\n".join(novas))


def aviso_canais_invalido():
    """Se o canais.json estiver com erro, explica onde e oferece conserto em 1 clique."""
    dados, erro = canais_estado()
    if erro is None:
        return
    st.error(f"⚠️ O arquivo **canais.json** tem um erro de digitação (linha {erro.lineno}, coluna {erro.colno}): {erro.msg}. "
             "Enquanto isso, o painel trata a lista de canais como vazia.")
    linhas = CANAIS.read_text(encoding="utf-8").splitlines()
    a, b = max(0, erro.lineno - 4), min(len(linhas), erro.lineno + 1)
    st.code("\n".join(f"{i + 1:>3} | {linhas[i]}" for i in range(a, b)), language=None)
    st.caption("O erro costuma ser uma **vírgula esquecida no fim da linha de cima**, ou uma vírgula a mais na última linha de uma lista.")
    c1, c2, _ = st.columns([1, 1, 3])
    if c1.button("🛠️ Corrigir automaticamente", type="primary"):
        texto = CANAIS.read_text(encoding="utf-8")
        novo = reparar_json(texto)
        try:
            json.loads(novo)
        except ValueError:
            st.warning("Não consegui corrigir sozinho. Use **Recriar do zero** ou arrume a linha indicada no Bloco de Notas.")
        else:
            (RAIZ / "canais.json.bak").write_text(texto, encoding="utf-8")
            CANAIS.write_text(novo, encoding="utf-8")
            st.rerun()
    if c2.button("♻️ Recriar do zero (faz backup)"):
        (RAIZ / "canais.json.bak").write_text(CANAIS.read_text(encoding="utf-8"), encoding="utf-8")
        base = ler(CANAIS_EX)
        base["canais"] = []
        salvar(CANAIS, base)
        st.rerun()
    st.stop()


def paginar(itens, chave, por_pagina=5):
    """Mostra poucos itens por vez (deixa o painel leve mesmo com dezenas de vídeos)."""
    total = len(itens)
    paginas = max(1, -(-total // por_pagina))
    k = f"pag_{chave}"
    if st.session_state.get(k, 1) > paginas:
        st.session_state[k] = paginas
    pag = 1
    if paginas > 1:
        c1, c2 = st.columns([1, 5])
        pag = c1.number_input(f"Página (de {paginas})", 1, paginas, 1, key=k)
        c2.caption(f"{total} itens no total")
    return itens[(pag - 1) * por_pagina: pag * por_pagina]


def _tarefas_view(tipos, chave):
    lista = tarefas.listar(tipos)[:4]
    if not lista:
        st.caption("Nada em andamento.")
        return
    for t in lista:
        quando = datetime.fromtimestamp(t["inicio"]).strftime("%H:%M:%S")
        if t["ativa"]:
            estado = "⏳ parando..." if t.get("parando") else "🟢 rodando"
        else:
            estado = "✅ finalizada"
        with st.expander(f"{estado} • {t['titulo']} • iniciada às {quando}", expanded=t["ativa"]):
            st.code(tarefas.ler_log(t) or "(aguardando saída...)", language=None)
            if t["ativa"]:
                c1, c2, _ = st.columns([1, 1, 4])
                if c1.button("⏹ Parar", key=f"p_{chave}_{t['id']}", help="Para com calma: termina o que estiver renderizando"):
                    tarefas.parar(t["id"])
                    st.rerun()
                if c2.button("⛔ Forçar", key=f"f_{chave}_{t['id']}", help="Encerra na hora"):
                    tarefas.forcar(t["id"])
                    st.rerun()


def painel_tarefas(tipos, chave):
    """Mostra as tarefas e atualiza sozinho enquanto houver alguma rodando."""
    if hasattr(st, "fragment"):
        ativa = any(t["ativa"] for t in tarefas.listar(tipos))
        st.fragment(run_every=3 if ativa else None)(_tarefas_view)(tipos, chave)
    else:
        _tarefas_view(tipos, chave)


def verificacoes():
    ig_ok = IG_CFG.exists() and "COLE_AQUI" not in IG_CFG.read_text(encoding="utf-8")
    return [
        ("Editor de vídeo (ffmpeg)", bool(shutil.which("ffmpeg")), "Rode o instalar.bat de novo", False),
        ("Motor de JavaScript para o YouTube (Deno ou Node)", bool(shutil.which("deno") or shutil.which("node")),
         "Rode o instalar.bat de novo", False),
        ("Download de lives (yt-dlp)", importlib.util.find_spec("yt_dlp") is not None, "Rode o instalar.bat de novo", False),
        ("YouTube conectado", (RAIZ / "token.json").exists(), "Aba ⚙️ Configurações > Conectar YouTube", False),
        ("Instagram configurado", ig_ok, "Aba ⚙️ Configurações > Instagram", False),
        ("Canais da Torre cadastrados", canais_ok(), "Aba 🗼 Torre > Meus canais", False),
        ("Chat da Kick (curl_cffi)", importlib.util.find_spec("curl_cffi") is not None,
         "Opcional: aumenta a chance de ler o chat da Kick. Rode o instalar.bat de novo", True),
    ]


# =============================================================== Torre (painel ao vivo)
def _hoje_ts():
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _status_real(m):
    pasta = m.get("pasta")
    if not pasta:
        return "Sinal (chat/espectadores)"
    if (PEND / pasta / "meta.json").exists():
        return "Aguardando aprovação"
    mp = APROV / pasta / "meta.json"
    if mp.exists():
        meta = ler(mp)
        return "Postado" if (meta.get("youtube_url") or meta.get("instagram_url") or meta.get("tiktok_postado")) else "Aprovado"
    if (REJ / pasta).exists():
        return "Rejeitado"
    return "Erro" if m.get("status") == "erro" else "Renderizando"


def render_torre():
    try:
        import torre_db as tdb
        canais = tdb.consultar("SELECT * FROM canais_estado ORDER BY espectadores DESC")
        momentos = tdb.consultar("SELECT * FROM momentos WHERE ts >= ? ORDER BY ts DESC", (_hoje_ts(),))
        ultimo = tdb.get_estado("ultimo_ciclo")
        chat_status = tdb.get_estado("chat_status")
    except Exception as e:
        st.error(f"Não consegui ler o banco da Torre: {e}")
        return
    if not canais:
        st.info("A Torre ainda não registrou nada. Cadastre seus canais em **Meus canais** (mais abaixo) e clique em **Ligar a Torre**.")
        return
    if ultimo:
        atraso = time.time() - float(ultimo)
        if atraso > 600:
            st.warning(f"A Torre parece parada (última checagem há {int(atraso // 60)} min). Clique em **Ligar a Torre**.")
        else:
            st.caption(f"Última checagem há {int(atraso)} s • esta área atualiza sozinha")

    vivos = [c for c in canais if c["ao_vivo"]]
    m = st.columns(5)
    m[0].metric("Lives monitoradas", len(canais))
    m[1].metric("Ao vivo agora", len(vivos))
    m[2].metric("Espectadores (todas)", f"{sum(c['espectadores'] for c in vivos):,}".replace(",", "."))
    m[3].metric("Gravando agora", len([c for c in vivos if "Ouvindo" in (c["status"] or "")]))
    m[4].metric("Momentos hoje", len(momentos))

    st.subheader("Esteira de produção (hoje)")
    contagem = {}
    for mo in momentos:
        k = _status_real(mo)
        contagem[k] = contagem.get(k, 0) + 1
    estilo.esteira([(e, contagem.get(e, 0)) for e in
                    ["Sinal (chat/espectadores)", "Renderizando", "Aguardando aprovação", "Aprovado", "Postado"]])
    extras = {k: contagem.get(k, 0) for k in ("Rejeitado", "Erro")}
    if any(extras.values()):
        st.caption("Também hoje: " + " • ".join(f"{k}: {v}" for k, v in extras.items() if v))

    st.subheader("Ao vivo agora")
    if vivos:
        estilo.grade_lives(vivos)
    else:
        st.write("Nenhum canal monitorado está ao vivo agora.")
    off = [c["nome"] for c in canais if not c["ao_vivo"]]
    if off:
        st.caption("Offline: " + ", ".join(off))

    if chat_status:
        try:
            cs = json.loads(chat_status)
            st.caption("💬 Leitura de chat: " + " • ".join(f"{estilo.PLAT_NOME.get(k, k)}: {v}" for k, v in cs.items()))
        except ValueError:
            pass

    st.subheader("Últimos momentos detectados")
    if momentos:
        st.dataframe([{"Hora": datetime.fromtimestamp(x["ts"]).strftime("%H:%M:%S"), "Canal": x["canal"],
                       "Plataforma": x["plataforma"], "Origem": x["origem"], "Nota": round(x["nota"], 1),
                       "Situação": _status_real(x), "Corte": x["pasta"] or "—"} for x in momentos[:30]],
                     hide_index=True)
    else:
        st.write("Nenhum momento detectado hoje ainda.")


# =============================================================== abas
def aba_inicio():
    st.header("Bem-vindo")
    pend = len(list(PEND.glob("*/meta.json")))
    ativas = [t for t in tarefas.listar() if t["ativa"]]
    c = st.columns(4)
    c[0].metric("Cortes para aprovar", pend)
    c[1].metric("Aprovados", len(aprovados()))
    c[2].metric("Rejeitados", len(list(REJ.glob("*/meta.json"))))
    c[3].metric("Tarefas rodando", len(ativas))

    st.subheader("Como usar")
    estilo.passos([
        ("➕ Novo corte", "Cole o link de uma live (ao vivo ou encerrada) e clique em Gerar cortes."),
        ("✅ Aprovação", "Assista aos cortes, ajuste o título e aprove ou rejeite."),
        ("📤 Publicar", "Envie ao YouTube e ao Instagram e use o modo assistido do TikTok."),
        ("🗼 Torre", "Cadastre canais e deixe o sistema vigiar, gravar e cortar sozinho."),
    ])

    st.subheader("Está tudo pronto?")
    tudo = True
    for nome, ok, dica, opcional in verificacoes():
        tudo &= ok or opcional
        estilo.checagem(nome, ok, dica, opcional)
    if tudo:
        st.success("Tudo configurado. Bons cortes! 🎉")
    if ativas:
        st.subheader("Em andamento agora")
        painel_tarefas(["cortes", "ao_vivo", "torre", "postar", "compilado", "conectar"], "inicio")


def aba_novo():
    st.header("➕ Novo corte")
    st.write("Cole o link de uma live ou vídeo da **Twitch, Kick ou YouTube**. O sistema acha os melhores momentos "
             "e gera os cortes verticais de 30 s, que aparecem na aba ✅ Aprovação.")
    with st.form("form_novo"):
        link = st.text_input("Link da live ou vídeo", placeholder="https://www.twitch.tv/videos/...  ou  https://youtube.com/watch?v=...")
        credito = st.text_input("Nome do streamer (aparece no vídeo como crédito)", placeholder="Ex.: Gaules")
        modo = st.radio("Como está essa live?",
                        ["Já terminou (ou é um vídeo gravado)", "Está acontecendo agora (acompanhar e cortar em tempo real)"])
        col1, col2, col3 = st.columns(3)
        qtd = col1.slider("Quantidade de cortes", 3, 20, 10, help="Só para lives que já terminaram")
        legenda = col2.checkbox("Legenda automática", value=False, help="Mais lento no seu PC")
        horizontal = col3.checkbox("Preparar para o compilado", value=True, help="Gera também a versão horizontal (mais lento)")
        enviar = st.form_submit_button("🚀 Gerar cortes", type="primary")
    if enviar:
        if not link.strip().startswith("http"):
            st.error("Cole um link válido (começando com https://).")
        elif "agora" in modo:
            args = ["ao_vivo.py", "--url", link.strip(), "--credito", credito.strip()]
            if legenda:
                args.append("--com-legenda")
            if not horizontal:
                args.append("--sem-horizontal")
            tarefas.iniciar("ao_vivo", f"Ao vivo: {credito or link[:40]}", args)
            st.success("Gravando a live! Os cortes vão aparecendo em ✅ Aprovação conforme surgirem momentos fortes.")
        else:
            args = ["clipador.py", "--url", link.strip(), "--credito", credito.strip(), "--quantidade", str(qtd)]
            if not legenda:
                args.append("--sem-legenda")
            if not horizontal:
                args.append("--sem-horizontal")
            tarefas.iniciar("cortes", f"Cortes: {credito or link[:40]}", args)
            st.success("Iniciado! Acompanhe abaixo. Quando terminar, vá em ✅ Aprovação.")
    st.subheader("Em andamento")
    painel_tarefas(["cortes", "ao_vivo"], "novo")


def aba_torre():
    st.header("🗼 Torre de Controle")
    def _controle():
        rodando = tarefas.ativa("torre")
        c1, c2 = st.columns([2, 3])
        with c1:
            if rodando and rodando.get("parando"):
                st.warning("⏳ **Desligando...** Terminando de renderizar os cortes que estavam na fila. "
                           "Pode levar alguns minutos.")
                if st.button("⛔ Forçar desligamento agora", key="forcar_torre"):
                    tarefas.forcar(rodando["id"])
                    st.rerun()
                st.caption("Forçar encerra na hora; o corte que estiver sendo renderizado nesse instante é perdido.")
            elif rodando:
                st.success("A Torre está **ligada**.")
                if st.button("⏹ Desligar a Torre", key="desligar_torre"):
                    tarefas.parar(rodando["id"])
                    st.rerun()
            else:
                st.warning("A Torre está **desligada**.")
                gravar = st.checkbox("Gravar e cortar automaticamente as lives mais assistidas", value=True,
                                     help="Desmarque para só monitorar (não grava nada)")
                ok = canais_ok()
                if st.button("▶️ Ligar a Torre", type="primary", disabled=not ok, key="ligar_torre"):
                    tarefas.iniciar("torre", "Torre de Controle", ["torre.py"] + ([] if gravar else ["--sem-gravar"]))
                    st.rerun()
                if not ok:
                    st.caption("Cadastre pelo menos um canal em **Meus canais** (abaixo).")
        with c2:
            st.caption("Dica: não feche a janela preta do Clipador enquanto a Torre estiver ligada.")

    if hasattr(st, "fragment"):
        st.fragment(run_every=3 if tarefas.ativa("torre") else None)(_controle)()
    else:
        _controle()

    if hasattr(st, "fragment"):
        st.fragment(run_every=15)(render_torre)()
    else:
        render_torre()

    with st.expander("📝 Meus canais (quem a Torre vigia)", expanded=not canais_ok()):
        cfg = config_canais()
        df = pd.DataFrame(cfg["canais"] or [{"plataforma": "twitch", "id": "", "nome": "", "gravar": True}],
                          columns=["plataforma", "id", "nome", "gravar"])
        editado = st.data_editor(
            df, num_rows="dynamic", hide_index=True, key="ed_canais",
            column_config={
                "plataforma": st.column_config.SelectboxColumn("Plataforma", options=["twitch", "kick", "youtube"], required=True),
                "id": st.column_config.TextColumn("Canal (Twitch/Kick: nome na URL • YouTube: @canal)", required=True),
                "nome": st.column_config.TextColumn("Nome (crédito)"),
                "gravar": st.column_config.CheckboxColumn("Gravar e cortar", default=True)})
        maximo = st.slider("Gravar no máximo quantas lives ao mesmo tempo?", 1, 3, int(cfg.get("gravar_no_maximo", 1)),
                           help="No seu PC, 1 ou 2 é o ideal")
        st.caption("Ler o chat de quais plataformas?")
        k1, k2, k3 = st.columns(3)
        chat_tw = k1.checkbox("Twitch", value=cfg["chat"].get("twitch", True))
        chat_kk = k2.checkbox("Kick", value=cfg["chat"].get("kick", True))
        chat_yt = k3.checkbox("YouTube", value=cfg["chat"].get("youtube", True))
        if st.button("💾 Salvar canais"):
            linhas = [{"plataforma": r["plataforma"], "id": str(r["id"]).strip(), "nome": str(r["nome"] or r["id"]).strip(),
                       "gravar": bool(r["gravar"])} for r in editado.to_dict("records")
                      if str(r.get("id") or "").strip() and str(r.get("id")) != "nan"]
            cfg["canais"], cfg["gravar_no_maximo"] = linhas, maximo
            cfg["chat"] = {"twitch": chat_tw, "kick": chat_kk, "youtube": chat_yt}
            salvar(CANAIS, cfg)
            st.success(f"{len(linhas)} canal(is) salvo(s). Se a Torre estiver ligada, desligue e ligue de novo.")

    with st.expander("🎥 Testar a gravação de uma live"):
        st.caption("Confere em cerca de 1 minuto se o sistema consegue gravar uma live (e mostra qual método funcionou). "
                   "A live precisa estar ao vivo agora.")
        link_t = st.text_input("Link da live", key="link_teste_grav", placeholder="https://www.twitch.tv/canal  ou  https://kick.com/canal")
        if st.button("🔍 Testar gravação", disabled=not link_t.strip().startswith("http")):
            tarefas.iniciar("conectar", "Teste de gravação", ["ao_vivo.py", "--url", link_t.strip(), "--so-testar"])
            st.success("Teste iniciado! O resultado aparece abaixo em instantes (procure por TESTE OK).")
        painel_tarefas(["conectar"], "grav")

    with st.expander("💬 Testar a leitura de chat"):
        st.caption("Confirma se o chat de uma live está sendo lido. A live precisa estar ao vivo e com mensagens.")
        t1, t2, t3 = st.columns([1, 3, 1])
        plat = t1.selectbox("Plataforma", ["twitch", "kick", "youtube"])
        alvo = t2.text_input("Canal (Twitch/Kick) ou link da live (YouTube)")
        seg = t3.number_input("Segundos", 15, 120, 40)
        if st.button("🔍 Testar leitura de chat", disabled=not alvo.strip()):
            tarefas.iniciar("conectar", f"Teste de chat: {plat}", ["chat.py", "--testar", f"{plat}:{alvo.strip()}",
                                                                   "--segundos", str(int(seg))])
            st.success("Teste iniciado! O resultado aparece abaixo em alguns segundos.")
        painel_tarefas(["conectar"], "chat")
    painel_tarefas(["torre"], "torre")


def aba_aprovacao():
    st.header("✅ Aprovação")
    pendentes = sorted(PEND.glob("*/meta.json"))
    if not pendentes:
        st.info("Nenhum corte para aprovar agora. Gere cortes na aba ➕ Novo corte ou ligue a 🗼 Torre.")
    for meta_path in paginar(pendentes, "aprov"):
        pasta = meta_path.parent
        meta = ler(meta_path)
        with st.container(border=True):
            col_v, col_f = st.columns([1, 2])
            with col_v:
                st.video(str(pasta / "video.mp4"))
            with col_f:
                st.caption(f"{pasta.name} • nota {meta['nota']} • fonte: {meta['fonte']}")
                meta["titulo"] = st.text_input("Título", meta["titulo"], key=f"t{pasta.name}")
                meta["credito"] = st.text_input("Crédito (streamer)", meta["credito"], key=f"c{pasta.name}")
                meta["hashtags"] = st.text_input("Hashtags", meta["hashtags"], key=f"h{pasta.name}")
                b1, b2, _ = st.columns([1, 1, 3])
                if b1.button("✅ Aprovar", key=f"a{pasta.name}", type="primary"):
                    salvar(meta_path, meta)
                    shutil.move(str(pasta), str(APROV / pasta.name))
                    st.rerun()
                if b2.button("🗑️ Rejeitar", key=f"r{pasta.name}"):
                    shutil.move(str(pasta), str(REJ / pasta.name))
                    st.rerun()


def aba_publicar():
    st.header("📤 Publicar")
    lista = [(m, ler(m)) for m in aprovados()]
    sem_yt = [x for x in lista if not x[1].get("youtube_id")]
    sem_ig = [x for x in lista if not x[1].get("instagram_url")]
    sem_tk = [x for x in lista if not x[1].get("tiktok_postado")]
    if not lista:
        st.info("Nada aprovado ainda. Aprove cortes na aba ✅ Aprovação.")

    with st.container(border=True):
        st.subheader("▶️ YouTube Shorts")
        if not (RAIZ / "token.json").exists():
            st.warning("Conecte o YouTube primeiro em ⚙️ Configurações.")
        st.write(f"**{len(sem_yt)}** corte(s) aprovado(s) ainda não postado(s). Sobem como **privados** — "
                 "você publica em lote no YouTube Studio.")
        n = st.number_input("Quantos enviar agora (limite do YouTube ≈ 6 por dia)", 1, 6, min(max(len(sem_yt), 1), 6), key="n_yt")
        if st.button("Enviar para o YouTube", type="primary", disabled=not sem_yt or not (RAIZ / "token.json").exists()):
            tarefas.iniciar("postar", "Postar no YouTube", ["postar_youtube.py", "--max", str(int(n))])
            st.success("Enviando! Acompanhe abaixo.")

    with st.container(border=True):
        st.subheader("📸 Instagram Reels")
        ig_ok = IG_CFG.exists() and "COLE_AQUI" not in IG_CFG.read_text(encoding="utf-8")
        if not ig_ok:
            st.warning("Configure o Instagram em ⚙️ Configurações.")
        st.write(f"**{len(sem_ig)}** corte(s) aprovado(s) ainda não postado(s). ⚠️ No Instagram o post sai **na hora e público**.")
        n2 = st.number_input("Quantos postar agora", 1, 10, min(max(len(sem_ig), 1), 3), key="n_ig")
        ciente = st.checkbox("Revisei e quero postar como público agora", key="ok_ig")
        if st.button("Postar no Instagram", type="primary", disabled=not (sem_ig and ig_ok and ciente)):
            tarefas.iniciar("postar", "Postar no Instagram", ["postar_instagram.py", "--max", str(int(n2)), "--sim"])
            st.success("Postando! Acompanhe abaixo.")

    with st.container(border=True):
        st.subheader("🎵 TikTok (assistido)")
        st.caption("O TikTok só aceita posts públicos de apps auditados. Baixe o vídeo, copie a legenda e envie pelo "
                   "TikTok Studio (tiktok.com/tiktokstudio/upload), que também permite agendar.")
        if not sem_tk:
            st.success("Tudo que está aprovado já foi marcado como postado no TikTok.")
        for meta_path, meta in paginar(sem_tk, "tk", 3):
            pasta = meta_path.parent
            col_v, col_f = st.columns([1, 2])
            with col_v:
                st.video(str(pasta / "video.mp4"))
            with col_f:
                st.code(legenda_tiktok(meta), language=None)
                st.download_button("⬇️ Baixar vídeo", data=(pasta / "video.mp4").read_bytes(), file_name=f"{pasta.name}.mp4",
                                   mime="video/mp4", key=f"d{pasta.name}")
                if st.button("✔️ Marcar como postado no TikTok", key=f"tk{pasta.name}"):
                    meta["tiktok_postado"] = True
                    salvar(meta_path, meta)
                    st.rerun()

    st.subheader("📋 Situação de cada corte")
    if lista:
        st.dataframe([{"Corte": m.parent.name, "Título": d["titulo"], "YouTube": d.get("youtube_url", "—"),
                       "Instagram": d.get("instagram_url", "—"), "TikTok": "✅" if d.get("tiktok_postado") else "—"}
                      for m, d in lista], hide_index=True)
    st.subheader("Em andamento")
    painel_tarefas(["postar"], "publicar")


def aba_compilado():
    st.header("🎞️ Compilado de ~15 minutos")
    com_h = [m for m in aprovados() if (m.parent / "horizontal.mp4").exists()]
    st.write(f"Cortes aprovados com versão horizontal: **{len(com_h)}** (30 cortes = 15 min). "
             "Para ter a versão horizontal, deixe marcado *Preparar para o compilado* ao gerar os cortes.")
    if st.button("🎬 Montar compilado", type="primary", disabled=not com_h):
        tarefas.iniciar("compilado", "Montar compilado", ["compilado.py"])
        st.success("Montando! Acompanhe abaixo.")
    painel_tarefas(["compilado"], "comp")

    st.subheader("Compilados prontos")
    arquivos = sorted(COMPILADOS.glob("compilado_*.mp4"), reverse=True) if COMPILADOS.exists() else []
    if not arquivos:
        st.caption("Nenhum compilado ainda.")
        return
    escolhido = st.selectbox("Escolha", [a.name for a in arquivos])
    caminho = COMPILADOS / escolhido
    if st.button("📂 Abrir a pasta dos compilados"):
        abrir_pasta(COMPILADOS)
    desc = caminho.with_name(caminho.stem + "_descricao.txt")
    if desc.exists():
        with st.expander("Descrição com capítulos e créditos (copie para o YouTube)"):
            st.code(desc.read_text(encoding="utf-8"), language=None)
    titulo = st.text_input("Título no YouTube", "Os melhores momentos do lançamento do GTA 6 🔥")
    if st.button("▶️ Enviar compilado ao YouTube (privado)", type="primary", disabled=not (RAIZ / "token.json").exists()):
        tarefas.iniciar("postar", "Postar compilado no YouTube",
                        ["postar_youtube.py", "--compilado", str(caminho), "--titulo", titulo])
        st.success("Enviando! Acompanhe em 📤 Publicar.")


def aba_config():
    st.header("⚙️ Configurações")
    st.subheader("Verificação")
    for nome, ok, dica, opcional in verificacoes():
        estilo.checagem(nome, ok, dica, opcional)

    st.subheader("YouTube")
    st.caption("Precisa do arquivo `client_secret.json` na pasta do programa (veja o LEIA-ME, Etapa 2).")
    if not (RAIZ / "client_secret.json").exists():
        st.warning("Falta o `client_secret.json`.")
    if st.button("🔗 Conectar / reconectar o YouTube", disabled=not (RAIZ / "client_secret.json").exists()):
        tok = RAIZ / "token.json"
        if tok.exists():
            tok.unlink()
        tarefas.iniciar("conectar", "Conectar YouTube", ["postar_youtube.py", "--autenticar"])
        st.info("Uma janela do navegador vai abrir para você autorizar. Depois, volte aqui.")

    st.subheader("Instagram")
    atual = ler(IG_CFG) if IG_CFG.exists() else {}
    with st.form("form_ig"):
        ig_id = st.text_input("ID da conta do Instagram", atual.get("ig_user_id", "") if "COLE" not in atual.get("ig_user_id", "COLE") else "")
        ig_tok = st.text_input("Token de acesso", type="password",
                               value=atual.get("access_token", "") if "COLE" not in atual.get("access_token", "COLE") else "")
        if st.form_submit_button("💾 Salvar Instagram"):
            salvar(IG_CFG, {"ig_user_id": ig_id.strip(), "access_token": ig_tok.strip(), "versao": atual.get("versao", "v26.0"),
                            "host": atual.get("host", "https://graph.facebook.com"),
                            "upload_host": atual.get("upload_host", "https://rupload.facebook.com")})
            st.success("Salvo.")
    if st.button("🔍 Descobrir o ID a partir do token", disabled=not IG_CFG.exists()):
        tarefas.iniciar("conectar", "Descobrir conta do Instagram", ["postar_instagram.py", "--descobrir-conta"])

    st.subheader("Twitch e Kick (chaves gratuitas para a Torre)")
    cfg = config_canais()
    with st.form("form_chaves"):
        c1, c2 = st.columns(2)
        tw_id = c1.text_input("Twitch Client ID", cfg["twitch"].get("client_id", ""))
        tw_sec = c2.text_input("Twitch Client Secret", cfg["twitch"].get("client_secret", ""), type="password")
        kk_id = c1.text_input("Kick Client ID", cfg["kick"].get("client_id", ""))
        kk_sec = c2.text_input("Kick Client Secret", cfg["kick"].get("client_secret", ""), type="password")
        if st.form_submit_button("💾 Salvar chaves"):
            cfg["twitch"] = {"client_id": tw_id.strip(), "client_secret": tw_sec.strip()}
            cfg["kick"] = {"client_id": kk_id.strip(), "client_secret": kk_sec.strip()}
            salvar(CANAIS, cfg)
            st.success("Salvo. Sem as chaves a Torre funciona, mas mais lenta (usa o yt-dlp).")
    painel_tarefas(["conectar"], "config")

    st.subheader("Pastas")
    c1, c2 = st.columns(2)
    if c1.button("📂 Abrir pasta do programa"):
        abrir_pasta(RAIZ)
    if c2.button("📂 Abrir pasta de logs"):
        abrir_pasta(RAIZ / "logs")


# =============================================================== página
estilo.topo()
aviso_canais_invalido()
t_inicio, t_novo, t_torre, t_aprov, t_pub, t_comp, t_conf = st.tabs(
    ["🏠 Início", "➕ Novo corte", "🗼 Torre", "✅ Aprovação", "📤 Publicar", "🎞️ Compilado", "⚙️ Configurações"])
with t_inicio:
    aba_inicio()
with t_novo:
    aba_novo()
with t_torre:
    aba_torre()
with t_aprov:
    aba_aprovacao()
with t_pub:
    aba_publicar()
with t_comp:
    aba_compilado()
with t_conf:
    aba_config()
estilo.rodape()
