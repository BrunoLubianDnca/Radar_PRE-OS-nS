# Auditoria da coleta e popularidade — 05/11/2026

## Situação inicial
- Duas vitrines: 28 links cada, 36 candidatos únicos.
- 18/36 páginas tiveram ofertas interpretadas; 18/36 não forneceram
  os dados exigidos pela extração conservadora.
- Sete jogos cumpriram os filtros naquela execução.
- A página de Switch anuncia mais de 2.400 jogos, mas o HTML de listagem
  expõe a primeira seleção (aprox. 28-30 títulos). A paginação aparece
  como botões JavaScript. **Não é correto afirmar cobertura do catálogo.**

## Decisões de segurança
- Uma terceira vitrine pública de jogos bem avaliados foi adicionada:
  https://valeojogo.com.br/promocoes/bem-avaliados/
  Ela inclui várias plataformas; só entram ofertas com preço verificado
  na entrada digital Nintendo eShop e link HTTPS oficial Nintendo.
- O algoritmo segue páginas seguintes somente quando existirem URLs
  de paginação explícitas em links `a[href]` da mesma vitrine.
  Botões JavaScript sem href **não** são considerados páginas rastreáveis.
- Limite configurado de três páginas por vitrine e pequena pausa entre
  requisições; nenhuma URL de API interna foi inventada.
- Algumas páginas de detalhe servem apenas um resumo inicial
  ("Carregando o histórico de preço, as lojas e a comunidade...").
  Sem preço antigo, oferta digital e link oficial confirmados, a oferta
  permanece descartada. A coleta não fabrica preço usando porcentagem.
- Um segundo formato **explícito** de desconto na oferta eShop é aceito:
  `-75% R$ 22,49 de R$ 89,99`. A diferença matemática precisa bater.

## Ranking editorial verificável
- `radar/popular.py` documenta a lista editorial de franquias e a fórmula
  `popularity_evidence` de 0 a 100.
- Evidências: presença na lista editorial, nota da crítica e quantidade/
  percentual de avaliações informados pela fonte.
- Sem valores estimados de vendas, downloads ou popularidade oficial.
- A ordenação escolhe as ofertas mais relevantes para os até 12 espaços
  de e-mail. O template visual existente continua exibindo os selecionados
  por desconto, sem modificações no arquivo.
- O ranking **não relaxa** os critérios existentes de aprovação, preço,
  desconto ou o controle de alertas do estado.

## Limitações e próximos passos
- O total de títulos observados ainda depende das vitrines HTML acessíveis;
  a paginação JS não foi automatizada.
- A qualidade do ranking depende da cobertura das avaliações da fonte.
  A ausência de avaliações significa "não informado", não 0% de aprovação.
- Para chegar ao catálogo completo, é necessária uma fonte oficial ou
  mecanismo publicamente documentado/permitido com URLs de paginação
  verificáveis, respeitando limites de acesso.
- Validar a execução de GitHub Actions após a alteração; testes unitários
  cobrem a descoberta explícita, cálculos, rejeições e classificação.
