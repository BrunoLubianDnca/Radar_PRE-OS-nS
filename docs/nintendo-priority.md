# Alertas Nintendo em destaque — 06/11/2026

O Radar continua alertando **somente jogos digitais para Nintendo Switch pela Nintendo eShop**, com os mesmos filtros dos jogos comuns (até R$100, a partir de 30%, crítica 80, jogadores 85% quando amostra >=200).

## Seleção especial Nintendo
- `nintendo_priority_enabled: true`
- `nintendo_min_discount_percent: 15`
- `nintendo_max_price_brl: 250`
- Nota mínima de crítica e avaliação de jogadores **continuam iguais**.
- As ofertas de franquias selecionadas aparecem primeiro na seleção do e-mail, identificadas como **Nintendo em destaque**.
- As séries contempladas incluem Super Mario, Mario Kart, Mario Party, Paper Mario, Donkey Kong, Zelda, Kirby, Metroid, Splatoon, Pikmin, Animal Crossing, Fire Emblem, Luigi's Mansion, Pokémon e outras séries curadas.
- Mario + Rabbids, Mario & Sonic, Pokémon UNITE e edições explicitamente *Switch 2 Edition* **não** recebem os limites especiais. Os jogos de parceiros ainda podem entrar pelas regras comuns.
- A identificação é **curadoria por título/franquia**, e **não verificação automática do campo editora/publicadora**. O e-mail não alega uma editora não verificada.

## Fontes e limitações
- A quarta vitrine é `https://valeojogo.com.br/promocoes/nintendo/`. Ela inclui Switch 2; o parser exige a entrada `Switch digital Nintendo eShop`, desconto matematicamente consistente e URL oficial Nintendo.
- A seleção especial **não garante busca de todo catálogo**. As vitrines públicas exibem parte dos jogos; a paginação JS ainda não possui mecanismo público confirmado pelo projeto. Um título não aparecer na vitrine significa que o Radar pode não o detectar mesmo que esteja em promoção.
- A página oficial de descontos (https://www.nintendo.com/pt-br/store/sales-and-deals/) pode ser consultada manualmente. Não foi adicionada como fonte automática sem parser verificado e preços em reais vinculados a ofertas.
- O monitor não gera preço, desconto ou link caso faltem dados suficientes. Ele ignora o jogo.
- O histórico `data/state.json` e as configurações SMTP não foram alterados. Nenhum disparo manual ou `send_initial` foi realizado.
