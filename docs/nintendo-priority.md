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

## Acompanhamento nominal e consulta oficial complementar

- A lista em radar/nintendo_watch.py contém 31 jogos Switch específicos,
  com nomes de Mario, Donkey Kong, Zelda, Kirby, Metroid e outros.
- Cada execução registra os títulos presentes nas vitrines, os elegíveis,
  os rejeitados e os não encontrados. A tabela aparece no Summary
  do job monitor no GitHub Actions.
- Além das vitrines Vale o Jogo, o Radar faz uma tentativa de leitura
  de https://www.nintendo.com/pt-br/store/sales-and-deals/.
- radar/official_sales.py aceita somente um cartão de produto quando
  título monitorado, versão Switch, preços promocional/normal e URL
  oficial Nintendo pertencem ao mesmo cartão.
- Como a Nintendo pode renderizar preços por JavaScript, nem sempre
  esses valores estarão presentes no HTML. Nesse caso, a fonte retorna
  zero promoções verificadas, sem deduzir ou inventar preços.
- Jogos com oferta verificada diretamente na Nintendo não recebem nota
  fictícia de crítica: o e-mail exibe "Crítica não disponível".
- A lista é nominal, mas ainda não significa monitoramento individual
  de todos os 31 produtos. A busca continua dependendo das vitrines e
  dos itens efetivamente publicados na página oficial de ofertas.
- Ausência de oferta Nintendo não desativa as ofertas comuns e não
  muda o histórico por si só.
