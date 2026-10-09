#!/usr/bin/env python3
"""Monitor Pokémon Celebração 30 Anos — SP Kids + Copag.

Roda no GitHub Actions a cada ~10 min. Só usa a biblioteca padrão do Python.
NUNCA finaliza compra: só manda aviso (ntfy) com links de "colocar no carrinho".
O estado da última checagem fica em state.json (salvo de volta no repositório).
"""
import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

SPK = "https://spkidsdistribuidora.com.br"
COPAG = "https://www.b2b.copagloja.com.br"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
DRY_RUN = os.environ.get("DRY_RUN") == "1"
BRT = timezone(timedelta(hours=-3))

# Produtos acompanhados (id SP Kids -> nome curto). Ordem = prioridade.
PRODUTOS = {
    2003: "Treinador Avançado",
    1997: "Box Fichário",
    1982: "Box EX",
    1988: "Blister Duplo",
    1992: "Blister Triplo",
    2001: "Box Pôster",
}
TREINADOR, FICHARIO = 2003, 1997

PALAVRAS = ["30 anos", "celebra", "aniversari", "fichario", "poster",
            "blister duplo", "box ex", "mini lata", "pikachu"]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")


def norm(txt):
    txt = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode()
    return " ".join(txt.lower().replace("-", " ").split())


def tem_palavra(txt):
    t = norm(txt)
    return any(p in t for p in PALAVRAS)


def get_json(url, tentativas=2):
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}_={int(time.time() * 1000)}"  # fura cache
    ultimo = None
    for i in range(tentativas):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept": "application/json",
            "Cache-Control": "no-cache", "Pragma": "no-cache"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.status, json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return e.code, None
            ultimo = e
        except Exception as e:  # rede, timeout, JSON inválido
            ultimo = e
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url} -> {ultimo}")


def add_to_cart(pid, qtd):
    return f"{SPK}/?add-to-cart={pid}&quantity={qtd}"


def quantidades(liberados, maximos):
    """Regra do Bruno. maximos[pid] = limite do carrinho informado pela loja (ou None)."""
    q = {}
    lim_fich = maximos.get(FICHARIO) or 1
    if TREINADOR in liberados:
        lim = maximos.get(TREINADOR) or 1
        if lim <= 1:
            q[TREINADOR], pastas = 1, 2
        elif lim == 2:
            q[TREINADOR], pastas = 2, 2
        else:
            q[TREINADOR], pastas = min(5, lim), 1
        if FICHARIO in liberados:
            q[FICHARIO] = max(1, min(pastas, lim_fich))
    elif FICHARIO in liberados:
        q[FICHARIO] = max(1, min(2, lim_fich))
    for pid in liberados:
        q.setdefault(pid, 1)
    return q


def ntfy(titulo, msg, prioridade=3, tags="", click=None, acoes=None):
    print(f"[AVISO p{prioridade}] {titulo}\n{msg}\n")
    if DRY_RUN or not NTFY_TOPIC:
        if not NTFY_TOPIC:
            print("(NTFY_TOPIC vazio: aviso não enviado)")
        return
    corpo = {"topic": NTFY_TOPIC, "title": titulo, "message": msg,
             "priority": prioridade}
    if tags:
        corpo["tags"] = [t for t in tags.split(",") if t]
    if click:
        corpo["click"] = click
    if acoes:
        corpo["actions"] = [{"action": "view", "label": l, "url": u, "clear": False}
                            for l, u in acoes[:3]]
    for i in range(3):
        try:
            req = urllib.request.Request(
                "https://ntfy.sh/", data=json.dumps(corpo).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=20).read()
            return
        except Exception as e:
            print(f"ntfy falhou ({e}), tentativa {i + 1}")
            time.sleep(5 * (i + 1))


# ---------------------------------------------------------------- checagens
def checar_produtos():
    atual = {}
    for pid in PRODUTOS:
        status, d = get_json(f"{SPK}/wp-json/wc/store/v1/products/{pid}")
        if d is None:
            atual[str(pid)] = {"existe": False}
            continue
        atual[str(pid)] = {
            "existe": True,
            "nome": d.get("name"),
            "em_estoque": bool(d.get("is_in_stock")),
            "compravel": bool(d.get("is_purchasable")),
            "maximo": (d.get("add_to_cart") or {}).get("maximum"),
            "preco": (d.get("prices") or {}).get("price"),
            "link": d.get("permalink"),
        }
    return atual


def checar_busca_spk():
    vistos = {}
    for termo in ("30 anos", "celebracao", "aniversario"):
        q = urllib.parse.quote(termo)
        _, lista = get_json(f"{SPK}/wp-json/wp/v2/product?search={q}&per_page=50"
                            f"&_fields=id,slug,modified,class_list,link")
        for p in lista or []:
            vistos[str(p["id"])] = {"slug": p.get("slug"), "link": p.get("link"),
                                    "instock": "instock" in (p.get("class_list") or [])}
    return vistos


def checar_copag():
    nomes = {}
    for termo in ("30 anos", "pokemon", "celebracao"):
        q = urllib.parse.quote(termo)
        _, d = get_json(f"{COPAG}/api/io/_v/api/intelligent-search/product_search/"
                        f"?query={q}&count=50&hideUnavailableItems=false")
        for p in (d or {}).get("products", []):
            nome = p.get("productName") or ""
            link = p.get("link") or ""
            if link.startswith("/"):
                link = COPAG + link
            nomes[nome] = link
    return nomes


# ---------------------------------------------------------------- principal
def main():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            est = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        est = {}
    primeira_vez = not est
    agora = datetime.now(BRT)
    est.setdefault("erros", {})
    resumo = []

    # ---- SP Kids: produtos acompanhados
    try:
        prods = checar_produtos()
        if est["erros"].get("spk", 0) >= 3:
            ntfy("SP Kids voltou a responder", "O monitor voltou a ler a SP Kids.", 2)
        est["erros"]["spk"] = 0
    except Exception as e:
        prods = None
        n = est["erros"].get("spk", 0) + 1
        est["erros"]["spk"] = n
        print(f"ERRO SP Kids: {e}")
        if n == 3:
            ntfy("⚠️ Monitor sem acesso à SP Kids",
                 f"3 checagens seguidas falharam. Último erro: {str(e)[:200]}", 4, "warning")

    if prods is not None:
        antes = est.get("produtos", {})
        liberados, maximos, mudancas = [], {}, []
        for pid, nome in PRODUTOS.items():
            a, n = antes.get(str(pid), {}), prods[str(pid)]
            maximos[pid] = n.get("maximo")
            ok_agora = n.get("existe") and n.get("em_estoque") and n.get("compravel")
            ok_antes = a.get("existe") and a.get("em_estoque") and a.get("compravel")
            if ok_agora:
                liberados.append(pid)
            if not primeira_vez and a and not ok_agora and not ok_antes:
                if a.get("existe") != n.get("existe"):
                    mudancas.append(f"{nome}: {'voltou ao site' if n.get('existe') else 'saiu do site'}")
                elif a.get("maximo") != n.get("maximo") or a.get("preco") != n.get("preco"):
                    mudancas.append(f"{nome}: limite/preço mudou")
            resumo.append(f"{nome}: {'LIBERADO' if ok_agora else ('fora' if n.get('existe') else 'sumido')}")

        # aviso de liberação: insiste enquanto estiver liberado (até 6 vezes por liberação)
        novos = [p for p in liberados if not (antes.get(str(p), {}).get("em_estoque")
                                                and antes.get(str(p), {}).get("compravel"))]
        avisos = est.get("avisos_liberacao", 0)
        if liberados and (novos or avisos < 6):
            est["avisos_liberacao"] = 0 if novos else avisos
            est["avisos_liberacao"] += 1
            qtd = quantidades(liberados, maximos)
            ordem = [p for p in PRODUTOS if p in qtd]
            linhas = [f"{PRODUTOS[p]} x{qtd[p]}: {add_to_cart(p, qtd[p])}" for p in ordem]
            ntfy(f"🚨 LIBEROU SP Kids — {', '.join(PRODUTOS[p] for p in ordem)}",
                 "Toque num botão para pôr no carrinho (logado). Depois confira em "
                 f"{SPK}/carrinho/ e FINALIZE VOCÊ.\n\n" + "\n".join(linhas),
                 5, "rotating_light", click=add_to_cart(ordem[0], qtd[ordem[0]]),
                 acoes=[(f"{PRODUTOS[p][:18]} x{qtd[p]}", add_to_cart(p, qtd[p])) for p in ordem])
        elif not liberados:
            est["avisos_liberacao"] = 0

        if mudancas:
            ntfy("🟡 SP Kids mudou algo na coleção 30 anos", "\n".join(mudancas), 3, "eyes",
                 click=f"{SPK}/carrinho/")
        est["produtos"] = prods

    # ---- SP Kids: produto novo da coleção (outro número)
    try:
        busca = checar_busca_spk()
        conhecidos = set(est.get("busca_spk", {}))
        novos = [k for k in busca if k not in conhecidos and int(k) not in PRODUTOS]
        if novos and not primeira_vez:
            ntfy("🟡 Produto NOVO 30 anos na SP Kids",
                 "\n".join(f"{busca[k]['slug']} (id {k}) {busca[k]['link']}" for k in novos),
                 4, "eyes", click=busca[novos[0]]["link"])
        est["busca_spk"] = {**est.get("busca_spk", {}), **busca}
    except Exception as e:
        print(f"ERRO busca SP Kids: {e}")

    # ---- Copag (só aviso com link, nunca carrinho)
    try:
        nomes = checar_copag()
        conhecidos = set(est.get("copag", []))
        novos = [n for n in nomes if n not in conhecidos and tem_palavra(n)]
        if novos and not primeira_vez:
            ntfy("🟡 Copag: produto novo que pode ser 30 anos",
                 "\n".join(f"{n}: {nomes[n]}" for n in novos), 4, "eyes",
                 click=nomes[novos[0]] or None)
        est["copag"] = sorted(conhecidos | set(nomes))
        resumo.append(f"Copag: {len(novos)} novo(s) relevante(s)")
        est["erros"]["copag"] = 0
    except Exception as e:
        n = est["erros"].get("copag", 0) + 1
        est["erros"]["copag"] = n
        print(f"ERRO Copag: {e}")
        if n == 6:
            ntfy("⚠️ Monitor sem acesso à Copag", str(e)[:200], 3, "warning")

    # ---- sinal de vida diário (~9h) para silêncio não parecer "tudo certo" quando parou
    hoje = agora.strftime("%Y-%m-%d")
    if agora.hour >= 9 and est.get("ultimo_ok") != hoje:
        est["ultimo_ok"] = hoje
        if not primeira_vez:
            ntfy("✅ Monitor 30 anos funcionando",
                 "Checagem de hoje OK.\n" + "\n".join(resumo), 1, "white_check_mark")

    if primeira_vez:
        ntfy("✅ Monitor 30 anos ligado", "Primeira checagem feita.\n" + "\n".join(resumo),
             2, "white_check_mark")

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(est, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"{agora.strftime('%d/%m %H:%M')} BRT — " + " · ".join(resumo))


if __name__ == "__main__":
    sys.exit(main())
