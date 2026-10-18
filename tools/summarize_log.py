"""Resume um log de execução.

Uso:
    python3 tools/summarize_log.py events.log

Mostra o tempo total e a vazão (a partir da linha RUN) e, para cada operação e
resultado, a quantidade de chamadas e a distribuição da duração (fim - início),
em milissegundos: média, mediana (p50), p95, p99 e máximo.

Para a operação P, a duração inclui a espera pela permissão de cobrança e a
própria cobrança. Para as demais, é o tempo de resposta do serviço.
"""

import collections
import math
import sys


def percentile(sorted_vals, p):
    """Retorma um percentil usando o método de classificação mais próxima.

    Args:
        sorted_vals: Valores ordenados em ordem ascendente.
        p: Percentil solicitado, convencionalmente entre 0 e 100.

    Returns:
        Valor no percentil solicitado. Valores de ``p`` fora do intervalo 
        convencional são limitados ao primeiro ou último item.

    Raises:
        IndexError: Se ``sorted_vals`` for vazio
    """
    k = max(0, min(len(sorted_vals) - 1, math.ceil(p / 100 * len(sorted_vals)) - 1))
    return sorted_vals[k]


def main():
    """
    Resume latências e vazão de operações a partir de um log de execução.

    Lê o caminho do log a partir de ``sys.argv``, imprime métricas agregadas de 
    execução e distribuições de latência por operação, e retorna um código de 
    saída do processo.

    Returns:
        ``0`` quando um caminho de log tiver sido fornecido, ou ``2`` para uso incorreto.

    Raises:
        OSError: Se o log especificado não puder ser aberto.
        ValueError: Se um campo numérico obrigatório no log estiver mal formado.
    """
    if len(sys.argv) != 2:
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2
    durations = collections.defaultdict(list)
    run, sessions = None, set()
    with open(sys.argv[1], encoding="utf-8") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if c[0] == "OP":
                durations[(c[3], c[7])].append((int(c[6]) - int(c[5])) / 1e6)
                sessions.add(c[1])
            elif c[0] == "RUN":
                run = {k: int(v) for k, v in (t.split("=") for t in c[1:])}
    total_ops = sum(len(v) for v in durations.values())
    if run:
        wall = run["wall_ns"] / 1e9
        print(f"threads: {run['workers']}  tempo: {wall:.3f} s  sessões: {len(sessions)}  "
              f"vazão: {len(sessions) / wall:.1f} sessões/s, {total_ops / wall:.0f} ops/s")
    else:
        print("aviso: log sem linha RUN (execução incompleta)")
    print()
    print(f"{'op':<4}{'resultado':<10}{'n':>8}{'média':>10}{'p50':>10}" \
          f"{'p95':>10}{'p99':>10}{'máx':>10}   (ms)")
    for (kind, res) in sorted(durations):
        v = sorted(durations[(kind, res)])
        print(f"{kind:<4}{res:<10}{len(v):>8}{sum(v) / len(v):>10.3f}" \
              f"{percentile(v, 50):>10.3f}{percentile(v, 95):>10.3f}" \
                f"{percentile(v, 99):>10.3f}{v[-1]:>10.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
