"""
Posta no Instagram (Reels) os cortes APROVADOS, usando a API oficial da Meta.
ATENÇÃO: o Instagram publica na hora e como PÚBLICO (não existe "privado" na API).
Por isso o script pede confirmação antes de enviar, a menos que você use --sim.

Config: copie instagram_config.exemplo.json para instagram_config.json e preencha (veja o LEIA-ME).

Uso:
  python postar_instagram.py --teste         # só mostra o que seria postado
  python postar_instagram.py                 # pede confirmação e posta (máx. 5 por execução)
  python postar_instagram.py --max 2 --sim   # posta 2 sem perguntar
  python postar_instagram.py --renovar-token # renova o token (só para token do "login do Instagram", 60 dias)
  python postar_instagram.py --descobrir-conta  # mostra o ID e o @ das contas ligadas ao token
"""
import argparse
import json
import sys
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).parent
APROV = RAIZ / "clips" / "aprovados"
CONFIG = RAIZ / "instagram_config.json"


def carregar_config():
    if not CONFIG.exists():
        sys.exit("Falta o instagram_config.json (copie o instagram_config.exemplo.json e preencha).")
    c = json.loads(CONFIG.read_text(encoding="utf-8"))
    for k in ("ig_user_id", "access_token"):
        if not c.get(k) or "COLE_AQUI" in c[k]:
            sys.exit(f"Preencha '{k}' no instagram_config.json.")
    c.setdefault("versao", "v26.0")
    c.setdefault("host", "https://graph.instagram.com")
    c.setdefault("upload_host", "https://rupload.facebook.com")
    return c


def checar(resp, etapa):
    try:
        dados = resp.json()
    except Exception:
        dados = {"resposta": resp.text[:500]}
    if resp.status_code >= 400 or "error" in dados:
        raise RuntimeError(f"{etapa} falhou ({resp.status_code}): {json.dumps(dados, ensure_ascii=False)}")
    return dados


def descobrir_conta():
    """Lista as contas Instagram ligadas ao token (para achar o ig_user_id)."""
    if not CONFIG.exists():
        sys.exit("Falta o instagram_config.json com o access_token preenchido.")
    c = json.loads(CONFIG.read_text(encoding="utf-8"))
    host = c.get("host", "https://graph.facebook.com")
    ver = c.get("versao", "v26.0")
    cab = {"Authorization": f"Bearer {c.get('access_token', '')}"}
    if "graph.instagram.com" in host:
        dados = checar(requests.get(f"{host}/{ver}/me", headers=cab, params={"fields": "user_id,username"}), "Consultar conta")
        print(f"@{dados.get('username')}  ->  ig_user_id = {dados.get('user_id') or dados.get('id')}")
        return
    dados = checar(requests.get(f"{host}/{ver}/me/assigned_instagram_accounts", headers=cab,
                                params={"fields": "id,username"}), "Consultar contas")
    contas = dados.get("data", [])
    if not contas:
        print("Nenhuma conta Instagram ligada a este token. Resposta:", json.dumps(dados, ensure_ascii=False))
    for c_ in contas:
        print(f"@{c_.get('username')}  ->  ig_user_id = {c_.get('id')}")


def legenda(meta):
    partes = [meta["titulo"], ""]
    if meta.get("credito"):
        partes.append(f"Corte da live de {meta['credito']}. Créditos ao criador original.")
        partes.append("")
    tags = meta.get("hashtags", "#GTA6 #GTAVI").replace("#shorts", "").strip()
    partes.append(tags + " #reels")
    return "\n".join(partes)[:2200]


def publicar_reel(cfg, video, texto):
    base = f"{cfg['host']}/{cfg['versao']}/{cfg['ig_user_id']}"
    cab = {"Authorization": f"Bearer {cfg['access_token']}"}

    # 1) cria o container (upload resumível)
    r = requests.post(f"{base}/media", headers=cab, json={
        "media_type": "REELS", "upload_type": "resumable", "caption": texto, "share_to_feed": True})
    container = checar(r, "Criar container")["id"]

    # 2) envia o arquivo
    tamanho = Path(video).stat().st_size
    with open(video, "rb") as f:
        r = requests.post(
            f"{cfg['upload_host']}/ig-api-upload/{cfg['versao']}/{container}",
            headers={"Authorization": f"OAuth {cfg['access_token']}", "offset": "0", "file_size": str(tamanho)},
            data=f)
    checar(r, "Enviar vídeo")

    # 3) espera o Instagram processar
    for _ in range(60):
        r = requests.get(f"{cfg['host']}/{cfg['versao']}/{container}", headers=cab,
                         params={"fields": "status_code,status"})
        st = checar(r, "Consultar status")
        codigo = st.get("status_code")
        if codigo == "FINISHED":
            break
        if codigo in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Processamento falhou: {st}")
        time.sleep(5)
    else:
        raise RuntimeError("Tempo esgotado esperando o processamento.")

    # 4) publica
    r = requests.post(f"{base}/media_publish", headers=cab, json={"creation_id": container})
    media_id = checar(r, "Publicar")["id"]

    r = requests.get(f"{cfg['host']}/{cfg['versao']}/{media_id}", headers=cab, params={"fields": "permalink"})
    link = r.json().get("permalink", "") if r.ok else ""
    return media_id, link


def renovar_token(cfg):
    r = requests.get(f"{cfg['host']}/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": cfg["access_token"]})
    dados = checar(r, "Renovar token")
    cfg["access_token"] = dados["access_token"]
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Token renovado. Válido por ~{dados.get('expires_in', 0) // 86400} dias.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teste", action="store_true")
    ap.add_argument("--sim", action="store_true", help="não pede confirmação")
    ap.add_argument("--max", type=int, default=5)
    ap.add_argument("--renovar-token", action="store_true")
    ap.add_argument("--descobrir-conta", action="store_true")
    a = ap.parse_args()

    if a.descobrir_conta:
        return descobrir_conta()

    if a.teste:
        cfg = {}
    else:
        cfg = carregar_config()
    if a.renovar_token:
        return renovar_token(cfg)

    pastas = []
    for mp in sorted(APROV.glob("*/meta.json")):
        meta = json.loads(mp.read_text(encoding="utf-8"))
        if not meta.get("instagram_url") and (mp.parent / "video.mp4").exists():
            pastas.append((mp, meta))
    pastas = pastas[: a.max]
    if not pastas:
        return print("Nenhum corte aprovado pendente para o Instagram.")

    print(f"{len(pastas)} corte(s) para o Instagram:")
    for mp, meta in pastas:
        print(f"- {mp.parent.name}: {meta['titulo']}")
        if a.teste:
            print("    " + legenda(meta).replace("\n", "\n    "))
    if a.teste:
        return
    if not a.sim and input("Postar como PÚBLICO agora? (s/N) ").strip().lower() != "s":
        return print("Cancelado.")

    for mp, meta in pastas:
        print(f"> {mp.parent.name}")
        try:
            media_id, link = publicar_reel(cfg, mp.parent / "video.mp4", legenda(meta))
        except Exception as e:
            print(f"   ERRO: {e}")
            if "rate" in str(e).lower() or "2207042" in str(e):
                return print("Limite de publicação atingido. Tente mais tarde.")
            continue
        meta["instagram_id"], meta["instagram_url"] = media_id, link or media_id
        mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"   postado: {link or media_id}")
        time.sleep(10)


if __name__ == "__main__":
    main()
