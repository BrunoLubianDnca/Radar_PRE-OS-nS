# Radar Nintendo Switch — MVP

Monitor pessoal de promoções **digitais da Nintendo eShop Brasil**, em BRL, com **preço até R$ 100**, **desconto mínimo de 30%** e **jogos populares e bem avaliados**. Executa a cada 3 horas pelo GitHub Actions e avisa por e-mail apenas sobre novidades ou reduções adicionais.

## Fonte e cobertura

- Descoberta: https://valeojogo.com.br/promocoes/switch/
- Verificação: página individual de cada jogo, seção **Switch digital — Nintendo eShop**, com link para a Nintendo.
- Critérios: crítica >=80/100, avaliação positiva dos jogadores >=85% e >=200 análises, todos necessários.
- **Limitação importante:** a versão 1 monitora os jogos da **primeira página** da vitrine, não os milhares de jogos do catálogo. O site agrega notas de diferentes fontes (IGDB e Steam); avaliações Steam não equivalem a avaliações da versão Switch.
- A origem declara atualizar preços diariamente: executar a cada 3 horas **não garante** mudanças a cada 3 horas.
- Dependemos de HTML de terceiro, sujeito a alterações e bloqueio de acesso. Não há API pública contratada, nem garantia de uptime. Consulte as políticas do site antes de publicar o monitor.
- Não consulta mídia física nem marketplaces; ignora ofertas sem evidência de preço digital da eShop e sem link Nintendo.

## Configuração rápida

1. Crie um **repositório privado** no GitHub, faça upload do conteúdo deste projeto e mantenha a branch principal como `main` (ou ajuste o nome da branch nas configurações).
2. Vá em **Settings → Secrets and variables → Actions → New repository secret**, e cadastre:

   | Secret | Exemplo Gmail |
   |---|---|
   | `SMTP_HOST` | `smtp.gmail.com` |
   | `SMTP_PORT` | `465` |
   | `SMTP_USER` | `seuemail@gmail.com` |
   | `SMTP_PASSWORD` | senha de app do Gmail (não a senha da conta) |
   | `EMAIL_TO` | destinatario@gmail.com |
   | `EMAIL_FROM` | opcional; deixe ausente para usar SMTP_USER |

   No Gmail, a senha de aplicativo geralmente requer verificação em duas etapas e disponibilidade da opção em sua conta. Nunca versionar segredos.

3. Em **Settings → Actions → General → Workflow permissions**, configure `Read and write permissions`, pois o workflow registra o estado em `data/state.json` com o `GITHUB_TOKEN`. Em alguns repositórios, as políticas da organização podem impedir a alteração.
4. Em **Actions → Radar Nintendo Switch → Run workflow**, execute manualmente. Por padrão a primeira execução **estabelece uma linha de base e não dispara um e-mail com ofertas antigas**. Se desejar receber todas as elegíveis desde o primeiro momento, marque a opção `send_initial` na primeira execução.
5. Depois, o agendamento `17 */3 * * *` executa aproximadamente de 3 em 3 horas (UTC). O GitHub pode atrasar execuções agendadas; o monitor **não é tempo real**.
6. Confira o log em Actions. Se falhar a leitura, o job mostra erro e preserva o histórico. O e-mail também não é enviado nessa condição.

## Teste local

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
pytest -q
python -m radar.main --dry-run
```

`--dry-run` lê a fonte real e imprime alertas, sem enviar e-mail e sem alterar o histórico. `--send-initial` ativa o envio inicial (se não for dry-run).

## Como o sistema evita mensagens repetidas

- `data/state.json` contém as ofertas elegíveis do último ciclo concluído.
- Primeira execução normal: cria linha de base, sem e-mail.
- Oferta nova: dispara 1 vez; mesma oferta com mesmo preço ou preço maior não dispara novamente.
- Nova queda de preço: dispara outro aviso.
- Oferta deixou a lista e voltou: dispara novamente (desde que o ciclo sem a oferta tenha concluído com segurança).
- Quando o envio SMTP falha, o arquivo não é atualizado para que a promoção possa ser reenviada na próxima execução.
- **Ressalva:** se o e-mail for aceito pelo SMTP mas o push de estado falhar, poderá ocorrer duplicação na execução seguinte. SMTP+Git não oferecem transação exatamente uma vez.

## Onde mudar os filtros

Edite `config/settings.json`. Valores iniciais:

```json
{"max_price_brl":100,"min_discount_percent":30,"min_critic_score":80,"min_player_positive_percent":85,"min_player_reviews":200}
```

Ajustes da frequência são feitos no cron do workflow. Evite consultas em excesso ou múltiplos monitores sobre o mesmo site.

## Privacidade e segurança

- Repositório privado, segredos apenas no GitHub Secrets, permissões mínimas para gravação de estado.
- Sem Docker, banco, servidor, credenciais Nintendo ou serviços pagos obrigatórios.
- SMTP usa TLS. Os links no e-mail são destinos externos; confirme sempre o domínio antes de comprar.
- A classificação 'popular' é uma aproximação baseada em volume de avaliações e notas, **não** um ranking oficial de vendas no Switch.

## Próximas melhorias

Aumentar a cobertura com uma fonte licenciada/API estável, incluir paginação quando verificável, adaptar o HTML do fornecedor se mudar, e adicionar whitelist de gêneros ou jogos já comprados.
