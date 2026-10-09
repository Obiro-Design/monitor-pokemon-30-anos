# Monitor Pokémon Celebração 30 Anos

Robô gratuito (GitHub Actions) que confere a **SP Kids** e a **Copag B2B** a cada ~10 min e manda aviso no celular pelo **ntfy**.

**Ele nunca compra nada.** Quando um produto libera, o aviso traz botões de "colocar no carrinho" já com a quantidade certa. Você toca, confere o carrinho e finaliza.

## O que ele vigia
| Onde | O quê | Aviso |
|---|---|---|
| SP Kids | Treinador Avançado (2003), Box Fichário (1997), Box EX (1982), Blister Duplo (1988), Blister Triplo (1992), Box Pôster (2001) | 🚨 prioridade máxima quando fica comprável (repete até 6x, a cada ~10 min, enquanto seguir liberado) |
| SP Kids | Produto novo com "30 anos", "celebração" ou "aniversário" (recadastro com outro número) | 🟡 |
| SP Kids | Produto que sai/volta ao site, muda limite ou preço | 🟡 |
| Copag | Produto novo com 30 anos, Celebração, Fichário, Pôster, Box EX, Pikachu etc. | 🟡 só link, nunca carrinho |
| Robô | Sinal de vida todo dia ~9h; alerta se não conseguir acessar o site 3x seguidas | ✅ / ⚠️ |

## Quantidades (regra do Bruno)
- Limite do Treinador = 1 → 1 Treinador + 2 Fichários
- Limite = 2 → 2 Treinadores + 2 Fichários
- Limite > 2 → até 5 Treinadores + 1 Fichário
- Nunca passa do limite que a loja informa (o Fichário hoje é 1 por CNPJ). Demais itens: 1.

## Como mexer
- **Rodar agora:** aba **Actions** → *Monitor Pokémon 30 anos* → **Run workflow**.
- **Pausar:** aba **Actions** → *Monitor Pokémon 30 anos* → botão **···** → **Disable workflow**.
- **Canal de aviso:** segredo `NTFY_TOPIC` (Settings → Secrets and variables → Actions).
- Estado da última checagem: `state.json`.

Obs.: o GitHub desliga agendamentos de repositórios sem atividade por 60 dias; o commit diário do `state.json` evita isso.
