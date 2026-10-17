# Trabalho Prático: Bilheteria

[![Java](https://img.shields.io/badge/Java-17%2B-orange?logo=java)](https://www.oracle.com/java/technologies/javase-downloads.html)
[![C++](https://img.shields.io/badge/C++-20%2B-green?logo=c%2B%2B)](https://en.cppreference.com/w/cpp/20)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org)

Repositório-base do trabalho prático sobre **mecanismos de sincronização** da disciplina de **Programação Concorrente** da [Universidade Federal do Rio Grande do Norte (UFRN)](https://www.ufrn.br), Natal, RN.

Última atualização: 17/10/2026.

## Sumário

- [Objetivo](#objetivo)
- [Tarefas](#tarefas)
  - [O problema](#o-problema)
  - [Regras do serviço](#regras-do-serviço)
  - [Material fornecido](#material-fornecido)
  - [Implementação](#implementação)
  - [Experimentação](#experimentação)
  - [Relato](#relato)
- [Autoria e política de colaboração](#autoria-e-política-de-colaboração)
- [Entrega](#entrega)
- [Avaliação](#avaliação)
- [Dúvidas e informações](#dúvidas-e-informações)

## Objetivo

Projetar, implementar e avaliar o núcleo concorrente de um serviço de venda de ingressos de alta demanda, escolhendo e justificando os **mecanismos de sincronização** adequados a cada parte do problema. O foco não está em fazer o programa rodar, e sim em responder, com argumentos e medições, perguntas como:

- Que estado é compartilhado e que invariantes precisam ser protegidos?
- Qual mecanismo (exclusão mútua, semáforo, monitor com variável de condição, trava de leitura e escrita, barreira, operação atômica) serve melhor a cada ponto, e por quê?
- Quanto custa a escolha mais simples, e o que se ganha ao refiná-la?

## Tarefas

### O problema

Na abertura da venda de um show, milhares de compradores acessam ao mesmo tempo o mesmo mapa de assentos. A procura se concentra nos melhores lugares, e vários compradores disputam o mesmo assento. O serviço precisa garantir que **cada assento seja vendido no máximo uma vez**, mesmo sob essa disputa, e continuar respondendo rapidamente a quem apenas consulta o mapa.

O funcionamento imita o de bilheterias reais:

1. O comprador **consulta o mapa** de um setor (operação de leitura, muito frequente).
2. Escolhe assentos e os **reserva** (*hold*). A reserva vale por um tempo limitado (**TTL**); se o comprador não concluir a compra, o assento volta a ficar disponível. Cada comprador pode manter no máximo `max_holds` reservas ao mesmo tempo (o grupo é limitado).
3. **Compra** cada assento reservado. O pagamento passa por um gateway externo que aceita só `max_payments` cobranças simultâneas, e o serviço deve respeitar esse limite.
4. Pode também **liberar** uma reserva própria.

Cada comprador é atendido por uma única thread, que executa as suas operações em sequência (com pausas de "reflexão" entre elas). Compradores diferentes são atendidos concorrentemente. A compra de um grupo **não** é atômica: cada assento é reservado e comprado individualmente, e é aceitável que o comprador consiga apenas parte do que queria.

### Regras do serviço

Estas regras definem o comportamento esperado. O [validador](#material-fornecido) verifica o que for possível a partir do log.

**Parâmetros.** Lidos da linha `PARAMS` da carga: `seats` (assentos, numerados de 0 a `seats-1`), `section_size` (o setor de um assento é `assento / section_size`), `max_holds`, `ttl_ms`, `payment_ms`, `max_payments`, `grace_ms` e `queue_capacity`.

**Estado de um assento.** `DISPONÍVEL`, `RESERVADO` por um comprador até `t0 + TTL` (em que `t0` é o instante em que a reserva foi concedida), `EM PAGAMENTO` ou `VENDIDO`. Uma reserva cujo prazo passou **equivale a assento disponível** para todos os efeitos, seja qual for a estratégia usada para detectar isso. Qualquer operação que comece mais de `grace_ms` depois do vencimento deve enxergar o assento como disponível.

**`hold(comprador, assento)`**, verificando nesta ordem:

| Situação | Resultado |
|:--|:--|
| Assento vendido, ou reservado/em pagamento por **outro** comprador | `TAKEN` |
| Assento já reservado (ainda válido) pelo próprio comprador | `ALREADY` (o prazo não é renovado) |
| O comprador já tem `max_holds` reservas válidas | `LIMIT` |
| Caso contrário | `HELD` (reserva válida até agora + TTL) |

Reservas já consumidas por compra ou liberação, e reservas vencidas, não contam para o limite.

**`purchase(comprador, assento, cartão_ok)`**

- Para cobrar, o serviço chama `gateway.charge(...)`, que dura `payment_ms`. **No máximo `max_payments` cobranças podem estar em andamento ao mesmo tempo.**
- A existência de uma reserva válida do comprador é verificada **depois** de obter permissão para cobrar (e não antes de esperar por ela). Sem reserva válida, retorna `NOHOLD` e **não cobra**.
- Com reserva válida, o assento passa a `EM PAGAMENTO`: ninguém mais o obtém enquanto a cobrança durar, mesmo que o TTL termine nesse intervalo.
- Cobrança aprovada: `SOLD` (o assento é vendido). Recusada: `DECLINED` (o assento volta a ficar disponível).

**`release(comprador, assento)`**: `RELEASED` se o comprador tem reserva válida do assento (que volta a ficar disponível), senão `NOHOLD`.

**`view(setor)`**: devolve quantos assentos do setor estão disponíveis, reservados (reservas válidas ou em pagamento) e vendidos. Cada assento deve ser contado exatamente uma vez. O resultado não precisa ser um instantâneo atômico de todo o setor.

**Contadores.** Ao final, `stats()` informa `sold`, `holds_granted` (resultados `HELD`), `holds_rejected` (qualquer outro resultado de `hold`), `purchases_declined` e `views`. Devem coincidir exatamente com o que ocorreu, sem perder atualizações.

### Material fornecido

```
ticket-sync/
├── tools/
│   ├── generate_workload.py   # gerador de carga (determinístico, a partir de uma semente)
│   └── validate_log.py        # validador do log de execução
├── workloads/                 # cargas geradas (não versionadas; ver .gitignore)
├── java/src/                  # Harness.java (fornecido) + esqueletos para completar
├── cpp/                       # harness.h (fornecido) + esqueletos + Makefile
├── python/                    # harness.py (fornecido) + esqueletos
├── author.md
└── README.md
```

**Gerador de carga.** Produz um arquivo texto com as sessões dos compradores: consultas, grupos de 1 a 4 assentos (e alguns compradores gananciosos que tentam passar do limite), compradores que desistem sem liberar, que liberam, que demoram mais que o TTL e que usam cartão recusado. 60% dos pedidos miram o mesmo setor, de modo a criar um ponto quente.

```bash
python3 tools/generate_workload.py --profile realistic --seed 1 -o workloads/realistic-1.txt
python3 tools/generate_workload.py --profile stress    --seed 1 -o workloads/stress-1.txt
```

| Perfil | Característica | Sessões (padrão) | Para que serve |
|:--|:--|--:|:--|
| `realistic` | Pausas de reflexão de 5 a 120 ms, TTL de 200 ms, `max_payments` = 8 | 3000 | Comportamento próximo ao de uso real; o tempo é dominado pelas pausas |
| `stress` | Quase sem pausas, TTL de 100 ms, `max_payments` = 4 | 20000 | Expor o custo da sincronização |

A opção `--sessions N` altera o tamanho. A mesma semente gera sempre o mesmo arquivo. **A avaliação usará sementes que não são divulgadas**, portanto teste com várias.

**Código fornecido (`Harness`).** Lê a carga, fornece o relógio `now_ns()`, o gateway de pagamento, o executor de sessões (`SessionRunner`) e grava o log. **Não modifique** esses arquivos (`Harness.java`, `harness.h`, `harness.py`): na avaliação eles serão substituídos pelos originais. Use o relógio `now_ns()` também no serviço, para o cálculo do TTL.

**Validador.** Lê a carga e o log e verifica, só a partir dos registros:

| Categoria | O que verifica |
|:--|:--|
| `completude` | Todas as operações da carga foram executadas e registradas exatamente uma vez, e a execução terminou |
| `assento-vendido-uma-vez` | Nenhum assento foi vendido duas vezes |
| `reserva-exclusiva` | Dois compradores nunca mantêm reserva do mesmo assento ao mesmo tempo |
| `reserva-em-assento-vendido` | Nenhuma reserva é concedida depois da venda |
| `operacao-sem-reserva`, `operacao-apos-expiracao` | Compra e liberação bem-sucedidas exigem reserva do próprio comprador, ainda válida |
| `rejeicao-indevida` | Nenhum `TAKEN`, `LIMIT` ou `NOHOLD` sem justificativa possível (por exemplo, reserva vencida que nunca foi liberada) |
| `limite-de-reservas` | Nenhum comprador excede `max_holds` |
| `limite-de-pagamentos` | Nunca há mais de `max_payments` cobranças simultâneas no gateway |
| `pagamento` | Cada compra concluída tem exatamente uma cobrança, coerente com o cartão; nenhuma cobrança sem compra |
| `mapa-de-assentos` | Os totais de `view` somam o tamanho do setor, e o número de vendidos é compatível com o log |
| `contadores` | `stats()` coincide com o log |

```bash
python3 tools/validate_log.py workloads/realistic-1.txt events.log
```

Cada operação é registrada com o instante de início e de término. Como o efeito real ocorreu em algum ponto desse intervalo, **o validador só aponta violações inequívocas**. Isso tem duas consequências. Se ele reclamar, o seu programa tem defeito. Se ele não reclamar, o programa **não** está provado correto: condições de corrida são intermitentes, então repita as execuções, com muitas threads e várias sementes, e argumente a corretude no relatório.

### Implementação

Implemente o trabalho em **uma** das linguagens fornecidas (Java 17+, C++20 ou Python 3.10+), a mesma para toda a dupla. Copie o diretório da linguagem escolhida para a raiz do seu repositório e **remova os demais**. Os esqueletos compilam, mas lançam exceção nos métodos a implementar.

**Serviço.** Implemente a interface `TicketService` **duas vezes**:

1. `Coarse`: uma versão simples e correta, com sincronização grossa. Ela é a sua referência de corretude e a linha de base dos experimentos.
2. `Fine`: uma versão refinada, com granularidade de sincronização mais fina e/ou mecanismos diferentes dos da primeira, para reduzir a contenção. Deve ser realmente diferente: não basta renomear a primeira.

Além das duas versões, **decida e justifique**:

- como e quando as reservas vencidas são liberadas (por exemplo, ao serem encontradas por uma operação, ou por uma thread auxiliar; se houver thread auxiliar, ela deve ser encerrada em `close()`);
- como o limite de `max_payments` é garantido;
- como o mapa de assentos é lido sem atrapalhar quem reserva e compra;
- como os contadores são mantidos.

**Pipeline** (`Main`). O esqueleto executa tudo sequencialmente. Substitua o laço por um pipeline concorrente com:

- um **produtor**, que entrega as sessões da carga, na ordem do arquivo, a `--workers` threads trabalhadoras;
- uma **fila limitada**: no máximo `queue_capacity` sessões esperando; quando está cheia, o produtor espera; quando está vazia, as trabalhadoras esperam. A espera não deve consumir processador;
- **`--workers` threads trabalhadoras**, cada uma com o seu `SessionRunner` e a sua lista de registros, que processam uma sessão inteira por vez;
- uma **porta de largada**: o produtor, as trabalhadoras e a thread principal começam juntos, e o tempo medido (`wall`) vai da abertura da porta até o término de todas as sessões, sem incluir a criação das threads;
- **encerramento correto**: as trabalhadoras terminam quando as sessões acabam, sem depender de pausas, de tempo limite nem de valores sentinela fora da carga, e o programa termina sem threads penduradas.

**Restrições.**

- As threads devem ser criadas explicitamente. **Não é permitido usar executores nem pools de threads** (em Java, `ExecutorService`, `ForkJoinPool`, `CompletableFuture` assíncrono e *streams* paralelas; em C++, `std::async` e bibliotecas de pools; em Python, `concurrent.futures` e `multiprocessing.pool`).
- Em Python, use threads (`threading`), não processos.
- Não use espera ocupada, exceto quando for o mecanismo escolhido e justificado (por exemplo, uma trava giratória), e nesse caso meça o custo.
- Não altere o código fornecido nem o formato do log.

**Execução.**

```bash
# Java
javac -d out java/src/*.java
java -cp out Main workloads/realistic-1.txt --workers 16 --impl fine -o events.log

# C++
make -C cpp && ./cpp/ticket_sync workloads/realistic-1.txt --workers 16 --impl fine -o events.log

# Python
python3 python/main.py workloads/realistic-1.txt --workers 16 --impl fine -o events.log

# Validação (qualquer linguagem)
python3 tools/validate_log.py workloads/realistic-1.txt events.log
```

### Experimentação

Toda execução que entrar nos resultados deve ser **validada**, e o relatório deve informar quantas execuções passaram. Resultado de execução inválida não é resultado.

1. **Número de threads trabalhadoras.** Varie `--workers` em pelo menos cinco valores, entre eles 1 e um valor bem maior que o número de núcleos lógicos (por exemplo, 1, 2, 8, 32 e 64).
2. **Duas versões do serviço.** Compare `coarse` e `fine` em cada valor.
3. **Dois perfis de carga.** Use `realistic` e `stress`. Para os experimentos, reduza o tamanho para que o total seja viável (sugestão: `--sessions 600` no `realistic` e `--sessions 5000` no `stress`; a execução com 1 thread é a mais demorada).
4. **Uma decisão de projeto adicional.** Escolha pelo menos uma decisão da lista da seção anterior (por exemplo, liberação preguiçosa × por thread auxiliar, ou mapa lido com ou sem exclusão total) e meça o efeito de trocá-la, mantendo o resto fixo.
5. **Repetições.** Cada configuração deve ser executada pelo menos **10 vezes**, informando **média e desvio padrão amostral** (n-1) do tempo e da vazão (sessões por segundo). Se usar Java, execute antes algumas rodadas de aquecimento (*warm-up*), descarte-as e informe quantas foram. Use a mesma carga em todas as repetições e, se quiser variar a semente, faça-o de forma sistemática e informada.
6. **Ambiente.** Informe processador, número de **núcleos lógicos**, sistema operacional, versão da linguagem e do compilador, e feche outros programas durante as medições.
7. Para ao menos uma configuração, interprete também o **tempo por operação** a partir do log (por exemplo, a distribuição da duração de `hold` e `view`).

### Relato

Escreva um relatório em **português**, em PDF, **sem limite de páginas**, com ao menos:

1. **Identificação e ambiente**: dupla, linguagem, ambiente de execução.
2. **Projeto da sincronização**: uma tabela com, para cada parte do estado compartilhado, o invariante que ela precisa preservar, o mecanismo escolhido nas versões `coarse` e `fine`, a razão da escolha e as alternativas que você considerou e descartou.
3. **Argumento de corretude**: para cada regra do serviço, como o seu código a garante. Indique as seções críticas, a ordem de aquisição de travas e por que **não há deadlock**, e discuta se pode haver **starvation** de algum comprador. Se usou variáveis de condição, explique por que a condição é testada em laço e quem sinaliza quem.
4. **Pipeline**: como a fila limitada e o encerramento funcionam, e por que não há perda de sessões nem espera infinita.
5. **Metodologia dos experimentos**: o que foi medido, como, quantas repetições, o tratamento do *warm-up* (Java) e como a validação foi usada.
6. **Resultados**: tabelas e gráficos com média e desvio padrão.
7. **Análise**: explique os resultados em vez de apenas descrevê-los. Por que `fine` ganha (ou não) de `coarse` em cada perfil? O que acontece quando as threads superam os núcleos? Por que o perfil `realistic` esconde diferenças que o `stress` revela? Houve algum resultado que contrariou a sua expectativa? Em Python, discuta o efeito do GIL nas medições.
8. **Limitações e trabalhos futuros**: o que o seu teste não cobre e o que você faria com mais tempo.

## Autoria e política de colaboração

O trabalho deve ser realizado em **dupla**, com as tarefas divididas de forma equilibrada entre os integrantes. Após a implementação, preencha o arquivo [`author.md`](author.md) com o nome completo e o e-mail de cada integrante.

Discutir ideias com colegas é permitido, mas **cópia de código** é proibida: trabalhos copiados, no todo ou em parte, de outros colegas, da Internet ou de ferramentas de geração de código por inteligência artificial serão **anulados** e receberão **nota zero**. Usar a documentação das linguagens e consultar material da disciplina é, naturalmente, permitido. Os integrantes devem ser capazes de explicar qualquer trecho do código e do relatório.

## Entrega

- **Código**: no repositório Git da dupla, criado por meio da atividade do **Classroom 50** disponibilizada na turma do SIGAA. Mantenha apenas os diretórios necessários (`tools/` e o diretório da linguagem escolhida). Configure o `.gitignore` para não versionar arquivos gerados (executáveis, `out/`, `__pycache__/`, cargas e logs). O repositório deve conter instruções de compilação e execução.
- **Relatório**: em PDF, enviado pelo SIGAA (opção **Tarefas**) por **apenas um** integrante da dupla, com a URL do repositório no campo **Comentários**. Somente o PDF é enviado pelo SIGAA.
- **Prazo**: **31/10/2026, às 23h59**. Os commits posteriores ao prazo não serão considerados.

## Avaliação

O trabalho vale até **10,0 pontos**.

| Critério | Pontos |
|:--|--:|
| **Corretude**: o validador não aponta violações, nem há deadlock, nas execuções de avaliação (sementes não divulgadas, os dois perfis, vários números de threads, execuções repetidas, limite de 5 minutos por execução) | 3,0 |
| **Projeto da sincronização**: adequação e uso correto dos mecanismos, granularidade, ausência de deadlock e de espera ocupada injustificada, versão `fine` de fato refinada, pipeline e encerramento corretos | 2,0 |
| **Rigor experimental**: variação de threads, duas versões, dois perfis, decisão adicional, 10 repetições com média e desvio padrão, *warm-up* em Java, uso do validador, ambiente informado | 2,0 |
| **Qualidade do relatório**: justificativas, argumento de corretude, interpretação genuína dos resultados, limitações | 2,5 |
| **Código e repositório**: README com instruções, histórico de commits razoável, organização do código | 0,5 |

Observações:

- Violação de uma regra de segurança nas execuções de avaliação (por exemplo, assento vendido duas vezes) reduz a nota de corretude proporcionalmente às execuções afetadas. Um programa que trava ou não termina no limite de tempo tem a execução contada como inválida.
- Usar um mecanismo que funciona, mas sem justificar por que é adequado, vale menos que um mecanismo mais simples, bem justificado.
- Relatórios cujas conclusões não se sustentam nos dados apresentados perdem pontos no critério de qualidade do relatório.

## Dúvidas e informações

Dúvidas sobre o trabalho devem ser enviadas por e-mail ao professor: [everton.cavalcante@ufrn.br](mailto:everton.cavalcante@ufrn.br). Se encontrar erro no gerador, no validador ou no código fornecido, avise: a correção será divulgada para toda a turma.
