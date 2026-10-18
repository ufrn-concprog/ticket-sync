"""Gerador de carga.

Produz um arquivo de texto que descreve, de forma determinística, 
as sessões de compradores que chegam ao serviço.
O mesmo arquivo é lido pelas versões em Java, C++ e Python e pelo validador.

Uso:
    python3 tools/generate_workload.py --profile realistic --seed 1 -o workloads/realistic-1.txt
    python3 tools/generate_workload.py --profile stress --seed 7 --sessions 5000 -o workloads/stress-7.txt

Formato do arquivo (uma linha por registro; '#' inicia comentário):
    PARAMS seats=2000 section_size=100 max_holds=4 ttl_ms=200 ...
    SESSION <id> <op> <op> ...
onde cada <op> ocupa um ou dois tokens:
    V <setor>           consultar o mapa de assentos de um setor
    H <assento>         reservar (hold) um assento
    P <assento> ok|bad  comprar um assento reservado (pagamento aceito ou recusado)
    R <assento>         liberar uma reserva própria
    T <ms>              tempo de reflexão do comprador (a sessão dorme)
"""

import argparse
import random
import sys
from contextlib import nullcontext

#: Parâmetros e contagens padrão de sessões para cada perfil de geração
PROFILES = {
    # Tempos realistas: o gargalo é o tempo de reflexão, a contenção é moderada
    "realistic": {
        "seats": 2000, "section_size": 100, "max_holds": 4, "ttl_ms": 200, 
        "payment_ms": 10, "max_payments": 8, "grace_ms": 50, "queue_capacity": 64,
        "think": (5, 120), "slow": (250, 400), "sessions": 3000,
    },
    # Sem pausas longas e com pico de demanda: o gargalo é a sincronização
    "stress": {
        "seats": 2000, "section_size": 100, "max_holds": 4, "ttl_ms": 100, 
        "payment_ms": 2, "max_payments": 4, "grace_ms": 50, "queue_capacity": 32,
        "think": (0, 30), "slow": (110, 150), "sessions": 20000,
    },
}

#: Proporção de solicitações de assentos direcionadas ao primeiro setor (0)
HOT_FRACTION = 0.6

#: Tamanhos de grupos candidatos e seus pesos de amostragem relativos.
GROUP_SIZES = [1, 2, 3, 4]
GROUP_WEIGHTS = [35, 35, 15, 15]

#: Perfis de compradores e seus pesos de amostragem relativos.
ARCHETYPES = ["browser", "buyer", "abandoner", "slow", "greedy"]
ARCHETYPE_WEIGHTS = [25, 40, 18, 12, 5]

#: Probabilidade de falha de pagamento
BAD_CARD_PROBABILITY = 0.05

def pick_seat(rng, p):
    """
    Escolhe um assento, direcionando uma proporção das solicitações ao 
    primeiro setor.

    Args:
        rng: Gerador de números aleatórios usado para a escolha
        p: Parâmetros do perfil de carga

    Returns:
        Índice do assento.
    """
    if rng.random() < HOT_FRACTION:
        return rng.randrange(0, min(p["section_size"], p["seats"]))
    return rng.randrange(0, p["seats"])


def pick_block(rng, p, size):
    """Escolhe um bloco contíguo de assentos dentro de um setor.

    Args:
        rng: Gerador de números aleatórios usado para a escolha
        p: Parâmetros do perfil de carga
        size: Número de assentos no bloco

    Returns:
        A list of consecutive zero-based seat indices.
    """
    start = pick_seat(rng, p)
    sec = start // p["section_size"]
    hi = min((sec + 1) * p["section_size"], p["seats"])
    start = min(start, hi - size)
    return list(range(start, start + size))


def section_of(p, seat):
    """Retorna o índice do setor que contém um assento.

    Args:
        p: Parâmetros do perfil de carga
        seat: Índice do assento

    Returns:
        Índice do setor
    """
    return seat // p["section_size"]

def n_sections(p):
    """Calcula o número de setores necessários para os assentos do perfil.

    Args:
        p: Parâmetros do perfil de carga

    Returns:
        Número de setores, incluindo um setor final potencialmente parcial.
    """
    return (p["seats"] + p["section_size"] - 1) // p["section_size"]


def think(rng, rng_range):
    """Escolhe um atraso de pensamento aleatório dentro de um intervalo

    Args:
        rng: Gerador de números aleatórios usado para a escolha
        rng_range: Atrasos mínimo e máximo em milissegundos

    Returns:
        Atraso em milissegundos.
    """
    lo, hi = rng_range
    return rng.randint(lo, hi)


def build_session(rng, p, archetype):
    """Monta a lista de operações para uma sessão de comprador.

    Sessões do perfil "navegador" só visualizam seções. Outros perfis escolhem um 
    grupo de assentos e depois compram, liberam, abandonam ou tentam comprar 
    muito tardiamente de acordo com seu comportamento.

    Args:
        rng: Gerador de números aleatórios usado para todas as escolhas da sessão
        p: Parâmetros do perfil de carga
        archetype: Categoria de comportamento do comprador de :data:`ARCHETYPES`

    Returns:
        Lista de tuplas de operações. Cada tupla contém um código de operação e
        seus argumentos; operações de pensamento são representadas como ``("T", ms)``.
    """
    ops = []
    if archetype == "browser":
        for _ in range(rng.randint(3, 10)):
            sec = (0 if rng.random() < 0.4 else rng.randrange(n_sections(p)))
            ops.append(("V", sec))
        return ops

    size = rng.choices(GROUP_SIZES, GROUP_WEIGHTS)[0]
    size = min(size, p["max_holds"])
    if archetype == "greedy":   # tenta reservar além do limite por comprador
        size = p["max_holds"] + rng.randint(1, 2)
    seats = pick_block(rng, p, size)
    for _ in range(rng.randint(1, 2)):
        ops.append(("V", section_of(p, seats[0])))
    for s in seats:
        ops.append(("H", s))

    if archetype in ("buyer", "greedy"):
        ops.append(("T", think(rng, p["think"])))
        for s in seats:
            card = "bad" if rng.random() < BAD_CARD_PROBABILITY else "ok"
            ops.append(("P", s, card))
    elif archetype == "abandoner":
        ops.append(("T", think(rng, p["think"])))
        if rng.random() < 0.4:
            for s in seats:
                ops.append(("R", s))
        # caso contrário a sessão simplesmente desiste: a reserva expira sozinha
    else:  # slow: demora mais que o TTL e tenta comprar tarde demais
        ops.append(("T", think(rng, p["slow"])))
        for s in seats:
            ops.append(("P", s, "ok"))
    return ops


def fmt_op(op):
    """Formata uma tupla de operação como tokens de carga separados por espaços.

    Args:
        op: Código de operação e seus argumentos

    Returns:
        Representação textual de uma única linha da operação.
    """
    return " ".join(str(x) for x in op)


def main():
    """Processa as opções da linha de comando e escreve a carga gerada.

    A saída é escrita na saída padrão por padrão ou para o caminho fornecido 
    com a opção ``-o``/``--output``. Um gerador local com semente faz com que 
    a saída da carga seja repetível para argumentos idênticos.
    """
    ap = argparse.ArgumentParser(description=__doc__, 
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", choices=sorted(PROFILES), default="realistic")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--sessions", type=int, 
                    help="número de sessões (padrão depende do perfil)")
    ap.add_argument("-o", "--output", default="-", 
                    help="arquivo de saída (padrão: saída padrão)")
    args = ap.parse_args()

    p = dict(PROFILES[args.profile])
    n_sessions = args.sessions if args.sessions is not None else p["sessions"]
    if n_sessions < 1:
        ap.error("--sessions deve ser >= 1")
    rng = random.Random(args.seed)

    with (
        nullcontext(sys.stdout)
        if args.output == "-"
        else open(args.output, "w", encoding="utf-8")
    ) as out:
        out.write(f"# ticket-sync workload v1 profile={args.profile} " \
                  f"seed={args.seed} sessions={n_sessions}\n")
        out.write(
            "PARAMS seats={seats} section_size={section_size} " \
            "max_holds={max_holds} ttl_ms={ttl_ms} "
            "payment_ms={payment_ms} max_payments={max_payments} grace_ms={grace_ms} "
            "queue_capacity={queue_capacity}\n".format(**p)
        )
        for sid in range(n_sessions):
            archetype = rng.choices(ARCHETYPES, ARCHETYPE_WEIGHTS)[0]
            ops = build_session(rng, p, archetype)
            out.write(f"SESSION {sid} " + " ".join(fmt_op(o) for o in ops) + "\n")

if __name__ == "__main__":
    main()
