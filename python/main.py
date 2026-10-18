"""
Ponto de entrada do programa.

O esqueleto atual processa as sessões sequencialmente na thread principal. A
implementação completa deve substituir esse laço pelo pipeline concorrente
descrito na especificação.
"""

import argparse

from harness import (PaymentGateway, SessionRunner, load_workload, now_ns, write_log)
from ticket_service import IMPLEMENTATIONS


def main():
    """Analisa argumentos e executa as sessões da carga selecionada.

    Lê os parâmetros e sessões do arquivo de carga, cria o gateway e a
    implementação solicitada do serviço, executa as sessões, fecha o serviço
    e grava o log de eventos.

    Raises:
        OSError: Se a carga ou o log não puderem ser lidos ou escritos
        ValueError: Se o arquivo de carga não tiver parâmetros válidos
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("workload")
    ap.add_argument("-w", "--workers", type=int, default=16, 
                    help="número de threads trabalhadoras")
    ap.add_argument("--impl", choices=sorted(IMPLEMENTATIONS), default="coarse")
    ap.add_argument("-o", "--output", default="events.log")
    args = ap.parse_args()

    params, sessions = load_workload(args.workload)
    gateway = PaymentGateway(params)
    service = IMPLEMENTATIONS[args.impl](params, gateway)
    service.start()

    # Um SessionRunner e uma lista por thread
    out = []
    runner = SessionRunner(service, out)

    t0 = now_ns()

    # TODO: 
    # Substituir pelo pipeline concorrente (porta de largada, produtor, fila limitada
    # de capacidade params.queue_capacity, args.workers threads, encerramento).
    for session in sessions:
        runner.run(session)
    wall = now_ns() - t0

    service.close()
    write_log(args.output, [out], gateway, service.stats(), args.workers, wall)
    print(f"{len(sessions)} sessoes em {wall / 1e9:.3f} s -> {args.output}")


if __name__ == "__main__":
    main()
