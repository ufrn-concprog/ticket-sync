# Trabalho Prático: Serviço de Bilheteria

<sub>Última atualização: 19/10/2026</sub><br/>

[![Java](https://img.shields.io/badge/Java-17%2B-orange?logo=java)](https://www.oracle.com/java/technologies/javase-downloads.html)
[![C++](https://img.shields.io/badge/C++-20%2B-green?logo=c%2B%2B)](https://en.cppreference.com/w/cpp/20)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org)

> **Declaração sobre o uso de Inteligência Artificial generativa.** A concepção deste trabalho prático (o tema, o problema, os objetivos de aprendizagem, as regras do serviço e os critérios de avaliação) foi realizada pelo docente. A presente especificação e os códigos-fonte disponibilizados neste repositório foram produzidos com o auxílio de uma ferramenta de Inteligência Artificial generativa (mais precisamente, o Claude, da Anthropic, no modelo Sonnet 5.5), sob a direção, revisão e validação do docente, que permanece integralmente responsável pelos artefatos produzidos e por seu conteúdo. O material foi revisado e testado pelo docente com soluções de referência nas linguagens de programação Java, C++ e Python, mas ainda pode haver erros ou eventuais inconsistências. Destaque-se que esta declaração **não altera** a política de colaboração e de uso de ferramentas de Inteligência Artificial para a entrega a ser realizada, conforme estabelecido na seção [Autoria e política de colaboração](#autoria-e-política-de-colaboração).

## Sumário

- [Objetivo](#objetivo)
- [O problema](#o-problema)
- [Funcionamento do serviço](#funcionamento-do-serviço)
- [Material fornecido](#material-fornecido)
- [Tarefas](#tarefas)
  - [Implementação](#implementação)
  - [Experimentação](#experimentação)
  - [Relato](#relato)
- [Autoria e política de colaboração](#autoria-e-política-de-colaboração)
- [Entrega](#entrega)
- [Avaliação](#avaliação)
- [Dúvidas e informações](#dúvidas-e-informações)

## Objetivo

O objetivo deste trabalho prático é projetar, implementar e avaliar o núcleo concorrente de um serviço de venda de ingressos de alta demanda, escolhendo e justificando os mecanismos de sincronização adequados para cada parte do problema. O foco não está apenas em fazer o programa executar, mas também em responder, com argumentos e medições, perguntas como:

- Que estado é compartilhado e quais invariantes precisam ser preservados?
- Qual mecanismo de sincronização (semáforo, monitor com variável de condição, *lock* de leitura e escrita, barreira, operação atômica) serve melhor a cada ponto, e por quê?
- Quanto custa a escolha mais simples, e o que se ganha ao refiná-la?

## O problema

Na abertura das vendas de um espetáculo em um teatro, centenas de compradores podem acessar o mesmo mapa de assentos simultaneamente. A procura concentra-se nos melhores lugares e vários compradores disputam o mesmo assento. O serviço precisa garantir que cada assento seja vendido no máximo uma vez, mesmo durante essa disputa, e continuar respondendo rapidamente a quem apenas consulta o mapa.

O funcionamento desse serviço se assemelha ao de bilheterias reais:

1. A pessoa compradora consulta o mapa de um setor, o que caracteriza uma operação de leitura muito frequente.
2. A pessoa compradora escolhe assentos e os reserva, que ficam em espera (*hold*) por um tempo limitado, o chamado *time-to-live* ($TTL$). Se a pessoa compradora não concluir a compra, o assento volta a ficar disponível. Cada comprador pode manter um número máximo de reservas simultâneas (`max_holds`).
3. A pessoa compradora adquire cada assento reservado. O pagamento passa por um *gateway* externo que aceita apenas um número limitado de cobranças simultâneas (`max_payments`), e o serviço deve respeitar esse limite.
4. A pessoa compradora também pode liberar uma reserva por conta própria.

Para melhor atender às múltiplas requisições, cada pessoa compradora é atendida por uma *thread* que executa suas operações sequencialmente, enquanto compradores diferentes são atendidos de forma concorrente. A compra de um grupo **não** é atômica: cada assento é reservado e comprado individualmente e é aceitável que a pessoa compradora consiga apenas parte do que queria.

## Funcionamento do serviço

### Estrutura do arquivo de carga

O serviço de bilheteria a ser implementado não tem usuários reais. O que se consome é um arquivo de texto, chamado **carga** (*workload*), que descreve todas as ações que a pessoa compradora vai realizar durante a venda, sendo, assim, uma espécie de roteiro de execução. O programa lê esse roteiro, cria as *threads* para representar os compradores e o resultado é registrado em um *log*.

É importante destacar que a carga é apenas a entrada do programa: ela descreve o que cada pessoa compradora tenta fazer, e não o que acontece. O resultado quanto a quem efetivamente reserva cada assento depende da disputa entre as *threads* e é decidido pelo serviço.

O arquivo de carga contém uma linha por registro. Linhas em branco e linhas começadas por # são comentários, devendo, portanto, ser ignoradas. Há basicamente dois tipos de registro:

| Registro | Quantidade | Conteúdo |
| :------- | :--------- | :------- |
| `PARAMS ...` | Exatamente um, antes das sessões | Os oito parâmetros do serviço, no formato `nome=valor` |
| `SESSION <id> <operação> <operação> ...` | Um por pessoa compradora | O identificador da pessoa compradora e a sequência das suas ações |

### Parâmetros

O comportamento do serviço depende de oito parâmetros, fornecidos na linha iniciada com o prefixo `PARAMS` no arquivo de carga. Esses parâmtros são:

| Parâmetro | Significado |
| :-------- | :---------- |
| `seats` | Número total de assentos do evento. Os assentos são identificados por números inteiros de `0` a `seats-1`. |
| `section_size` | Quantidade de assentos em cada setor. O setor do assento `a` é `a / section_size` (divisão inteira), de modo que o Setor 0 tem assentos numerados de `0` a `section_size-1`, o Setor 1 os seguintes, e assim por diante. O último setor pode ser menor, se `seats` não for múltiplo de `section_size`. Os setores existem apenas para a operação `view`, que consulta o mapa de um setor por vez. |
| `max_holds` | Número máximo de reservas válidas que um mesmo comprador pode manter simultaneamente (limite do grupo). |
| `ttl_ms` | Tempo ($TTL$), em milissegundos, durante o qual uma reserva permanece válida. Uma reserva concedida no instante $t_0$ é válida até $t_0$ + `ttl_ms`. Depois disso, o assento volta a ficar disponível, mesmo que ninguém o tenha liberado explicitamente. |
| `payment_ms` | Duração, em milissegundos, de cada cobrança no *gateway* de pagamento, correspondente ao tempo que a chamada `gateway.charge(...)` leva para retornar. Quem chama o serviço fica esperando durante esse tempo. |
| `max_payments` | Número de cobranças que o *gateway* aceita simultaneamente. O *gateway* fornecido não impõe esse limite; respeitá-lo é responsabilidade do serviço. |
| `grace_ms` | Tempo de tolerância, em milissegundos, para a detecção de uma reserva vencida. Uma implementação pode liberar reservas vencidas imediatamente (ao encontrá-las numa operação) ou posteriormente (por exemplo, por uma *thread* auxiliar que acorda periodicamente). Este parâmetro é o atraso máximo aceito, de modo que passados `ttl_ms` + `grace_ms` milissegundos desde a concessão, qualquer operação deve tratar o assento como disponível. |
| `queue_capacity` | Capacidade da fila, que se refere ao número de sessões que podem aguardar por uma *thread* ao mesmo tempo. |

A infraestrutura de execução do serviço, cujo código-fonte está disponível neste repositório (ver a seção [Material fornecido](#material-fornecido)), lê essa linha e a entrega ao programa como um objeto, que é então passado ao construtor do serviço. Assim, o mesmo programa funciona com qualquer carga e o validador usa os mesmos valores para conferir o *log*.

### Operações

Em cada linha `SESSION` do arquivo de carga, `<id>` é um inteiro único, usado como identificador da pessoa compradora, e as operações são executadas uma após a outra, na ordem em que aparecem. Cada uma ocupa um ou dois argumentos depois da letra:

| Operação na linha | Significado | Chamada no serviço |
| :---------------- | :---------- | :----------------- |
| `V <sector>` | A pessoa compradora consulta o mapa de um setor | `view(sector)` |
| `H <seat>` | A pessoa compradora tenta reservar um assento | `hold(buyer, seat)` |
| `P <seat> ok` ou `P <seat> bad` | A pessoa compradora paga pelo assento; `ok` refere-se a pagamento aprovado e `bad` a pagamento recusado | `purchase(buyer, seat, card_ok)` |
| `R <seat>` | A pessoa compradora libera uma reserva por conta própria | `release(buyer, seat)` |
| `T <time>` | A pessoa compradora "pensa" por `<time>` milissegundos antes da próxima operação | Nenhuma: a *thread* é simplesmente suspensa |

Um arquivo ilustrativo teria, por exemplo, o seguinte conteúdo:

```text
PARAMS seats=2000 section_size=100 max_holds=4 ttl_ms=200 payment_ms=10 max_payments=8 grace_ms=50 queue_capacity=64
SESSION 0 V 0 V 14 V 3
SESSION 1 V 0 H 77 H 78 T 94 P 77 ok P 78 bad
SESSION 2 V 0 H 69 T 120 R 69
SESSION 3 V 0 H 69 T 347 P 69 ok
```

Nesse exemplo:

- Na Sessão 0, a pessoa compradora apenas olha o mapa dos Setores 0, 14 e 3 e abandona o processo. É um tipo de pessoa usuária que apenas navega pelo serviço (operação mais comum) e é o que mais pesa na operação `view`.
- Na Sessão 1, a pessoa compradora consulta o Setor 0, tenta reservar os assentos 77 e 78, pensa por 94 ms e então paga por ambos. O primeiro pagamento é aprovado e o segundo recusado.
- Na Sessão 2, a pessoa compradora consulta o Setor 0, reserva o assento 69, pensa por 120 ms e, em seguida, libera esse assento sem finalizar efetivamente a compra.
- Na Sessão 3, a pessoa compradora também consulta o Setor 0 e reserva o assento 69, mas demora 347 ms para pagar pela reserva, o que excede o `ttl_ms` de 200 ms. Se a reserva existiu, ela terá vencido.

É importante destacar que as sessões são independentes entre si, mas disputam os mesmos assentos. As Sessões 2 e 3 do exemplo acima disputam o assento 69 do Setor 0. Além disso, a ordem em que o serviço as atende varia de uma execução para outra, e é aí que as condições de corrida aparecem. A ordem das linhas `SESSION` no arquivo de carga é a ordem em que o produtor as entrega às *threads*, mas isso não determina a ordem em que elas terminam.

### Estado de um assento

Um assento pode ter os seguintes estados:

| Estado         | Significado                              |
| :------------- | :--------------------------------------- |
| *Disponível*   | Ninguém reservou ou comprou o assento. |
| *Reservado*    | Uma pessoa compradora reservou o assento e tem até $t_0$ + `ttl_ms` para finalizar o pagamento ($t_0$ é o instante em que a reserva foi concedida). Outros compradores não conseguem reservar esse assento bloqueado. |
| *Em pagamento* | A pessoa compradora que reservou o assento está realizando o pagamento, que está em andamento no *gateway*. |
| *Vendido*      | O pagamento foi aprovado e o assento não muda mais de estado. |

Uma reserva cujo prazo expirou equivale a um assento disponível para todos os efeitos, independentemente da estratégia utilizada para detectá-la. Note que não existe uma operação que "expire" a reserva: o vencimento ocorre porque o tempo passou e o serviço precisa percebê-lo.

O serviço é um objeto que implementa a interface `TicketService` definida na infraestrutura de execução. Essa interface define quatro operações que correspondem às ações de uma pessoa compradora, somando-se a operações adicionais referentes à execução do serviço:

| Operação | Ação da pessoa compradora | Quem a chama |
| :------- | :------------------------ | :----------- |
| `view(sector)` | Consultar o mapa de assentos de um setor | `SessionRunner`, a cada linha `V` do arquivo de carga |
| `hold(buyer, seat)` | Reservar um assento | `SessionRunner`, a cada linha `H` do arquivo de carga |
| `purchase(buyer, seat, card_ok)` | Pagar pelo assento reservado | `SessionRunner`, a cada linha `P` do arquivo de carga |
| `release(buyer, seat)` | Desistir de uma reserva | `SessionRunner`, a cada linha `R` do arquivo de carga |
| `stats()` | Esta não é uma ação do processo de reserva e compra; ela apenas devolve os contadores | `Main`, uma vez, no fim da execução |
| `start()` e `close()` | Estas não são ações de compra, mas sim para iniciar e encerrar o serviço | `Main`, uma vez cada |

O objeto `SessionRunner` fornecido lê as operações de cada sessão da carga, na ordem, e as chama no serviço. Entre uma operação e outra, ele pode ser suspenso (linhas `T` da carga), simulando o tempo que a pessoa compradora leva para decidir sobre a compra. Cada *thread* executa uma sessão por vez, então muitas *threads* chamam as operações do mesmo objeto de serviço simultaneamente, e por isso o estado interno do serviço precisa de sincronização.

As operações podem ter os seguintes argumentos:

- **`buyer`:** É um número inteiro que identifica a pessoa compradora, definido na sessão do arquivo de carga. Uma sessão corresponde a uma pessoa compradora, e uma pessoa compradora é atendida por uma única *thread*; logo, as operações de uma mesma pessoa compradora nunca se sobrepõem no tempo. Por outro lado, operações de compradores diferentes se sobrepõem o tempo todo.
- **`seat` e `sector`:** São números inteiros definidos por `seats` e `section_size` no mapa de parâmetros.
- **`card_ok`:** Indica se o pagamento da pessoa compradora será aprovado (`true`) ou recusado (`false`). Na operação `purchase`, ele deve ser repassado ao *gateway* sem alterá-lo, e ele decide o resultado da cobrança, não cabendo ao serviço determiná-lo.

Cada operação retorna um código de resultado, escrito exatamente como `HELD`, `TAKEN`, `SOLD`, `NOHOLD` etc. O `SessionRunner` grava esse código no *log* e o validador o confere. As constantes já estão definidas no código fornecido para a infraestrutura de execução. Cada uma das operações é detalhada a seguir.

**`hold(buyer, seat)`:** Esta operação reserva um assento para uma pessoa compradora, mantendo a reserva por `ttl_ms` milissegundos. As verificações são feitas **nesta ordem** e a primeira que se aplicar decide o resultado:

| Situação | Resultado |
| :------- | :-------- |
| O assento está *vendido*, ou *reservado* ou *em pagamento* por outra pessoa compradora | `TAKEN`: não foi possível reservar o assento, pois ele não está livre |
| O assento está *reservado* pela própria pessoa compradora e a reserva ainda está válida | `ALREADY`: nada muda |
| A pessoa compradora já tem `max_holds` reservas válidas | `LIMIT`: a pessoa compradora atingiu o limite do grupo |
| Nenhuma das anteriores | `HELD`: o assento fica reservado à pessoa compradora do instante de tempo atual mais `ttl_ms` |

Reservas já consumidas por compra ou liberação, e reservas vencidas, não contam para o limite. Por exemplo, com `max_holds=4`, uma pessoa compradora que já reservou os assentos 10, 11, 12 e 13 recebe `LIMIT` ao tentar o 14, mas recebe `ALREADY` ao tentar o 12 novamente, pois o assento é verificado antes da verificação do limite.

**`purchase(buyer, seat, card_ok)`:** Esta operação realiza o pagamento de um assento reservado. Sem esta operação, a reserva expira.

- Para efetivar o pagamento, o serviço chama `gateway.charge(buyer, seat, card_ok)`, que dura `payment_ms` e retorna `true` se o pagamento foi aprovado. No máximo `max_payments` cobranças podem estar em andamento ao mesmo tempo; se já houver esse número, a compra espera a sua vez.
- A existência de uma reserva válida da pessoa compradora é verificada **depois** de obter permissão para efetuar o pagamento, e não antes de aguardá-la, pois a espera pode durar e a reserva pode vencer nesse intervalo. Sem reserva válida, o resultado desta operação é `NOHOLD` e nenhuma cobrança é efetuada. Isso vale tanto para quem nunca reservou o assento quanto para quem reservou e perdeu o prazo.
- Com reserva válida, o assento passa ao estado *em pagamento*: ninguém mais o obtém enquanto a cobrança durar, mesmo que `ttl_ms` termine nesse intervalo.
- Caso o pagamento tenha sido aprovado, o assento passa ao estado *vendido* e a operação retorna `SOLD`. Caso o pagamento tenha sido recusado, o assento volta ao estado *disponível* e o resultado da operação é `DECLINED`.

**`release(buyer, seat)`:**: Esta operação refere-se à ação de uma pessoa compradora que desistiu da compra do assento reservado. Ela retorna `RELEASED` se a pessoa compradora tinha uma reserva válida do assento, que passa ao estado *disponível*, ou `NOHOLD` caso a pessoa compradora nunca tenha reservado, já tenha liberado, a reserva já tenha expirado ou o assento seja de outra pessoa.

**`view(sector)`:** Esta operação realiza a consulta do mapa de um setor, retornando três números: quantos assentos do setor estão disponíveis, reservados (reservas válidas, incluindo os assentos em pagamento) e vendidos. Reservas vencidas contam como disponíveis. Nos códigos fornecidos, o resultado é um objeto com os campos `available`, `held` e `sold` (`SectionView` em Java e C++) ou a tupla `(available, held, sold)`, nessa ordem, em Python. Cada assento do setor deve ser contado exatamente uma vez, de modo que os três números somem o tamanho do setor. O resultado não precisa ser atômico em todo o setor: se um assento mudar de estado durante a contagem, vale a contagem de antes ou a de depois. É a operação mais frequente, e é ela que mostra o custo de uma sincronização excessiva para as *threads* que realizam apenas operações de leitura.

**`stats` e contadores:** Ao final da execução, `Main` chama `stats()`, que deve informar:

| Contador | O que conta |
| :------- | ----------- |
| `sold`   | Quantos assentos foram vendidos (resultados `SOLD`) |
| `holds_granted` | Quantas chamadas da operação `hold` retornaram `HELD` |
| `holds_rejected` | Quantas chamadas da operação `hold` retornaram qualquer outro resultado (`TAKEN`, `LIMIT` ou `ALREADY`) |
| `purchases_declined` | Quantas chamadas da operação `purchase` retornaram `DECLINED` |
| `views` | Quantas chamadas da operação `view` foram feitas |

Nos códigos fornecidos, o resultado de `stats()` tem exatamente estes cinco campos: em Python, um `dict` com as chaves acima; em C++, um objeto `Stats` com os mesmos nomes; em Java, um objeto Stats com os mesmos nomes em *camel case* (`holdsGranted`, `holdsRejected`, `purchasesDeclined`). Esses contadores são atualizados por várias *threads* simultaneamente e devem corresponder exatamente ao que ocorreu: o validador os compara com o *log*, e uma atualização perdida é considerada uma falha.

## Material fornecido

Para que o foco do trabalho seja na sincronização, este repositório fornece um conjunto de códigos implementados nas linguagens de programação Java, C++ e Python, mais precisamente:

- um **gerador de carga**, que cria o roteiro do que os compradores vão fazer;
- o código da **infraestrutura de execução** (*harness*) que lê esse roteiro, simula o *gateway* de pagamento, executa as operações de cada pessoa compradora no serviço e grava um registro (*log*) do que aconteceu;
- um **validador**, que lê o roteiro e o *log* e aponta violações das regras do serviço; e
- esqueletos do serviço e do programa principal em Java, C++ e Python, a serem completados; os esqueletos compilam e executam, porém as operações do serviço lançam uma exceção ("TODO") até que sejam implementadas.

O repositório está organizado da seguinte forma e os seus elementos principais são descritos a seguir.

```text
ticket-sync/
├── author.md
├── README.md
├── cpp/
│   ├── coarse_service.h
│   ├── fine_service.h
│   ├── harness.h
│   ├── main.cpp
│   ├── Makefile
├── java/src/
│   ├── CoarseTicketService.java
│   ├── FineTicketService.java
│   ├── Harness.java
│   ├── Main.java   
├── python/
│   ├── harness.py
│   ├── main.py
│   ├── ticket_service.py
├── tools/
│   ├── generate_workload.py
│   ├── summarize_log.py
│   └── validate_log.py
├── workloads/
```

### Gerador de carga

O gerador de carga cria um arquivo de texto de forma determinística a partir de um *perfil*, considerando, de forma aleatória, os seguintes tipos de pessoa compradora com base em proporções fixas:

| Tipo | Comportamento na carga | Proporção aproximada |
| :--- | :--------------------- | :------------------- |
| *Navegador* | Apenas consulta mapas (de 3 a 10 `V`) | 25% |
| *Comprador* | Consulta, reserva um grupo de 1 a 4 assentos vizinhos, pensa e paga por todos (com 5% de pagamento recusado) | 40% |
| *Desistente* | Reserva um grupo, pensa e abandona o processo de compra, ou libera os assentos (`R`) e desiste, deixando a reserva vencer por si só | 18% |
| *Lento* | Reserva, demora mais tempo que o $TTL$ e tenta efetuar o pagamento muito tardiamente | 12% |
| *Ganancioso* | Tenta reservar mais assentos que o limite `max_holds` | 5% |

Cerca de 60% das tentativas de reserva miram o Setor 0, localizado mais à frente do teatro, criando um "ponto quente" de disputa. As demais tentativas de reserva se distribuem uniformemente ao longo do evento.

O gerador de carga (arquivo [`generate_workload.py`](tools/generate_workload.py) localizado no diretório [`tools`](tools/)) foi implementado em Python e **não deve ser modificado**. Para gerar os arquivos, o gerador de carga deve ser executado a partir da raiz do repositório (o diretório [`workloads`](workloads/) já existe e os arquivos de texto gerados não são versionados):

```bash
python3 tools/generate_workload.py --profile realistic --seed 1 -o workloads/realistic-1.txt
python3 tools/generate_workload.py --profile stress    --seed 1 -o workloads/stress-1.txt
python3 tools/generate_workload.py --profile stress    --seed 7 --sessions 2000 -o workloads/stress-7-2000.txt
```

Cada um desses três comandos cria um arquivo de carga. As opções do gerador são as seguintes:

| Opção | Significado | Valor padrão |
| :---- | :---------- | :----------- |
| `--profile` | Perfil da carga (`realistic` ou `stress`), que define os parâmetros do serviço gravados na linha `PARAMS` e o tempo de reflexão dos compradores | `realistic` |
| `--seed` | Um número inteiro que representa a semente do sorteio. A mesma semente (com o mesmo perfil e o mesmo tamanho) sempre gera o mesmo arquivo, e sementes diferentes geram cargas diferentes. | `1` |
| `--sessions` | O tamanho da carga, em número de sessões (compradores) | `3000` para o perfil `realistic` e `20000` para o perfil `stress` |
| `-o` | Arquivo de saída. Sem esta opção, o gerador escreve o resultado na saída padrão | Saída em tela |

Os perfis *realistic* e *stress* têm o mesmo evento (2000 assentos, 20 setores de 100 assentos, limite de 4 reservas por comprador) e os mesmos tipos de compradores. O que muda entre eles é o ritmo e os limites, de modo a representar duas situações diferentes:

|    | `realistic` | `stress` |
| :- | :---------- | :------- |
| Pausa de reflexão `T` (comprador comum) | 5 a 120 ms | 0 a 30 ms |
| Pausa do comprador lento | 250 a 400 ms | 110 a 150 ms |
| `ttl_ms` (validade da reserva) | 200 | 100 |
| `payment_ms` (duração da cobrança) | 10 | 2 |
| `max_payments` (cobranças simultâneas) | 8 | 4 |
| `queue_capacity` (fila do *pipeline*) | 64 | 32 |
| Sessões (padrão) | 3000 | 20000 |

O perfil *realistic* imita a duração de uma interação humana: a pessoa compradora demora mais para decidir e o pagamento é mais lento. A maior parte do tempo de cada sessão é gasta sem progresso significativo, então esse perfil mostra se o serviço se comporta bem sob uma carga plausível e em que medida o número de *threads* ajuda a atender mais compradores simultaneamente. Em compensação, ele disfarça o custo da sincronização, porque o serviço passa quase todo o tempo ocioso. Já o perfil *stress* encurta as pausas, reduz a validade das reservas e o prazo de pagamento, além de limitar ainda mais as cobranças simultâneas. As mesmas operações chegam com maior densidade e as reservas vencem com mais frequência, o que aumenta a disputa pelos mesmos assentos e pelo *gateway*.

### Infraestrutura de execução (*harness*)

Como mencionado anteriormente, este repositório disponibiliza um conjunto de códigos-fonte, implementados em C++, Java e Python, já prontos para fazer o serviço funcionar. Essa infraestrutura de execução lê o arquivo de carga, fornece o temporizador, o *gateway* de pagamento, o executor de sessões (`SessionRunner`) e grava o *log*. Os arquivos [Harness.java](java/src/Harness.java), [harness.h](cpp/harness.h) e [harness.py](python/harness.py), localizados nos diretórios associados a cada linguagem de programação, **não devem ser modificados em hipótese alguma**. Na implementação do serviço, o temporizador fornecido (`Harness.nowNs()` em Java, `harness::now_ns()` em C++ e `now_ns()` em Python) deve ser utilizado para o cálculo do tempo $TTL$.

### Validador

O validador é um programa, implementado em Python (arquivo [validate_log.py](tools/validate_log.py)), para verificar se o que o serviço fez durante a execução respeitou as regras estabelecidas. Esse validador serve a dois propósitos: (i) encontrar defeitos durante o desenvolvimento e (ii) conferir cada execução. O validador lê o arquivo de carga (o que deveria acontecer) e o arquivo de *log* (o que efetivamente aconteceu) e procura contradições entre eles e no próprio *log*.

O *log* é o arquivo que o programa grava ao final de cada execução (`events.log`, por padrão, ou o nome especificado pela opção `-o`). Quem o escreve é a infraestrutura de execução, e não o código do serviço, de modo que este não modifica a estrutura do arquivo de *log*.

O objeto `SessionRunner` anota cada operação que executa, o *gateway* anota cada tentativa de pagamento, e o código principal grava o arquivo no fim. O conteúdo desse arquivo possui com campos separados por tabulação e quatro tipos de linha:

| Linha | Quantidade | Conteúdo |
| ----- | :--------- | :------- |
| `OP` | Uma por operação executada (não há linha para `T`) | Pessoa compradora, posição da operação na sessão, tipo (`V`, `H`, `P`, `R`), argumento, instante de início, instante de fim, resultado e informações extras |
| `CHG` | Uma por cobrança no *gateway* | Pessoa compradora, assento, instante de início, instante de fim e *status* do pagamento (`ok` ou `declined`) |
| `STATS` | Uma | Os cinco contadores devolvidos por `stats()` |
| `RUN` | Uma, sempre a última | Número de *threads* e tempo total da execução |

Os instantes de tempo são medidos em nanossegundos, pelo relógio monotônico do processo, a partir do início do programa. Um trecho de um arquivo de *log*, com as operações de uma pessoa compradora e a cobrança correspondente, seria:

```text
OP	62	0	V	0	87964268	87992991	OK	avail=50,held=31,sold=19
OP	62	1	H	35	87994407	88002285	HELD	
OP	62	3	P	35	152114617	162239678	SOLD	
CHG	62	35	152123377	162219116	ok
STATS	sold=236	holds_granted=387	holds_rejected=360	purchases_declined=16	views=1043
RUN	workers=32	wall_ns=1184389066
```

Nesse exemplo, a segunda linha indica que a pessoa compradora com ID 62, na operação de índice 1 da sua sessão, chamou `hold` no assento 35; a chamada começou em 87 994 407 ns, terminou em 88 002 285 ns e retornou `HELD`, o que significa que o assento passou ao estado *reservado*. O índice 2 não aparece no *log* porque é uma pausa (`T`), que não gera registro. A terceira linha refere-se à compra do mesmo assento, que resultou em `SOLD` (estado *vendido*), e a quarta linha diz respeito ao registro da tentativa de pagamento no *gateway*, cujo intervalo está contido no da compra. A linha `RUN` serve de sinal de que o programa terminou, de modo que um *log* sem ela indica uma execução que travou ou foi interrompida.

Para executar o validador, o seguinte comando deve ser executado, informando os arquivos de carga e de *log*, **nessa ordem**:

```bash
python3 tools/validate_log.py workloads/realistic-1.txt events.log
```

É essencial usar a mesma carga com a qual o log foi gerado, pois o validador compara as duas cargas. A opção `--max-print N` define quantos exemplos de cada categoria são exibidos (o padrão é 5). Numa execução sem violações, a saída esperada seria:

```text
sessões: 400  operações registradas: 2424/2424  assentos vendidos: 236  cobranças: 252  pico de pagamentos simultâneos: 8 (limite 8)
threads: 32  tempo: 1.184 s  vazão: 2047 ops/s, 338 sessões/s
RESULTADO: OK (nenhuma violação encontrada)
```

As duas primeiras linhas do resultado da validação indicam quantas operações foram registradas em relação ao esperado, quantos assentos foram vendidos, o maior número de cobranças simultâneas observado e a vazão da execução.

Em uma execução com defeito (aqui, um serviço sem o limite de pagamentos simultâneos, carga `stress`, 48 threads), o resultado da validação seria:

```text
sessões: 1500  operações registradas: 8898/8898  assentos vendidos: 555  cobranças: 582  pico de pagamentos simultâneos: 12 (limite 4)
threads: 48  tempo: 0.894 s  vazão: 9951 ops/s, 1677 sessões/s
[limite-de-pagamentos] 1 violação(ões)
    - até 12 cobranças simultâneas observadas no gateway (limite 4)
RESULTADO: FALHA (1 violações em 1 categoria(s))
```

Cada violação aparece sob o nome da sua categoria, entre colchetes, com a quantidade encontrada e alguns exemplos que identificam os compradores e os assentos envolvidos. O código de saída do programa é `0` se não houver violações, `1` se houver violações, ou `2` se algum arquivo não puder ser lido ou estiver mal formatado.

Cada categoria, descrita a seguir, corresponde a uma regra do serviço:

| Categoria | O que verifica |
| :-------- | :------------- |
| `completude` | Todas as operações da carga foram executadas e registradas exatamente uma vez, e a execução terminou |
| `assento-vendido-uma-vez` | Nenhum assento foi vendido duas vezes |
| `reserva-exclusiva` | Dois compradores nunca mantêm reserva do mesmo assento ao mesmo tempo |
| `reserva-em-assento-vendido` | Nenhuma reserva é concedida depois da venda |
| `operacao-sem-reserva`, `operacao-apos-expiracao` | Compra e liberação bem-sucedidas exigem reserva do próprio comprador, ainda válida |
| `rejeicao-indevida` | Nenhum `TAKEN`, `LIMIT` ou `NOHOLD` sem justificativa possível (por exemplo, reserva vencida que nunca foi liberada) |
| `limite-de-reservas` | Nenhum comprador excede `max_holds` |
| `limite-de-pagamentos` | Nunca há mais de `max_payments` cobranças simultâneas no *gateway* |
| `pagamento` | Cada compra concluída tem exatamente uma cobrança, e não há nenhuma cobrança sem compra associada |
| `mapa-de-assentos` | Os totais de `view` somam o tamanho do setor e o número de assentos com estado *vendido* é compatível com o *log* |
| `contadores` | `stats()` coincide com o registrado no *log* |

Cada operação é registrada com o instante em que a chamada começou e o instante em que terminou, mas o seu efeito real ocorreu em algum ponto dentro desse intervalo, o que o *log* não revela. Quando as chamadas de dois compradores se sobrepõem, ambas as ordens podem ser válidas. Por isso, o validador só aponta uma violação quando nenhuma ordem possível a explica. Exemplo: a pessoa compradora $A$ recebe `HELD` para o assento 17 em uma chamada que termina no instante 5 ms e a pessoa compradora $B$ recebe `HELD` para o mesmo assento em uma chamada que começa em 20 ms e termina em 25 ms. Com `ttl_ms` de 200, a reserva da pessoa $A$ continuava válida durante toda a chamada da pessoa $B$ e a primeira não liberou nem comprou o assento antes disso. Não há ordem possível em que ambos sejam atendidos corretamente; a violação é, portanto, evidente. Se a chamada da pessoa $B$ tivesse começado depois de 205 ms, a reserva da pessoa $A$ já teria vencido e nada teria sido apontado.

### Sumarizador

O sumarizador é um programa, também implementado em Python (arquivo [`summarize_log.py`](tools/summarize_log.py)), que resume o *log* considerando métricas como tempo, vazão (*throughput*) e duração por operação, as quais serão úteis na etapa de [experimentação](#experimentação) deste trabalho. O sumarizador lê o *log* de uma execução e apenas o resume.

Para utilizar o sumarizador, o seguinte comando deve ser utilizado:

```bash
python3 tools/summarize_log.py events.log
```

O sumarizador exibe como resultado o número de *threads*, o tempo total (`wall_ns` da linha `RUN` do arquivo de *log*, convertido para segundos), o número de sessões e a vazão. Além disso, exibe uma tabela com cada tipo de operação (`V`, `H`, `P`, `R`) e cada resultado, a quantidade de chamadas e a distribuição da duração de cada chamada (fim menos início), em milissegundos. Como medidas-resumo, são calculados os valores de média, de mediana (p50), dos percentis 95 e 99 (p95, p99) e o valor máximo.

Um exemplo de resultado da execução do sumarizador seria:

```text
threads: 32  tempo: 1.184 s  sessões: 400  vazão: 337.7 sessões/s, 2047 ops/s

op  resultado        n     média       p50       p95       p99       máx   (ms)
H   HELD           387     0.019     0.004     0.016     0.028     4.995
H   TAKEN          351     0.002     0.001     0.005     0.017     0.028
P   SOLD           236    10.164    10.148    10.293    10.439    10.610
V   OK            1043     0.019     0.016     0.038     0.061     0.105
```

Nesse exemplo, as 387 reservas concedidas (`H` `HELD`) levaram, em média, 0,019 ms; porém, a mais lenta levou 4,995 ms. Esse contraste entre a média e o máximo costuma indicar espera por uma trava ou atraso de escalonamento. Uma compra (`P` `SOLD`) levou cerca de 10 ms porque inclui a cobrança no *gateway* (`payment_ms`) e, se houver fila, a espera pela permissão de cobrança. Os percentis mostram a cauda da distribuição, que a média esconde.

## Tarefas

### Implementação

Implemente o trabalho em **Java, C++ ou Python, obrigatoriamente**. Após clonar este repositório, mantenha **apenas o diretório da linguagem de programação escolhida**; os demais, das outras linguagens, devem ser **removidos**. Como mencionado anteriormente, os esqueletos compilam, mas lançam exceções nos métodos a implementar.

**Serviço.** Implemente a interface `TicketService` em **duas versões**, que diferem pela granularidade da sincronização, isto é, por quanto do estado compartilhado cada trava protege:

1. *Coarse* (`CoarseTicketService`, opção `--impl coarse`): Nesta versão, um único mecanismo de exclusão mútua (um *lock* ou monitor) protege **todo** o estado do serviço (assentos, reservas de cada pessoa compradora, contadores e consulta ao mapa), de modo que qualquer operação de qualquer pessoa compradora precisa adquiri-lo. Esta é a versão mais simples de implementar e de provar correta, e serve como referência de corretude e como *baseline* dos experimentos. O limite de cobranças simultâneas (`max_payments`) continua sendo necessário e pode ser garantido com um semáforo, que não conta como refinamento.
2. *Fine* (`FineTicketService`, opção `--impl fine`): Nesta versão, o estado é dividido de modo que operações independentes não precisem esperar umas pelas outras. Para ser considerada fina, a versão deve satisfazer pelo menos uma das condições a seguir, em relação à *coarse*:

- Estado particionado: há travas distintas para partes distintas do estado (por exemplo, por assento ou por setor), de modo que compradores que disputam assentos diferentes não se bloqueiam.
- Leitura sem exclusão mútua total: a operação `view` não bloqueia as demais operações, nem as outras consultas, por exemplo, com um *lock* de leitura e escrita ou via operações atômicaso.

É importante destacar que a versão *fine* não necessariamente é melhor em termos de desempenho. Dessa forma, se essa versão não for mais rápida que a *coarse* em alguma situação, isso é um resultado válido, desde que explicado no relatório.

No processo de implementação, deverão ser tomadas as seguintes decisões:

- como e quando as reservas vencidas são liberadas, por exemplo, ao serem encontradas por uma operação, ou por uma *thread* auxiliar; se houver thread auxiliar, ela deve ser encerrada em `close()`;
- como o limite de `max_payments` é garantido;
- como o mapa de assentos é lido sem interferir nos processos de reserva e de compra;
- como os contadores são mantidos.

***Pipeline*** (`Main`). O esqueleto executa tudo sequencialmente. O *loop* deve ser substituído por um *pipeline* concorrente com:

- um **produtor**, que entrega as sessões da carga, na ordem do arquivo, ao número de *threads* definido na opção `--workers`;
- uma **fila limitada** com, no máximo, `queue_capacity` sessões esperando; quando a fila está cheia, o produtor espera, e quando está vazia, as *threads* esperam;
- o número de **threads** definido pela opção `--workers`, cada *thread* com o seu objeto `SessionRunner` e a sua lista de registros, que processam uma sessão inteira por vez;
- uma **porta de largada**: o produtor, as *threads* e a *thread* principal começam juntos, e o tempo medido (`wall`) vai da abertura da porta até o término de todas as sessões, sem incluir a criação das *threads*;
- **encerramento correto**: as *threads* terminam quando as sessões terminam, sem depender de pausas ou limites de tempo.

A implementação deve considerar as seguintes restrições:

- As *threads* devem ser criadas explicitamente, **não sendo permitido usar *pools* de *threads***;
- Em Python, deverão ser utilizadas *threads* (módulo `threading`), não processos.
- O código fornecido e o formato do arquivo de *log* **não devem ser alterados**.

Para executar os programas, os seguintes comandos devem ser utilizados de acordo com a linguagem de programação escolhida para a implementação:

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

***Warm-up* (Java):** O esqueleto de [`Main.java`](java/src/Main.java) também aceita a opção `--warmup N` (valor padrão `0`), usada na etapa de [experimentação](#experimentação). Essa opção faz com que o *pipeline* seja executado `N` vezes sobre as primeiras 100 sessões da carga, descartando o resultado, antes da execução medida. Não é necessário implementar essa opção, mas sim apenas garantir que a execução do *pipeline* (método `execute`) crie tudo o que usa (serviço, *gateway*, filas e *threads*) a cada chamada e não deixe estado de uma chamada para a próxima. Em C++ e em Python, essa opção não é necessária e, por isso, não existe no esqueleto para essas linguagens.

### Experimentação

A tarefa de experimentação consiste em realizar sucessivas execuções do programa implementado, buscando responder às seguintes perguntas:

- Quanto o aumento do número de *threads* reduz o tempo de execução e a partir de que ponto deixa de reduzir?
- A versão refinada (*fine*) é realmente superior à versão simples (*coarse*)? Em que situação e por quanto?
- A resposta muda entre uma carga branda (*realistic*) e uma carga intensa (*stress*)?
- Uma decisão de projeto específica (por exemplo, como as reservas vencidas são liberadas) faz diferença?

**Toda execução cujo resultado for considerado deve ter sido validada pelo validador**, e o relatório deve informar quantas execuções foram aprovadas. O resultado de uma execução com violações não é válido, pois mede um programa incorreto.

#### Métricas

As seguintes variáveis devem ser medidas na experimentação:

| Métrica | Definição | Origem |
| :------ | :-------- | :----- |
| Tempo (`wall`) | Tempo, em segundos, desde a abertura da porta de largada até o término de todas as sessões, desconsiderando os tempos de criação das *threads* e o da leitura da carga. | Campo `wall_ns` da linha `RUN` do *log* (em nanossegundos), que também aparece na saída do validador e do sumarizador de *log* |
| Vazão (*throughput*) | Sessões atendidas por tempo em segundos | Calculada pelo validador e pelo sumarizador de *log* |
| Aceleração (*speed-up*) | $S(n) = T(1) / T(n)$, em que $T(n)$ é o tempo médio com $n$ *threads*, da mesma versão do serviço e da mesma carga | Calculada a partir das médias |
| Tempo por operação | Duração de cada chamada, por tipo de operação e resultado | Linhas `OP` do *log*, resumidas pelo sumarizador de *log* |

#### Fatores

Os experimentos a serem realizados neste trabalho tratam de combinações dos três fatores a seguir. Os fatores são os elementos a serem controlados, e as métricas listadas anteriormente são as variáveis a serem observadas.

| Fator | Níveis | Como é controlado |
| :---- | :----- | :---------------- |
| Número de threads | Pelo menos cinco valores, incluindo 1 e um valor maior que o número de núcleos de processamento disponíveis na máquina de execução (por exemplo, 1, 2, 4, 8 e 16) | Opção `--workers` do programa. Com 1 thread, o *pipeline* opera sequencialmente e serve como base de comparação. |
| Versão do serviço | `coarse` e `fine` | Opção `--impl` do programa |
| Perfil de carga | `realistic` e `stress` | Arquivo de carga gerado com `--profile` |

Para os experimentos, **as cargas devem ser geradas uma única vez** e os mesmos arquivos devem ser sempre utilizados em todas as execuções. Para que o total seja viável, os seguintes comandos devem ser utilizados:

```bash
python3 tools/generate_workload.py --profile realistic --seed 1 --sessions 600  -o workloads/exp-realistic.txt
python3 tools/generate_workload.py --profile stress    --seed 1 --sessions 2000 -o workloads/exp-stress.txt
```

#### Experimentos a serem realizados

Devem ser realizados três experimentos conforme descritos a seguir:

| ID | Foco | Pergunta | O que varia | Elementos fixos | Execuções |
| -- | :--- | :------- | :---------- | :-------------- | :-------- |
| E1 | Escalabilidade | Como o tempo de execução varia com o número de *threads*? | Número de *threads* (5 valores) | Versão e perfil | 2 versões × 2 perfis × 5 valores × 10 repetições = 200 |
| E2 | Comparação das versões | A versão *fine* é superior à *coarse*? Em que condições? | Versão | Número de *threads* e perfil | 0 (usa os dados do experimento E1) |
| E3 | Tempo por operação | Onde o tempo é gasto no serviço? | Versão | Uma configuração por versão | 0 (usa os *logs* do experimento E1) |

**Experimentos E1 e E2 - Escalabilidade e comparação das versões:** Estes experimentos dizem respeito à mesma coleta de dados, porém sob duas perspectivas distintas que, juntas, respondem à pergunta central deste trabalho. No experimento E1, a matriz 2 versões × 2 perfis × 5 valores deve ser executada 10 vezes, e cada versão deve ser examinada separadamente quanto à variação do tempo e da vazão em função do número de *threads*, devendo ainda ser calculado o *speed-up* e identificada a situação em que ele deixa de crescer. No experimento E2, cada número de *threads* deve ser examinado separadamente, e as duas versões (*fine* e *coarse*) devem ser comparadas, calculando-se a razão entre os tempos médios e verificando-se se a diferença é maior que a variação (o desvio padrão). A pergunta não é só "qual é mais rápida", e sim em que condições a versão refinada compensa a complexidade extra. Há condições em que ela não compensa, e identificá-las é um resultado válido.

**Experimento E3 - Tempo por operação:** Para ao menos uma configuração de cada versão (por exemplo, o maior valor de `--workers` usado no experimento E1, no perfil `stress`), deve-se resumir o *log* com o sumarizador de *log* e comparar as durações das operações `view`, `hold` e `purchase` entre as duas versões. O tempo total indica quanto tempo o serviço leva, e esta análise mostra onde (por exemplo, se as operações de leitura ficam mais lentas quando as de escrita disputam o mesmo *lock*).

Os resultados decorrentes desses três experimentos devem constar no relatório (ver seção [Relato](#relato)). Para os experimentos E1 e E2, deve ser incluída uma tabela por perfil, com a média e o desvio padrão do tempo e da vazão de cada versão para cada número de *threads*, além de dois gráficos: um para o tempo (ou a vazão) em função do número de *threads*, com as duas versões, e outro para o *speed-up*. Para o experimento E3, deve ser incluída uma tabela com a distribuição das durações das operações na configuração escolhida. Em todos os casos, devem ser informados quantas execuções foram feitas e quantas passaram na validação.

#### Execução dos experimentos

Como o experimento E1 envolve centenas de execuções, é interessante automatizar sua execução; registrar os resultados manualmente é altamente desaconselhável. Por exemplo, pode ser elaborado um *script* (em *shell*, Python ou o que preferir) que, para cada configuração, executa o programa, executa o validador sobre o *log* e registra o tempo e se a validação passou.

Os *logs* também devem ser guardados, pois a análise do tempo por operação parte deles. Cada configuração (versão × perfil × número de threads) deve ser executada pelo menos **10 vezes**, e as execuções devem ser **alternadas**: em vez de fazer as 10 repetições de uma configuração e depois as da seguinte, elas **devem ser intercaladas** (por exemplo, *coarse*, *fine*, *coarse*, e assim sucessivamente), de modo que qualquer oscilação da máquina ao longo do tempo (temperatura, outros processos) afete ambas as versões igualmente.

Para controlar o ambiente de execução, recomenda-se que outros programas em execução sejam encerrados e que o computador seja conectado à tomada de energia e não seja utilizado durante as medições. O relatório deve registrar o processador, o número de núcleos de processamento, a quantidade de memória RAM instalada, o sistema operacional em execução, a versão da linguagem e do compilador (ou da máquina virtual Java, se for o caso) e as opções utilizadas.

Nas primeiras execuções, a máquina virtual Java ainda interpreta e compila o código, fazendo com que os tempos sejam maiores e mais variáveis e, consequentemente, distorcendo a média. Por isso, em Java, toda execução do experimento deve usar `--warmup N`: o programa executa o *pipeline* `N` vezes, sobre as primeiras 100 sessões e sem efetivamente medir, e somente a partir da próxima execução mede e grava o *log*. Para que o aquecimento não encareça demais as execuções com poucas *threads*, ele pode ser feito sobre uma carga reduzida (por exemplo, as primeiras 100 sessões do arquivo) em vez da carga completa, a escolha devendo ser reportada informada no relatório. Dessa forma, cada execução continua produzindo **um único tempo e um único *log***, exatamente como em C++ e em Python. Em C++ e em Python, não é necessário aquecimento, mas a primeira execução pode ser mais lenta por efeitos de *cache* do sistema, então é válido descartar uma execução inicial antes de começar a coleta, também informando isso no relatório.

#### Tratamento dos dados

Devem ser calculados a média e o desvio padrão amostral do tempo e da vazão para cada configuração. O desvio padrão indica a variabilidade: uma diferença entre versões menor do que o desvio padrão não pode ser considerada significativa. Se uma execução destoar muito das demais, não a remova: mantenha-a, informe-a e, se a causa for identificada, explique-a. Apresente as médias com o desvio padrão, por exemplo, como barras de erro nos gráficos.

O tempo total indica quanto tempo o serviço leva, mas não onde. Para isso, deve-se utilizar o sumarizador de *log*, que fornece a duração de cada tipo de operação e de cada resultado. Ele deve ser utilizado para tentar explicar as diferenças que o tempo total mostrou. Por exemplo, a duração das operações `view` e `hold` tende a aumentar com o número de *threads*, e a da operação `purchase` inclui o tempo da cobrança mais a espera pela permissão de cobrança. Os valores altos nas caudas (p99 e máximo) podem revelar esperas por *locks* ou escalonamento que a média esconderia.

### Relato

Uma vez realizadas as tarefas de implementação e de experimentação, deverá ser elaborado um relatório contendo, no mínimo, as seguintes seções:

1. **Identificação e ambiente**: nomes dos membros da equipe envolvida, linguagem de programação empregada, o ambiente de execução utilizado nas atividades de implementação e de experimentação e as instruções para compilação e execução do programa.
2. **Projeto da sincronização**: descrição do mecanismo de sincronização escolhido nas versões *coarse* e *fine*, da justificativa da escolha e das alternativas consideradas e descartadas.
3. **Metodologia**: o que foi medido nos experimentos, como, quantas repetições, o tratamento do *warm-up* (no caso de Java, o valor de `--warmup` e a carga utilizada no aquecimento) e como a validação foi realizada.
4. **Resultados**: tabelas e gráficos com média e desvio padrão.
5. **Análise**: explicação dos resultados, e não uma mera descrição deles, buscando responder às seguintes perguntas:

   - Por que a versão *fine* é superior (ou não) à versão *coarse* em cada perfil?
   - O que acontece quando o número de *threads* excede o número de núcleos de processamento disponíveis?
   - Por que o perfil *realistic* esconde diferenças que o perfil *stress* revela?
   - Houve algum resultado que contrariou as expectativas?
   - Em Python, qual o efeito do GIL nas medições?

6. **Limitações e trabalhos futuros**: o que os testes realizados não cobrem e o que poderia ser feito com mais tempo.

## Autoria e política de colaboração

Este trabalho deverá ser realizado em equipe composta por **dois estudantes**, sendo importante dividir as tarefas igualmente entre os integrantes, que devem ser capazes de explicar qualquer trecho do código e do relatório. Após a implementação da solução, o arquivo [`author.md`](https://github.com/ufrn-concprog/ticket-sync/tree/master/author.md) presente no repositório deverá ser editado para incluir as informações de identificação (nome completo e endereço de *e-mail*) dos integrantes da equipe.

O trabalho em cooperação entre os estudantes da turma é estimulado, sendo admissível a discussão de ideias e estratégias. Contudo, tal interação não deve ser entendida como permissão para utilizar parte do código-fonte de colegas, o que pode configurar plágio. **Trabalhos copiados, no todo ou em parte, de outros colegas ou da Internet, ou ainda gerados por ferramentas de Inteligência Artificial, serão anulados e receberão nota zero.**

## Entrega

O sistema de controle de versão [Git](https://git-scm.com) será utilizado para viabilizar a entrega da implementação. Para possibilitar a associação de repositórios Git a cada equipe e reuni-los sob a mesma infraestrutura, foi criada uma atividade (*assignment*) no [Classroom 50](https://classroom50.org/), cujo *link* de acesso está disponível na Turma Virtual do SIGAA. No processo de ingresso na atividade, **cada equipe deve ser obrigatoriamente nomeada com o primeiro nome de cada integrante da equipe**, por exemplo, `Maria&Joao`.

A fim de garantir a boa manutenção do repositório, deve-se ainda configurar corretamente o arquivo `.gitignore` para desconsiderar arquivos que não devam ser versionados, como os executáveis gerados pela compilação do código-fonte, os arquivos de carga e os *logs*. Por outro lado, devem ser mantidos o diretório [`tools`](tools/) e o da linguagem escolhida.

A entrega deste trabalho deverá ser realizada até as **23:59 do dia 9 de novembro de 2026** no respectivo repositório Git da equipe. O relatório, em formato PDF, deverá ser enviado por meio da opção *Tarefas* da Turma Virtual do SIGAA, juntamente com o endereço do repositório, no campo *Comentários*. **Um único membro da equipe deve realizar esse envio**, e não serão aceitos envios por outros meios ou em repositórios que não os descritos nesta especificação. **Apenas o arquivo PDF do relatório deve ser enviado via SIGAA**.

## Avaliação

A avaliação do trabalho contabilizará nota de até 10,0 pontos na 2ª Unidade da disciplina e será feita de acordo com os seguintes critérios:

| Critério | Pontos |
| :------- | -----: |
| Corretude: o validador não aponta violações nas execuções de avaliação | 3,0 |
| Projeto da sincronização: adequação e uso correto dos mecanismos, granularidade, versão *fine* de fato refinada, *pipeline* e encerramento corretos | 2,0 |
| Rigor experimental: variação do número de *threads*, duas versões, dois perfis, 10 repetições com média e desvio padrão calculados, consideração de *warm-up* em Java, uso do validador, ambiente informado | 2,0 |
| Qualidade do relatório: justificativas, interpretação dos resultados, limitações | 2,5 |
| Código e repositório: histórico de commits razoável, organização do código | 0,5 |

Na avaliação dos critérios acima, poderão ser aplicadas reduções de nota nos seguintes casos:

- Violação de uma regra de segurança nas execuções de avaliação (por exemplo, assento vendido duas vezes) reduz a nota de corretude proporcionalmente ao número de execuções afetadas. Um programa que trava ou não termina dentro do limite de tempo tem sua execução considerada inválida.
- Usar um mecanismo que funciona, mas sem justificar por que é adequado, vale menos do que usar um mecanismo mais simples, bem justificado.
- Relatórios cujas conclusões não se sustentam com base nos dados apresentados perdem pontos no critério de qualidade do relatório.

## Dúvidas e informações

Caso haja qualquer dúvida, questionamento ou necessidade de informação adicional, bem como identificados erros no gerador, no validador ou em qualquer código-fonte fornecido, enviar um *e-mail* para <everton.cavalcante@ufrn.br>. As correções nos artefatos serão disponibilizadas a toda a turma com a maior brevidade possível.
