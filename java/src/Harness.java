import java.io.IOException;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * Infraestrutura de execução do serviço de bilheteria.
 *
 * <p>Fornece leitura da carga, relógio, <em>gateway</em> de pagamento, executor de
 * sessões e gravação do log consumido pelo validador.</p>
 */
public final class Harness {
    /** Impede a instanciação desta classe utilitária */
    private Harness() {}

    /** Resultado de uma reserva concedida. */
    public static final String HELD = "HELD";

    /** Resultado de uma reserva recusada por conflito com outra pessoa compradora */
    public static final String TAKEN = "TAKEN";

    /** Resultado de uma reserva recusada por atingir o limite da pessoa compradora */
    public static final String LIMIT = "LIMIT";
    
    /** Resultado de uma tentativa de reserva repetida pela mesma pessoa compradora */
    public static final String ALREADY = "ALREADY";
    
    /** Resultado de uma compra concluída com sucesso */
    public static final String SOLD = "SOLD";

    /** Resultado de uma tentativa de compra sem reserva válida */
    public static final String NOHOLD = "NOHOLD";

    /** Resultado de uma compra cujo pagamento foi recusado */
    public static final String DECLINED = "DECLINED";

    /** Resultado de uma liberação concluída com sucesso */
    public static final String RELEASED = "RELEASED";

    /** Instante monotônico usado como origem para as medições do processo */
    private static final long ORIGIN = System.nanoTime();

    /**
     * Retorna o tempo monotônico decorrido desde o início do processo
     * @return tempo decorrido em nanossegundos
     */
    public static long nowNs() {
        return System.nanoTime() - ORIGIN;
    }

    /**
     * Parâmetros que definem o serviço e a execução da carga
     *
     * @param seats quantidade total de assentos
     * @param sectionSize quantidade de assentos por setor
     * @param maxHolds limite de reservas simultâneas por comprador
     * @param ttlMs validade das reservas em milissegundos
     * @param paymentMs duração simulada de cada pagamento em milissegundos
     * @param maxPayments limite de pagamentos simultâneos que o serviço deve respeitar
     * @param graceMs tolerância para reconhecer uma reserva vencida, em milissegundos
     * @param queueCapacity quantidade máxima de sessões aguardando na fila
     */
    public record Params(int seats, int sectionSize, int maxHolds, int ttlMs, int paymentMs,
                         int maxPayments, int graceMs, int queueCapacity) {
        /**
         * Converte a validade das reservas para nanossegundos.
         * @return validade das reservas em nanossegundos
         */
        public long ttlNs() { return ttlMs * 1_000_000L; }

        /**
         * Retorna o setor que contém determinado assento.
         * @param seat índice do assento, começando em zero
         * @return Índice do setor, começando em zero
         */
        public int sectionOf(int seat) { return seat / sectionSize; }

        /**
         * Retorna o índice do primeiro assento de um setor
         * @param section índice do setor, começando em zero
         * @return Índice do primeiro assento do setor
         */
        public int sectionLo(int section) { return section * sectionSize; }

        /**
         * Retorna o limite superior exclusivo dos assentos de um setor
         * @param section índice do setor, começando em zero
         * @return Limite exclusivo, limitado ao total de assentos do evento
         */
        public int sectionHi(int section) { 
            return Math.min(section * sectionSize + sectionSize, seats); 
        }
    }

    /**
     * Operação de uma sessão de comprador
     * @param kind código da operação: {@code V}, {@code H}, {@code P}, {@code R} ou {@code T}
     * @param arg setor em {@code V}, assento em {@code H}/{@code P}/{@code R} ou milissegundos em {@code T}
     * @param cardOk indica se o cartão deve ser aceito na operação {@code P}
     */
    public record Op(char kind, int arg, boolean cardOk) {}

    /**
     * Sessão de operações pertencente a uma pessoa compradora
     * @param id identificador do comprador
     * @param ops operações do comprador, na ordem de execução
     */
    public record Session(int id, List<Op> ops) {}

    /**
     * Carga de trabalho analisada
     * @param params parâmetros do serviço
     * @param sessions sessões dos compradores, na ordem do arquivo
     */
    public record Workload(Params params, List<Session> sessions) {}

    /**
     * Visão de um setor
     * @param available quantidade de assentos disponíveis
     * @param held quantidade de assentos reservados ou em pagamento
     * @param sold quantidade de assentos vendidos
     */
    public record SectionView(int available, int held, int sold) {}

    /**
     * Contadores agregados do serviço
     * @param sold quantidade de assentos vendidos
     * @param holdsGranted quantidade de reservas concedidas
     * @param holdsRejected quantidade de reservas rejeitadas
     * @param purchasesDeclined quantidade de pagamentos recusados
     * @param views quantidade de consultas ao mapa de assentos
     */
    public record Stats(long sold, long holdsGranted, long holdsRejected, 
        long purchasesDeclined, long views) {}

    /**
     * Lê os parâmetros e as sessões de uma carga de trabalho
     * @param path caminho do arquivo de carga
     * @return Parâmetros e sessões analisados
     * @throws IOException se o arquivo não puder ser lido ou não 
     *                     contiver um registro {@code PARAMS}
     */
    public static Workload loadWorkload(Path path) throws IOException {
        Params params = null;
        List<Session> sessions = new ArrayList<>();
        for (String raw : Files.readAllLines(path, StandardCharsets.UTF_8)) {
            String line = raw.trim();
            if (line.isEmpty() || line.startsWith("#")) continue;
            String[] t = line.split("\\s+");
            if (t[0].equals("PARAMS")) {
                int[] v = new int[8];
                String[] keys = {"seats", "section_size", "max_holds", "ttl_ms", 
                                "payment_ms", "max_payments", "grace_ms", 
                                "queue_capacity"};
                for (int i = 1; i < t.length; i++) {
                    String[] kv = t[i].split("=");
                    for (int k = 0; k < keys.length; k++) {
                        if (keys[k].equals(kv[0]))
                            v[k] = Integer.parseInt(kv[1]);
                    }
                }
                params = new Params(v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7]);
            } else if (t[0].equals("SESSION")) {
                List<Op> ops = new ArrayList<>();
                for (int i = 2; i < t.length; ) {
                    char k = t[i].charAt(0);
                    if (k == 'P') {
                        ops.add(new Op('P', Integer.parseInt(t[i + 1]), 
                            t[i + 2].equals("ok")));
                        i += 3;
                    } else {
                        ops.add(new Op(k, Integer.parseInt(t[i + 1]), true));
                        i += 2;
                    }
                }
                sessions.add(new Session(Integer.parseInt(t[1]), List.copyOf(ops)));
            }
        }
        if (params == null) throw new IOException("carga sem linha PARAMS");
        return new Workload(params, sessions);
    }

    /**
     * <em>Gateway</em> de pagamento simulado que registra cada cobrança.
     *
     * <p>Cada cobrança dura {@code paymentMs}. O <em>gateway</em> não 
     * limita as cobranças simultâneas; essa responsabilidade cabe ao serviço.</p>
     */
    public static final class PaymentGateway {
        /** Duração simulada de cada cobrança, em milissegundos */
        private final long delayMs;

        /** Registros no formato comprador, assento, início, fim e indicação de sucesso */
        private final List<long[]> charges = new ArrayList<>();

        /**
         * Cria o <em>gateway</em> a partir dos parâmetros da carga
         * @param p parâmetros que definem a duração do pagamento
         */
        public PaymentGateway(Params p) { this.delayMs = p.paymentMs(); }

        /**
         * Simula e registra uma tentativa de pagamento
         * @param buyer identificador da pessoa compradora
         * @param seat assento cuja compra está sendo processada
         * @param cardOk indica se o pagamento deve ser aceito
         * @return {@code true} se o pagamento for aceito; caso contrário, {@code false}
         */
        public boolean charge(int buyer, int seat, boolean cardOk) {
            long start = nowNs();
            sleep(delayMs);
            long end = nowNs();
            synchronized (charges) {
                charges.add(new long[]{buyer, seat, start, end, cardOk ? 1 : 0});
            }
            return cardOk;
        }

        /**
         * Retorna uma cópia dos registros de cobranças
         * @return Cobranças registradas
         */
        List<long[]> charges() {
            synchronized (charges) { return new ArrayList<>(charges); }
        }
    }

    /**
     * Suspende a <em>thread</em> atual pelo intervalo informado
     * @param ms Duração da suspensão em milissegundos
     */
    static void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    /**
     * Contrato implementado pelas versões do serviço de bilheteria.
     *
     * <p>Todos os métodos podem ser chamados concorrentemente por várias <em>threads</em>.
     */
    public interface TicketService {
        /**
         * Inicializa os recursos do serviço antes das operações.
         *
         * <p>Chamado uma vez antes de qualquer operação. <em>Threads</em> auxiliares
         * podem ser iniciadas aqui, se necessário.</p>
         */
        default void start() {}

        /**
         * Encerra os recursos do serviço depois da última operação.
         *
         * <p>Chamado uma vez após o término de todas as operações. 
         * <em>Threads</em> auxiliares devem ser encerradas aqui, se houver.</p>
         */
        default void close() {}

        /**
         * Tenta reservar um assento para uma pessoa compradora
         * @param buyer identificador da pessoa compradora
         * @param seat índice do assento
         * @return {@code HELD}, {@code TAKEN}, {@code LIMIT} ou {@code ALREADY}
         */
        String hold(int buyer, int seat);

        /**
         * Tenta efetuar o pagamento de um assento reservado
         * @param buyer identificador da pessoa compradora
         * @param seat índice do assento
         * @param cardOk indica se o <em>gateway</em> deve aceitar o cartão
         * @return {@code SOLD}, {@code NOHOLD} ou {@code DECLINED}
         */
        String purchase(int buyer, int seat, boolean cardOk);

        /**
         * Libera a reserva de um assento
         * @param buyer identificador da pessoa compradora
         * @param seat índice do assento
         * @return {@code RELEASED} se a reserva for liberada; 
         *         caso contrário, {@code NOHOLD}
         */
        String release(int buyer, int seat);

        /**
         * Consulta as quantidades de assentos disponíveis, reservados e vendidos
         * @param section índice do setor
         * @return Resumo dos assentos do setor
         */
        SectionView view(int section);

        /**
         * Retorna os contadores agregados do serviço
         * @return Estatísticas atuais do serviço
         */
        Stats stats();
    }

    /**
     * Registro do resultado e dos tempos de uma operação executada
     * @param buyer identificador da pessoa compradora
     * @param idx índice da operação na sessão
     * @param kind código da operação
     * @param arg argumento da operação
     * @param start instante de início em nanossegundos
     * @param end instante de término em nanossegundos
     * @param result código do resultado
     * @param info informações adicionais da operação
     */
    public record Rec(int buyer, int idx, char kind, int arg, 
        long start, long end, String result, String info) {}

    /**
     * Executa em ordem as operações de uma sessão e registra seus resultados.
     *
     * <p>Cada <em>thread</em> deve ter seu próprio executor e sua própria
     * lista de registros.</p>
     */
    public static final class SessionRunner {
        /** Serviço ao qual o executor encaminha as operações */
        private final TicketService svc;

        /** Lista de registros pertencente a este executor */
        private final List<Rec> out;

        /**
         * Cria um executor associado a um serviço e a uma lista de saída
         * @param svc serviço utilizado para executar as operações
         * @param out lista que receberá os registros das operações
         */
        public SessionRunner(TicketService svc, List<Rec> out) {
            this.svc = svc;
            this.out = out;
        }

        /**
         * Executa as operações de uma sessão sequencialmente
         * @param session sessão a executar
         * @throws IllegalStateException se a sessão contiver uma operação desconhecida
         */
        public void run(Session session) {
            int b = session.id();
            List<Op> ops = session.ops();
            for (int idx = 0; idx < ops.size(); idx++) {
                Op op = ops.get(idx);
                if (op.kind() == 'T') {
                    sleep(op.arg());
                    continue;
                }
                long s = nowNs();
                String res, info = "";
                switch (op.kind()) {
                    case 'V' -> {
                        SectionView v = svc.view(op.arg());
                        res = "OK";
                        info = "avail=" + v.available() + ",held=" + v.held() + 
                            ",sold=" + v.sold();
                    }
                    case 'H' -> res = svc.hold(b, op.arg());
                    case 'P' -> res = svc.purchase(b, op.arg(), op.cardOk());
                    case 'R' -> res = svc.release(b, op.arg());
                    default -> throw new IllegalStateException("operação desconhecida: " + op.kind());
                }
                long e = nowNs();
                out.add(new Rec(b, idx, op.kind(), op.arg(), s, e, res, info));
            }
        }
    }

    /**
     * Grava no arquivo os registros de operações, cobranças, estatísticas e execução
     * @param path caminho do arquivo de destino
     * @param outs listas de registros das threads trabalhadoras
     * @param gw gateway com as cobranças registradas
     * @param st estatísticas finais do serviço
     * @param workers quantidade de threads trabalhadoras
     * @param wallNs duração total da execução em nanossegundos
     * @throws IOException se não for possível gravar o arquivo
     */
    public static void writeLog(Path path, List<List<Rec>> outs, PaymentGateway gw, 
                                Stats st, int workers, long wallNs) throws IOException {
        try (PrintWriter w = 
            new PrintWriter(Files.newBufferedWriter(path, StandardCharsets.UTF_8))) {
            for (List<Rec> out : outs)
                for (Rec r : out)
                    w.print("OP\t" + r.buyer() + "\t" + r.idx() + "\t" + r.kind() + 
                            "\t" + r.arg() + "\t" + r.start() + "\t" + r.end() + "\t" + 
                            r.result() + "\t" + r.info() + "\n");
            for (long[] c : gw.charges())
                w.print("CHG\t" + c[0] + "\t" + c[1] + "\t" + c[2] + "\t" + c[3] + "\t" +
                        (c[4] == 1 ? "ok" : "declined") + "\n");
            w.print("STATS\tsold=" + st.sold() + "\tholds_granted=" + st.holdsGranted() +
                    "\tholds_rejected=" + st.holdsRejected() + 
                    "\tpurchases_declined=" + st.purchasesDeclined() +
                    "\tviews=" + st.views() + "\n");
            w.print("RUN\tworkers=" + workers + "\twall_ns=" + wallNs + "\n");
        }
    }
}
