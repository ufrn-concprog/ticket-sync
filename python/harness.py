"""Infraestrutura compartilhada de execução do serviço de bilheteria.

O módulo fornece tipos para representar parâmetros, operações e sessões;
carrega arquivos de carga; simula o gateway de pagamento; executa operações
das sessões e grava o log consumido por ``tools/validate_log.py``.
"""

import threading
import time
from dataclasses import dataclass

# Resultados retornados pelo serviço e registrados no log.
HELD = "HELD"          #: A reserva foi criada.
TAKEN = "TAKEN"        #: O assento já está reservado ou vendido por outra pessoa compradora
LIMIT = "LIMIT"        #: A pessoa compradora comprador atingiu o limite de reservas
ALREADY = "ALREADY"    #: A pessoa compradora já tem uma reserva para o assento
SOLD = "SOLD"          #: O assento foi vendido
NOHOLD = "NOHOLD"      #: A pessoa compradora não tem uma reserva válida para o assento
DECLINED = "DECLINED"  #: O pagamento foi recusado
RELEASED = "RELEASED"  #: A reserva foi liberada

_ORIGIN = time.monotonic_ns()


def now_ns():
    """
    Retorna o tempo monotônico decorrido desde o início do processo.

    Este relógio também deve ser usado no serviço, por exemplo, ao calcular a 
    validade das reservas (time-to-live, TTL).

    Returns:
        Tempo decorrido em nanossegundos
    """
    return time.monotonic_ns() - _ORIGIN


@dataclass(frozen=True)
class Params:
    """Parâmetros imutáveis da carga e do serviço

    Attributes:
        seats: Quantidade total de assentos
        section_size: Quantidade de assentos por setor
        max_holds: Limite de reservas simultâneas válidas por pessoa compradora
        ttl_ms: Validade das reservas em milissegundos
        payment_ms: Duração simulada de cada cobrança, em milissegundos
        max_payments: Limite de cobranças simultâneas que o serviço deve impor
        grace_ms: Tolerância para reconhecer reservas vencidas, em milissegundos
        queue_capacity: Quantidade máxima de sessões aguardando na fila
    """

    seats: int
    section_size: int
    max_holds: int
    ttl_ms: int
    payment_ms: int
    max_payments: int
    grace_ms: int
    queue_capacity: int

    @property
    def ttl_ns(self):
        """Validade da reserva convertida para nanossegundos"""
        return self.ttl_ms * 1_000_000

    def section_of(self, seat):
        """Retorna o setor que contém determinado assento

        Args:
            seat: Índice do assento, começando em zero

        Returns:
            Índice do setor, começando em zero
        """
        return seat // self.section_size

    def section_range(self, section):
        """Retorna o intervalo de assentos pertencente a um setor

        Args:
            section: Índice do setor, começando em zero

        Returns:
            Tupla ``(início, fim)`` com limite inferior inclusivo e superior
            exclusivo. O limite superior é reduzido para o tamanho do evento
            quando o último setor é parcial.
        """
        lo = section * self.section_size
        return lo, min(lo + self.section_size, self.seats)


@dataclass(frozen=True)
class Op:
    """Operação individual de uma sessão

    Attributes:
        kind: Código da operação: ``V``, ``H``, ``P``, ``R`` ou ``T``.
        arg: Setor para ``V``, assento para ``H``/``P``/``R`` ou duração em
            milissegundos para ``T``
        card_ok: Indica se o pagamento deve ser aceito; usado por ``P``
    """

    kind: str          # 'V', 'H', 'P', 'R' ou 'T'
    arg: int           # setor (V), assento (H, P, R) ou milissegundos (T)
    card_ok: bool = True


@dataclass(frozen=True)
class Session:
    """Sessão de operações de uma pessoa compradora

    Attributes:
        id: Identificador da pessoa compradora
        ops: Tupla imutável de operações na ordem de execução
    """

    id: int     # também é o identificador da pessoa compradora (buyer)
    ops: tuple


def load_workload(path):
    """Carrega parâmetros e sessões de um arquivo de carga.

    Linhas vazias e comentários iniciados por ``#`` são ignorados.

    Args:
        path: Caminho do arquivo de carga

    Returns:
        Tupla ``(params, sessions)`` com um :class:`Params` e uma lista de
        :class:`Session` na ordem em que aparecem no arquivo

    Raises:
        OSError: Se o arquivo não puder ser aberto ou lido
        ValueError: Se faltar o registro ``PARAMS`` ou algum valor não puder ser
            convertido para inteiro
        KeyError: Se um parâmetro obrigatório estiver ausente
    """
    params, sessions = None, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tok = line.split()
            if tok[0] == "PARAMS":
                kv = dict(t.split("=") for t in tok[1:])
                params = Params(**{k: int(v) for k, v in kv.items()})
            elif tok[0] == "SESSION":
                ops, i = [], 2
                while i < len(tok):
                    k = tok[i]
                    if k == "P":
                        ops.append(Op("P", int(tok[i + 1]), tok[i + 2] == "ok"))
                        i += 3
                    else:
                        ops.append(Op(k, int(tok[i + 1])))
                        i += 2
                sessions.append(Session(int(tok[1]), tuple(ops)))
    if params is None:
        raise ValueError("carga sem linha PARAMS")
    return params, sessions


class PaymentGateway:
    """Gateway simulado que aguarda e registra tentativas de pagamento

    Cada cobrança dura o valor ``payment_ms`` definido nos parâmetros. O
    gateway não limita a concorrência: é responsabilidade do serviço respeitar
    ``max_payments``.
    """

    def __init__(self, params):
        """Cria o gateway a partir dos parâmetros da carga

        Args:
            params: Configuração que determina a duração simulada da cobrança
        """
        self._delay = params.payment_ms / 1000.0
        self._lock = threading.Lock()
        self.charges = []  # Tuplas com comprador, assento, tempos e resultado.

    def charge(self, buyer, seat, card_ok):
        """Simula e registra uma tentativa de pagamento

        Args:
            buyer: Identificador da pessoa compradora
            seat: Índice do assento cuja compra está sendo processada
            card_ok: Indica se o pagamento deve ser aceito ou recusado

        Returns:
            ``True`` se o pagamento for aceito; caso contrário, ``False``.
        """
        start = now_ns()
        time.sleep(self._delay)
        end = now_ns()
        with self._lock:
            self.charges.append((buyer, seat, start, end, "ok" if card_ok else "declined"))
        return card_ok


class TicketService:
    """Contrato das implementações do serviço de bilheteria.

    Todos os métodos podem ser chamados concorrentemente por várias threads.
    """

    def start(self):
        """Inicializa recursos antes do início das operações.

        Chamado uma vez antes de qualquer operação. Uma implementação pode
        iniciar aqui threads auxiliares.
        """

    def close(self):
        """Encerra recursos depois da última operação.

        Chamado uma vez após todas as operações. Uma implementação deve
        encerrar quaisquer threads auxiliares que tenha iniciado.
        """

    def hold(self, buyer, seat):
        """Tenta reservar um assento para uma pessoa compradora

        Args:
            buyer: Identificador da pessoa compradora
            seat: Índice do assento

        Returns:
            ``HELD``, ``TAKEN``, ``LIMIT`` ou ``ALREADY``.
        """
        raise NotImplementedError

    def purchase(self, buyer, seat, card_ok):
        """Tenta pagar por um assento reservado

        A implementação deve limitar a quantidade de chamadas simultâneas a
        ``gateway.charge(...)`` ao valor ``max_payments``.

        Args:
            buyer: Identificador da pessoa compradora
            seat: Índice do assento
            card_ok: Indica se o pagamento deve ser aceito ou recusado

        Returns:
            ``SOLD``, ``NOHOLD`` ou ``DECLINED``.
        """
        raise NotImplementedError

    def release(self, buyer, seat):
        """Libera a reserva de um assento

        Args:
            buyer: Identificador da pessoa compradora
            seat: Índice do assento

        Returns:
            ``RELEASED`` se a reserva for liberada; caso contrário, ``NOHOLD``
        """
        raise NotImplementedError

    def view(self, section):
        """Consulta os assentos de um setor

        Args:
            section: Índice do setor

        Returns:
            Tupla ``(disponíveis, reservados, vendidos)``
        """
        raise NotImplementedError

    def stats(self):
        """Retorna os contadores agregados do serviço

        Returns:
            Dicionário com ``sold``, ``holds_granted``, ``holds_rejected``,
            ``purchases_declined`` e ``views``
        """
        raise NotImplementedError


class SessionRunner:
    """Executa em ordem as operações de uma sessão e registra seus resultados.

    Cada thread deve ter sua própria instância de :class:`SessionRunner` e 
    sua própria lista de saída.
    """

    def __init__(self, service, out):
        """Cria o executor com um serviço e uma lista de registros

        Args:
            service: Serviço usado para executar as operações
            out: Lista que receberá os registros produzidos por este executor
        """
        self._svc = service
        self._out = out

    def run(self, session):
        """Executa sequencialmente as operações de uma sessão

        Operações ``T`` suspendem a thread pelo intervalo especificado e não
        geram registros. As demais operações são encaminhadas ao serviço e
        acrescentadas à lista de saída.

        Args:
            session: Sessão a executar

        Raises:
            ValueError: Se a sessão contiver um código de operação desconhecido
        """
        b = session.id
        for idx, op in enumerate(session.ops):
            k = op.kind
            if k == "T":
                time.sleep(op.arg / 1000.0)
                continue
            s = now_ns()
            info = ""
            if k == "V":
                a, h, so = self._svc.view(op.arg)
                res, info = "OK", f"avail={a},held={h},sold={so}"
            elif k == "H":
                res = self._svc.hold(b, op.arg)
            elif k == "P":
                res = self._svc.purchase(b, op.arg, op.card_ok)
            elif k == "R":
                res = self._svc.release(b, op.arg)
            else:
                raise ValueError(f"operação desconhecida: {k}")
            e = now_ns()
            self._out.append((b, idx, k, op.arg, s, e, res, info))


def write_log(path, outs, gateway, stats, workers, wall_ns):
    """Grava operações, cobranças, estatísticas e metadados da execução

    Args:
        path: Caminho do arquivo de log a criar
        outs: Listas de registros produzidas pelos executores das threads
        gateway: Gateway que contém os registros de pagamento
        stats: Dicionário de contadores finais do serviço
        workers: Quantidade de threads
        wall_ns: Duração total da execução, em nanossegundos

    Raises:
        OSError: Se o arquivo de log não puder ser criado ou escrito
    """
    with open(path, "w", encoding="utf-8") as f:
        for out in outs:
            for (b, idx, k, arg, s, e, res, info) in out:
                f.write(f"OP\t{b}\t{idx}\t{k}\t{arg}\t{s}\t{e}\t{res}\t{info}\n")
        for (b, seat, s, e, res) in gateway.charges:
            f.write(f"CHG\t{b}\t{seat}\t{s}\t{e}\t{res}\n")
        f.write("STATS\t" + "\t".join(f"{k}={v}" for k, v in stats.items()) + "\n")
        f.write(f"RUN\tworkers={workers}\twall_ns={wall_ns}\n")
