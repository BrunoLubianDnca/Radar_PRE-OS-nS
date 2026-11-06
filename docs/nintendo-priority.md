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

## Busca nominal com preços regionais Nintendo BR

O Radar agora faz consulta individual aos 31 jogos monitorados através de
uma única busca multiquery no catálogo Nintendo Brasil (Algolia
ncom_game_pt_br). A busca não fica limitada aos 28 jogos de uma vitrine.

Para cada resultado com nome exato, NSUID de 14 dígitos e URL de produto
oficial da Nintendo (edição Nintendo Switch), uma chamada à API pública
api.ec.nintendo.com/v1/price consulta country=BR. Só produz alerta quando:
- o ID corresponde exatamente ao título acompanhado e há URL do produto;
- a resposta da Nintendo indica country BR e valores em moeda BRL;
- existe discount_price menor que regular_price;
- as datas de vigência, quando informadas, abrangem o momento da consulta;
- as regras especiais Nintendo (até R$250, a partir de 15%) são satisfeitas.

Nenhuma edição Switch 2 Edition ou preço de outra região é usado.
Um campo de crítica ausente na API oficial não é substituído por nota falsa.

Ambas as APIs públicas são não documentadas e podem alterar formato, chave
de busca ou disponibilidade. Falha não cria oferta falsa nem impede os
alertas comuns; o job mostrará quantos títulos e preços foram resolvidos.
Esta integração ainda precisa de confirmação da primeira execução
externa no GitHub Actions para validar a estrutura de resposta ao vivo.

Fontes técnicas:
- https://github.com/okou-ai/okou/issues/20611
- https://opentherank.com/pt/data-sources/
- https://favna.github.io/nintendo-switch-eshop/api/interfaces/gameus/

## Fonte oficial prioritária

Em todas as execuções de coleta (inclusive prévia), o Radar consulta **primeiro** https://www.nintendo.com/pt-br/store/sales-and-deals/. O HTML é consultado uma única vez por ciclo e, se tiver cartões completos com preço e link oficial, essas ofertas são aproveitadas. O catálogo regional e a API de preços Nintendo BR complementam a identificação e a confirmação dos preços. Vitrines de terceiros são fontes auxiliares, não substituem preço verificável da eShop. Se a página oficial não apresentar os dados no HTML (carregamento JS), o log informa isso e os alertas comuns permanecem ativos; consultar a página não garante descoberta de todos os jogos. A execução de teste SMTP --test-email não consulta jogos por definição.

## Correção da fonte oficial — novembro de 2026

Log investigado: página oficial sales-and-deals retornava HTML com cerca
de 1,39 milhão de caracteres, porém parser gerava zero ofertas; o índice
ncom_game_pt_br também retornava zero jogos monitorados.

Correções:
- Buscar a seleção Deals no índice store_all_products_pt_br, de catálogo
  atual da Nintendo Brasil (fonte de apoio à página sales-and-deals).
- Consultar até três páginas de resultados para descoberta de produtos
  digitais conhecidos do Switch 1, além dos 31 títulos acompanhados.
- Confirmar o desconto pela API api.ec.nintendo.com/v1/price com
  country=BR, valor em BRL, NSUID, preço cheio e promoção vigente.
- Aceitar raw_value além de amount e não exigir campo country na resposta
  quando a requisição foi explicitamente feita para BR; país divergente
  continua sendo rejeitado.
- Aceitar jogos populares de terceiros com preço oficial validado, mas
  sem inventar notas de crítica.
- Mostrar no log quantos itens da seleção Deals chegaram, seus campos
  disponíveis quando houver zero correspondências e quantos descontos
  brasileiros foram efetivamente confirmados.
- O modo automático só envia alertas inéditos/queda de preço;
  preview_email=true permite ver a seleção atual sem mudar histórico.

A confirmação de que esses endpoints e campos continuam respondendo
no ambiente do GitHub requer execução externa. Testes locais simulados
não comprovam a extração ao vivo.
