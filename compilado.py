"""Monta o compilado (~15 min) com os cortes aprovados + capítulos para a descrição do YouTube."""
import json
import subprocess
import time
from pathlib import Path

RAIZ = Path(__file__).parent
APROV = RAIZ / "clips" / "aprovados"
SAIDA = RAIZ / "compilados"


def main():
    itens = []
    for meta_path in APROV.glob("*/meta.json"):
        pasta = meta_path.parent
        if (pasta / "horizontal.mp4").exists():
            itens.append((json.loads(meta_path.read_text(encoding="utf-8")), pasta))
    if not itens:
        raise SystemExit("Nenhum corte aprovado com versão horizontal.")

    # melhor no início (gancho), segundo melhor no final, o resto em ordem crescente (crescendo)
    itens.sort(key=lambda x: x[0]["nota"], reverse=True)
    if len(itens) > 2:
        meio = sorted(itens[2:], key=lambda x: x[0]["nota"])
        itens = [itens[0]] + meio + [itens[1]]

    # limite ~15 min: 30 clipes de 30s
    itens = itens[:30]

    SAIDA.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    lista = SAIDA / f"lista_{stamp}.txt"
    lista.write_text("".join(f"file '{(p / 'horizontal.mp4').resolve().as_posix()}'\n" for _, p in itens), encoding="utf-8")

    destino = SAIDA / f"compilado_{stamp}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lista), "-c", "copy", str(destino)], check=True)

    # capítulos + créditos para colar na descrição
    linhas, t, creditos = [], 0, []
    for meta, _ in itens:
        m, s = divmod(t, 60)
        linhas.append(f"{m:02d}:{s:02d} {meta['titulo']}" + (f" ({meta['credito']})" if meta["credito"] else ""))
        if meta["credito"] and meta["credito"] not in creditos:
            creditos.append(meta["credito"])
        t += meta["duracao"]
    desc = "\n".join(linhas) + "\n\nCréditos: " + ", ".join(creditos) + "\n#GTA6 #GTAVI"
    (SAIDA / f"compilado_{stamp}_descricao.txt").write_text(desc, encoding="utf-8")
    print(f"Compilado pronto: {destino}  ({len(itens)} cortes, {t // 60} min {t % 60} s)")


if __name__ == "__main__":
    main()
