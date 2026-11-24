"""
Posta no YouTube os cortes APROVADOS (Shorts) e o compilado.

Primeira vez: abre o navegador para você autorizar o canal (gera token.json).
Requer client_secret.json (veja o LEIA-ME).

Uso:
  python postar_youtube.py --teste                      # só mostra o que seria postado
  python postar_youtube.py                              # posta Shorts aprovados (máx. 6/dia) como PRIVADO
  python postar_youtube.py --publico                    # posta como público (só funciona após auditoria da API)
  python postar_youtube.py --compilado compilados\\compilado_XXXX.mp4 --titulo "TÍTULO"
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).parent
APROV = RAIZ / "clips" / "aprovados"
POSTADOS = RAIZ / "clips" / "postados"
ESCOPOS = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",   # já pedido agora para o analytics (etapa 4)
]


def autenticar():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token = RAIZ / "token.json"
    cred = Credentials.from_authorized_user_file(str(token), ESCOPOS) if token.exists() else None
    if not cred or not cred.valid:
        if cred and cred.expired and cred.refresh_token:
            try:
                cred.refresh(Request())
            except Exception:
                cred = None
        if not cred or not cred.valid:
            segredo = RAIZ / "client_secret.json"
            if not segredo.exists():
                sys.exit("Faltou o client_secret.json. Veja o passo a passo no LEIA-ME.")
            cred = InstalledAppFlow.from_client_secrets_file(str(segredo), ESCOPOS).run_local_server(port=0)
        token.write_text(cred.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=cred)


def enviar(yt, arquivo, titulo, descricao, tags, privacidade):
    from googleapiclient.http import MediaFileUpload
    corpo = {
        "snippet": {
            "title": titulo[:100],
            "description": descricao[:4900],
            "tags": tags,
            "categoryId": "20",          # Games
        },
        "status": {"privacyStatus": privacidade, "selfDeclaredMadeForKids": False},
    }
    midia = MediaFileUpload(str(arquivo), chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=corpo, media_body=midia)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"      enviando... {int(status.progress() * 100)}%")
    return resp["id"]


def descricao_short(meta):
    linhas = [meta["titulo"], ""]
    if meta.get("credito"):
        linhas.append(f"Corte da live de {meta['credito']}. Todos os créditos ao criador.")
    if str(meta.get("fonte", "")).startswith("http"):
        linhas.append(f"Live original: {meta['fonte']}")
    linhas += ["", meta.get("hashtags", "#GTA6 #shorts")]
    if "#shorts" not in " ".join(linhas).lower():
        linhas.append("#shorts")
    return "\n".join(linhas)


def tags_de(meta):
    return [h.strip("#") for h in meta.get("hashtags", "").split() if h.startswith("#")]


def postar_shorts(a):
    pastas = sorted(p.parent for p in APROV.glob("*/meta.json")
                    if not json.loads(p.read_text(encoding="utf-8")).get("youtube_id"))
    if not pastas:
        print("Nenhum corte aprovado para postar.")
        return
    pastas = pastas[: a.max]
    yt = None if a.teste else autenticar()
    privacidade = "public" if a.publico else "private"

    for pasta in pastas:
        meta = json.loads((pasta / "meta.json").read_text(encoding="utf-8"))
        titulo = meta["titulo"] if "#shorts" in meta["titulo"].lower() else f"{meta['titulo']} #shorts"
        print(f"- {pasta.name}: {titulo}  [{privacidade}]")
        if a.teste:
            print(descricao_short(meta).replace("\n", "\n    "))
            continue
        try:
            vid = enviar(yt, pasta / "video.mp4", titulo, descricao_short(meta), tags_de(meta), privacidade)
        except Exception as e:
            if "quotaExceeded" in str(e) or "uploadLimitExceeded" in str(e):
                print("Cota diária do YouTube atingida. Continue amanhã (os restantes seguem aprovados).")
                return
            print(f"      ERRO: {e}")
            continue
        meta["youtube_id"] = vid
        meta["youtube_url"] = f"https://youtube.com/shorts/{vid}"
        (pasta / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"      postado: {meta['youtube_url']}")


def postar_compilado(a):
    arq = Path(a.compilado)
    desc_arq = arq.with_name(arq.stem + "_descricao.txt")
    descricao = desc_arq.read_text(encoding="utf-8") if desc_arq.exists() else "#GTA6 #GTAVI"
    titulo = a.titulo or "Os melhores momentos do lançamento do GTA 6 🔥"
    privacidade = "public" if a.publico else "private"
    print(f"Compilado: {titulo}  [{privacidade}]")
    if a.teste:
        print(descricao)
        return
    vid = enviar(autenticar(), arq, titulo, descricao, ["GTA6", "GTAVI", "compilado"], privacidade)
    print(f"Postado: https://youtube.com/watch?v={vid}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teste", action="store_true", help="não envia nada, só mostra")
    ap.add_argument("--publico", action="store_true", help="publica como público (padrão: privado)")
    ap.add_argument("--max", type=int, default=6, help="máximo de Shorts por execução (cota ≈ 6/dia)")
    ap.add_argument("--compilado", help="caminho do compilado .mp4 para postar")
    ap.add_argument("--titulo", help="título do compilado")
    ap.add_argument("--autenticar", action="store_true", help="só conecta a conta do YouTube e mostra o canal")
    a = ap.parse_args()
    if a.autenticar:
        yt = autenticar()
        canais = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
        for ch in canais:
            print(f"Conectado ao canal: {ch['snippet']['title']}")
        if not canais:
            print("Conectado, mas nenhum canal foi encontrado nessa conta.")
        return
    postar_compilado(a) if a.compilado else postar_shorts(a)


if __name__ == "__main__":
    main()
