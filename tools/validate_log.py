"""Validador do log de execução.

Uso:
    python3 tools/validate_log.py workloads/realistic-1.txt events.log

Lê a carga e o log produzido pela execução e verifica, apenas a partir
dos registros, se o serviço respeitou as regras. Cada operação é registrada
com o instante de início (s) e de término (e) medidos pelo relógio monotônico
do processo. O efeito real de uma operação ocorreu em algum instante dentro de
[s, e], então o validador só aponta violações inequívocas, ou seja, aquelas que
nenhuma ordenação possível das operações concorrentes consegue explicar.

Formato do log (campos separados por tabulação):
    OP   <sessão> <índice-da-op> <tipo> <arg> <início-ns> <fim-ns> <resultado> <info>
    CHG  <sessão> <assento> <início-ns> <fim-ns> <ok|declined>
    STATS sold=.. holds_granted=.. holds_rejected=.. purchases_declined=.. views=..
    RUN  workers=<n> wall_ns=<n>

Código de saída: 
    0 se nenhuma violação, 1 caso contrário, 2 para erro de uso/formato.
"""

import argparse
import collections
import sys

#: Limite superior para um assento vendido ativo
INF = float("inf")

#: Resultados permitidos do serviço, indexados pelo código da operação de carga.
RESULTS = {
    "V": {"OK"},
    "H": {"HELD", "TAKEN", "LIMIT", "ALREADY"},
    "P": {"SOLD", "NOHOLD", "DECLINED"},
    "R": {"RELEASED", "NOHOLD"},
}

class Report:
    """Coletam violações de validação em ordem de inserção por categoria.

    Args:
        max_print: Número máximo de mensagens de exemplo impressas por categoria

    Attributes:
        max_print: Limite de exibição por categoria
        by_cat: Mapeamento ordenado de nomes de categorias para mensagens de violação
    """

    def __init__(self, max_print):
        """Inicializa um relatório vazio com um limite de exibição por categoria.

        Args:
            max_print: Número máximo de exemplos impressos por categoria
        """
        self.max_print = max_print
        self.by_cat = collections.OrderedDict()

    def add(self, category, msg):
        """Adiciona uma violação à sua categoria.

        Args:
            category: Nome usado para agrupar a violação
            msg: Descrição legível da violação
        """
        self.by_cat.setdefault(category, []).append(msg)

    @property
    def total(self):
        """Retorna o número total de violações registradas."""
        return sum(len(v) for v in self.by_cat.values())

    def print(self):
        """Imprme todas as categorias e até ``max_print`` de suas mensagens."""
        for cat, msgs in self.by_cat.items():
            print(f"[{cat}] {len(msgs)} violação(ões)")
            for m in msgs[: self.max_print]:
                print(f"    - {m}")
            if len(msgs) > self.max_print:
                print(f"    ... e mais {len(msgs) - self.max_print}")


def fail_format(msg):
    """Reporta um registro de entrada malformado e termina com status 2.

    Args:
        msg: Descrição do erro de formato da entrada

    Raises:
        SystemExit: Sempre, com status de saída 2.
    """
    print(f"erro de formato: {msg}", file=sys.stderr)
    sys.exit(2)


def load_trace(path):
    """
    Lê parâmetros de carga e operações de sessão a partir de um arquivo 
    de carga.

    Linhas vazias e linhas que começam com ``#`` são ignoradas. Cada operação é
    armazenada como uma tupla contendo seu código, argumento numérico e 
    sinalizador opcional de cartão de pagamento.

    Args:
        path: Caminho para o arquivo de carga.

    Returns:
        Par ``(params, sessions)``. ``params`` mapeia nomes de parâmetros para
        valores inteiros; ``sessions`` mapeia IDs de sessão para tuplas de operações.

    Raises:
        OSError: Se a carga não puder ser aberta.
        SystemExit: Se um registro for desconhecido ou o arquivo de carga 
                    não tiver uma linha ``PARAMS``.
    """
    params, sessions = None, {}
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tok = line.split()
            if tok[0] == "PARAMS":
                params = {k: int(v) for k, v in (t.split("=") for t in tok[1:])}
            elif tok[0] == "SESSION":
                sid, i, ops = int(tok[1]), 2, []
                while i < len(tok):
                    k = tok[i]
                    if k == "P":
                        ops.append(("P", int(tok[i + 1]), tok[i + 2])); i += 3
                    elif k in "VHRT":
                        ops.append((k, int(tok[i + 1]), None)); i += 2
                    else:
                        fail_format(f"{path}:{ln}: operação desconhecida '{k}'")
                sessions[sid] = ops
            else:
                fail_format(f"{path}:{ln}: registro desconhecido '{tok[0]}'")
    if params is None:
        fail_format("Linha PARAMS inexistente no arquivo de carga")
    return params, sessions


class Op:
    """Representa o registro de uma operação lido do log de execução.

    Attributes:
        sid: ID da sessão do comprador
        idx: Índice da operação dentro da sessão
        kind: Código da operação (``V``, ``H``, ``P``, ou ``R``)
        arg: Argumento numérico da operação, geralmente um índice de seção ou assento
        s: Tempo de início em nanossegundos
        e: Tempo de término em nanossegundos
        res: Código do resultado do serviço
        info: Informações específicas da operação
    """

    __slots__ = ("arg", "e", "idx", "info", "kind", "res", "s", "sid")

    def __init__(self, sid, idx, kind, arg, s, e, res, info):
        """Inicializa uma operação a partir de seus campos analisados do log

        Args:
            sid: ID da sessão do comprador
            idx: Índice da operação dentro da sessão
            kind: Código da operação
            arg: Argumento numérico da operação
            s: Tempo de início em nanossegundos
            e: Tempo de término em nanossegundos
            res: Código do resultado do serviço
            info: Informações específicas da operação
        """
        self.sid, self.idx, self.kind, self.arg = sid, idx, kind, arg
        self.s, self.e, self.res, self.info = s, e, res, info


def load_log(path):
    """Lê operações, pagamentos, estatísticas e registros de execução de um log.

    Args:
        path: Caminho para o log de execução separado por tabulação

    Returns:
        Tupla ``(ops, charges, stats, run)``. ``ops`` contém instâncias de 
        :class:`Op`; ``charges`` contém tuplas de registros de pagamento. 
        ``stats`` e ``run`` são mapeamentos processados a partir de suas 
        respectivas linhas, ou ``None`` quando essas linhas estão ausentes.

    Raises:
        OSError: Se o log não puder ser aberto.
        SystemExit: Se uma linha estiver mal formada ou tiver um tipo de 
                    registro desconhecido.
    """
    ops, charges, stats, run = [], [], None, None
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            c = line.split("\t")
            try:
                if c[0] == "OP":
                    ops.append(Op(int(c[1]), int(c[2]), c[3], int(c[4]), 
                                  int(c[5]), int(c[6]), c[7], c[8] if len(c) > 8 else ""))
                elif c[0] == "CHG":
                    charges.append((int(c[1]), int(c[2]), int(c[3]), int(c[4]), c[5]))
                elif c[0] == "STATS":
                    stats = {k: int(v) for k, v in (t.split("=") 
                                                    for t in c[1:] if "=" in t)}
                elif c[0] == "RUN":
                    run = {k: int(v) for k, v in (t.split("=") 
                                                  for t in c[1:] if "=" in t)}
                else:
                    fail_format(f"{path}:{ln}: registro desconhecido '{c[0]}'")
            except (ValueError, IndexError):
                fail_format(f"{path}:{ln}: linha mal formada: {line!r}")
    return ops, charges, stats, run


def parse_info(info):
    """
    Processa pares de chave-valor inteiros a partir do campo de informações 
    de uma operação.

    O campo é separado por vírgulas; pares cujos valores não são inteiros são
    ignorados.

    Args:
        info: String com informações de operação, por exemplo, ``"avail=10,held=2"``.

    Returns:
        Mapeamento de chaves processadas para valores inteiros.
    """
    d = {}
    for part in info.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            try:
                d[k] = int(v)
            except ValueError:
                pass
    return d


def validate(params, sessions, ops, charges, stats, run, rep):
    """
    Verifica se os registros de execução satisfazem as regras da carga..

    Verifica a completude das operações, propriedade e vendas de assentos, 
    validade e limites de reservas, concorrência e resultados de pagamentos, 
    visualizações de seções e contadores de serviço. Ordenações possíveis de 
    operações concorrentes são consideradas; apenas contradições que não 
    podem ser explicadas pela concorrência são reportadas.

    Args:
        params:     Parâmetros da carga.
        sessions:   Operações esperadas, indexadas pelo ID da sessão
        ops:        Registros de operação processados do log de execução
        charges:    Registros de pagamento processados
        stats:      Contadores de serviço, 
                    ou ``None`` se o log não tiver uma linha ``STATS``
        run:        Metadados da execução, 
                    ou ``None`` se o log não tiver uma linha ``RUN``
        rep:        Relatório que recebe quaisquer violações detectadas

    Returns:
        Mapa com contagem de ``sessions``, ``ops``, ``sold``, ``charges``,
        ``peak_payments`` e ``expected_ops``
    """
    N = params["seats"]
    SS = params["section_size"]
    MAXH = params["max_holds"]
    TTL = params["ttl_ms"] * 1_000_000
    GRACE = params["grace_ms"] * 1_000_000
    K = params["max_payments"]

    # Término e completude
    if run is None:
        rep.add("completude", "log sem registro RUN: a execução não terminou "
                "(deadlock, falha ou log incompleto)")
    by_key = {}
    for o in ops:
        key = (o.sid, o.idx)
        if key in by_key:
            rep.add("completude", f"operação registrada mais de uma vez: " \
                    f"sessão {o.sid}, índice {o.idx}")
        by_key[key] = o
        if o.kind not in RESULTS:
            rep.add("completude", f"tipo de operação inválido '{o.kind}' " \
                    f"(sessão {o.sid})")
        elif o.res not in RESULTS[o.kind]:
            rep.add("completude", f"resultado '{o.res}' inválido para {o.kind} " \
                    f"(sessão {o.sid}, op {o.idx})")
        if o.e < o.s or o.s < 0:
            rep.add("completude", f"intervalo de tempo inválido " \
                    f"(sessão {o.sid}, op {o.idx})")
    expected = 0
    for sid, tops in sessions.items():
        prev_end = 0
        for idx, (k, arg, flag) in enumerate(tops):
            if k == "T":
                continue
            expected += 1
            o = by_key.get((sid, idx))
            if o is None:
                rep.add("completude", f"operação ausente no log: sessão {sid}, " \
                        f"índice {idx} ({k} {arg})")
                continue
            if o.kind != k or o.arg != arg:
                rep.add("completude", f"operação diferente da carga: sessão {sid}, " \
                        f"índice {idx}: esperado {k} {arg}, log tem {o.kind} {o.arg}")
            if o.s < prev_end:
                rep.add("completude", f"operações da sessão {sid} se sobrepõem no " \
                        f"tempo (índice {idx})")
            prev_end = o.e
    extra = [key for key in by_key if key[0] not in sessions or 
             key[1] >= len(sessions[key[0]])]
    if extra:
        rep.add("completude", f"{len(extra)} registro(s) de operação que " \
                f"não existem na carga")

    # Operações válidas para as análises seguintes
    ok_ops = [o for o in ops if o.kind in RESULTS and 
              o.res in RESULTS[o.kind] and o.e >= o.s]

    # Índices por (sessão, assento)
    per_ss = collections.defaultdict(list)   # (sid, seat) -> ops H/P/R em ordem de idx
    per_session_holds = collections.defaultdict(list)
    for o in ok_ops:
        if o.kind in "HPR":
            per_ss[(o.sid, o.arg)].append(o)
    for lst in per_ss.values():
        lst.sort(key=lambda x: x.idx)

    flag_of = {}
    for sid, tops in sessions.items():
        for idx, (k, arg, flag) in enumerate(tops):
            if k == "P":
                flag_of[(sid, idx)] = flag

    # Para cada hold bem-sucedido: a operação seguinte que o consome (P ou R), se houver
    hold_info = {}   # id(op) -> dict
    holds_by_seat = collections.defaultdict(list)
    for (sid, seat), lst in per_ss.items():
        for i, o in enumerate(lst):
            if o.kind != "H" or o.res != "HELD":
                continue
            nxt = None
            for q in lst[i + 1:]:
                if q.kind == "H" and q.res == "HELD":
                    break           # novo hold: o anterior terminou por expiração
                if q.kind in "PR":
                    nxt = q
                    break
            # fim possível da reserva (limite superior), usado para verificar 
            # rejeições indevidas
            pe = o.e + TTL + GRACE
            sold = False
            r_cert = INF    # instante a partir do qual a reserva pode ter acabado
            if nxt is not None:
                if nxt.kind == "R" and nxt.res == "RELEASED":
                    pe = min(pe, nxt.e)
                    r_cert = nxt.s
                elif nxt.kind == "P" and nxt.res == "DECLINED":
                    pe = max(pe, nxt.e)
                    r_cert = nxt.s
                elif nxt.kind == "P" and nxt.res == "SOLD":
                    pe, sold = INF, True
                    r_cert = nxt.s
            info = {"op": o, "nxt": nxt, "pe": pe, "sold": sold, "r": r_cert}
            hold_info[id(o)] = info
            holds_by_seat[seat].append(info)
            per_session_holds[sid].append(info)

    # Vendas
    sold_ops = collections.defaultdict(list)
    for o in ok_ops:
        if o.kind == "P" and o.res == "SOLD":
            sold_ops[o.arg].append(o)
    for seat, lst in sold_ops.items():
        if len(lst) > 1:
            who = ", ".join(f"sessão {o.sid}" for o in lst)
            rep.add("assento-vendido-uma-vez", f"assento {seat} " \
                    f"vendido {len(lst)} vezes ({who})")
    for seat in sold_ops:
        if not 0 <= seat < N:
            rep.add("assento-vendido-uma-vez", f"assento inexistente vendido: {seat}")

    # P e R exigem reserva válida; rejeições indevidas
    for (sid, seat), lst in per_ss.items():
        cand = None
        for o in lst:
            if o.kind == "H":
                if o.res == "HELD":
                    cand = o
                continue
            # o é P ou R: consome a última reserva
            success = o.res in ("SOLD", "DECLINED", "RELEASED")
            if success:
                if cand is None:
                    rep.add("operacao-sem-reserva",
                            f"sessão {sid}: {o.kind} {seat} -> {o.res} " \
                            f"sem reserva bem-sucedida (HELD) anterior")
                elif o.s >= cand.e + TTL:
                    rep.add("operacao-apos-expiracao",
                            f"sessão {sid}: {o.kind} {seat} -> {o.res} " \
                            f"iniciou {(o.s - cand.e - TTL) / 1e6:.1f} ms " \
                            f"depois de a reserva ter expirado com certeza")
            else:  # NOHOLD
                if cand is not None and o.e < cand.s + TTL:
                    rep.add("rejeicao-indevida",
                            f"sessão {sid}: {o.kind} {seat} -> NOHOLD, " \
                            f"mas a reserva (iniciada em t={cand.s}) " \
                            f"estava certamente válida durante toda a operação")
            cand = None

            # Valida resultado (ok/bad) contra pagamento (SOLD/DECLINED)
            if o.kind == "P":
                flag = flag_of.get((sid, o.idx))
                if o.res == "SOLD" and flag == "bad":
                    rep.add("pagamento", f"sessão {sid}: " \
                            f"assento {seat} vendido com pagamento recusado")
                if o.res == "DECLINED" and flag == "ok":
                    rep.add("pagamento", f"sessão {sid}: " \
                            f"assento {seat} recusado com pagamento válido")

    # Exclusão mútua das reservas (pares de holds no mesmo assento)
    for seat, infos in holds_by_seat.items():
        sold_by = sold_ops.get(seat, [])
        # hold concedido num assento já vendido com certeza
        for sop in sold_by:
            for h in infos:
                o = h["op"]
                if o.sid != sop.sid and o.s > sop.e:
                    rep.add("reserva-em-assento-vendido",
                            f"assento {seat}: sessão {o.sid} obteve reserva depois da venda "
                            f"(sessão {sop.sid}) ter terminado")
        
        # dois holds sem ordenação possível
        flagged = False
        for i in range(len(infos)):
            if flagged:
                break
            for j in range(i + 1, len(infos)):
                a, b = infos[i], infos[j]
                if a["op"].sid == b["op"].sid:
                    continue
                # a primeiro, b depois?
                ab = (not a["sold"]) and b["op"].e >= min(a["op"].s + TTL, a["r"])
                ba = (not b["sold"]) and a["op"].e >= min(b["op"].s + TTL, b["r"])
                if not (ab or ba):
                    rep.add("reserva-exclusiva",
                            f"assento {seat}: sessões {a['op'].sid} e {b['op'].sid} " \
                            f"obtiveram reserva simultaneamente " \
                            f"(sem expiração, liberação ou venda que justifique)")
                    flagged = True
                    break

    # TAKEN sem justificativa
    for o in ok_ops:
        if o.kind == "H" and o.res == "TAKEN":
            seat = o.arg
            justified = any(p.s <= o.e for p in sold_ops.get(seat, []))
            if not justified:
                for h in holds_by_seat.get(seat, []):
                    ho = h["op"]
                    if ho.sid != o.sid and ho.s <= o.e and h["pe"] >= o.s:
                        justified = True
                        break
            if not justified:
                rep.add("rejeicao-indevida",
                        f"sessão {o.sid}: reserva do assento {seat} -> TAKEN, " \
                        f"mas nenhuma reserva ou venda pode ter estado ativa no " \
                        f"intervalo da operação (reserva expirada não liberada?)")

    # Limite de reservas por pessoa compradora
    for sid, hs in per_session_holds.items():
        hs.sort(key=lambda h: h["op"].idx)
    for o in ok_ops:
        if o.kind != "H":
            continue
        hs = per_session_holds.get(o.sid, [])
        if o.res == "HELD":
            certain = 0
            for h in hs:
                ho = h["op"]
                if ho.idx >= o.idx or ho is o:
                    continue
                # ainda ativa com certeza durante toda a operação?
                consumed_before = h["nxt"] is not None and h["nxt"].idx < o.idx
                if not consumed_before and o.e < ho.s + TTL:
                    certain += 1
            if certain >= MAXH:
                rep.add("limite-de-reservas",
                        f"sessão {o.sid}: reserva do assento {o.arg} com {certain} reservas "
                        f"certamente ativas (limite {MAXH})")
        elif o.res == "LIMIT":
            possible = 0
            for h in hs:
                ho = h["op"]
                if ho.idx >= o.idx:
                    continue
                if h["nxt"] is not None and h["nxt"].idx < o.idx:
                    continue    # reserva já consumida (compra/liberação) antes desta operação
                if ho.s <= o.e and h["pe"] >= o.s:
                    possible += 1
            if possible < MAXH:
                rep.add("rejeicao-indevida",
                        f"sessão {o.sid}: reserva do assento {o.arg} -> LIMIT, " \
                        f"mas só {possible} reserva(s) poderiam estar ativas (limite {MAXH})")

    # Pagamentos: concorrência e correspondência com as compras
    events = []
    for (_, _, s, e, _) in charges:
        events.append((s, 1))
        events.append((e, -1))

    # em empate, término (-1) antes de início (+1)
    events.sort(key=lambda x: (x[0], x[1]))
    
    cur = peak = 0
    for _, d in events:
        cur += d
        peak = max(peak, cur)
    if peak > K:
        rep.add("limite-de-pagamentos",
                f"até {peak} cobranças simultâneas observadas no gateway (limite {K})")

    charge_idx = collections.defaultdict(list)
    for c in charges:
        charge_idx[(c[0], c[1])].append(c)
    paid_ops = [o for o in ok_ops if o.kind == "P" and o.res in ("SOLD", "DECLINED")]
    for o in paid_ops:
        cs = charge_idx.get((o.sid, o.arg), [])
        match = [c for c in cs if c[2] >= o.s and c[3] <= o.e]
        if len(match) != 1:
            rep.add("pagamento", 
                    f"sessão {o.sid}: compra do assento {o.arg} -> {o.res} com "
                    f"{len(match)} cobrança(s) no gateway (esperado exatamente 1)")
        else:
            want = "ok" if o.res == "SOLD" else "declined"
            if match[0][4] != want:
                rep.add("pagamento", 
                        f"sessão {o.sid}: resultado {o.res} incoerente com a cobrança "
                        f"({match[0][4]}) do assento {o.arg}")
    if len(charges) != len(paid_ops):
        rep.add("pagamento", f"{len(charges)} cobrança(s) no gateway para {len(paid_ops)} compra(s) "
                             f"concluída(s) (SOLD/DECLINED): cobrança sem compra, " \
                             f"ou compra NOHOLD que cobrou")

    # Mapa de assentos (view
    sold_by_section = collections.defaultdict(list)   # setor -> [(s, e)] das vendas
    for seat, lst in sold_ops.items():
        for o in lst:
            sold_by_section[seat // SS].append((o.s, o.e))
    for o in ok_ops:
        if o.kind != "V":
            continue
        d = parse_info(o.info)
        if not all(k in d for k in ("avail", "held", "sold")):
            rep.add("mapa-de-assentos", 
                    f"sessão {o.sid}: view {o.arg} sem info avail/held/sold")
            continue
        size = max(0, min(SS, N - o.arg * SS))
        if d["avail"] + d["held"] + d["sold"] != size or min(d.values()) < 0:
            rep.add("mapa-de-assentos",
                    f"sessão {o.sid}: view do setor {o.arg}: avail+held+sold = "
                    f"{d['avail'] + d['held'] + d['sold']} (esperado {size})")
        lo = sum(1 for interval in sold_by_section.get(o.arg, []) if interval[1] < o.s)
        hi = sum(1 for interval in sold_by_section.get(o.arg, []) if interval[0] < o.e)
        if not lo <= d["sold"] <= hi:
            rep.add("mapa-de-assentos",
                    f"sessão {o.sid}: view do setor {o.arg} informa sold={d['sold']}, "
                    f"mas o log só admite entre {lo} e {hi}")

    # Contadores do serviço
    if stats is None:
        rep.add("contadores", "log sem registro STATS")
    else:
        truth = {
            "sold": sum(1 for o in ok_ops if o.kind == "P" and o.res == "SOLD"),
            "holds_granted": sum(1 for o in ok_ops if o.kind == "H" and o.res == "HELD"),
            "holds_rejected": sum(1 for o in ok_ops if o.kind == "H" and o.res != "HELD"),
            "purchases_declined": sum(1 for o in ok_ops if o.kind == "P" and o.res == "DECLINED"),
            "views": sum(1 for o in ok_ops if o.kind == "V"),
        }
        for k, v in truth.items():
            if k not in stats:
                rep.add("contadores", f"contador '{k}' ausente em STATS")
            elif stats[k] != v:
                rep.add("contadores", f"contador '{k}' = {stats[k]}, mas o log tem {v}")

    return {
        "sessions": len(sessions), "ops": len(ok_ops), "sold": len(sold_ops), "charges": len(charges),
        "peak_payments": peak, "expected_ops": expected,
    }


def main():
    """
    Valida uma carga contra um log de execução e imprime um relatório.

    Os argumentos da linha de comando fornecem os caminhos para a carga e o log, 
    com uma opção de limite para o número de exemplos impressos por categoria de 
    violação.

    Returns:
        ``0`` se nenhuma violação for encontrada, ``1`` se a validação encontrar alguma.
        Erros de formato de entrada terminam com status ``2`` via :func:`fail_format`.

    Raises:
        OSError: Se o arquivo de carga ou o de log não puderem ser abertos.
    """
    ap = argparse.ArgumentParser(description=__doc__, 
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace", help="arquivo de carga (workload)")
    ap.add_argument("log", help="log de eventos produzido pela execução")
    ap.add_argument("--max-print", type=int, default=5, 
                    help="máximo de exemplos por categoria")
    args = ap.parse_args()

    params, sessions = load_trace(args.trace)
    ops, charges, stats, run = load_log(args.log)
    rep = Report(args.max_print)
    summary = validate(params, sessions, ops, charges, stats, run, rep)

    print(f"sessões: {summary['sessions']} "
        f"operações registradas: {summary['ops']}/{summary['expected_ops']} "
        f"assentos vendidos: {summary['sold']}  cobranças: {summary['charges']} "
        f"pico de pagamentos simultâneos: {summary['peak_payments']} "
        f"(limite {params['max_payments']})")
    if run:
        wall = run.get("wall_ns", 0) / 1e9
        if wall > 0:
            print(f"threads: {run.get('workers', '?')}  tempo: {wall:.3f} s  "
                  f"vazão: {summary['ops'] / wall:.0f} ops/s, "
                  f"{summary['sessions'] / wall:.0f} sessões/s")
    if rep.total == 0:
        print("RESULTADO: OK (nenhuma violação encontrada)")
        return 0
    rep.print()
    print(f"RESULTADO: FALHA ({rep.total} violações em {len(rep.by_cat)} categoria(s))")
    return 1


if __name__ == "__main__":
    sys.exit(main())
