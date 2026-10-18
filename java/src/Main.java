import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * Ponto de entrada do programa: configura e executa o serviço de bilheteria.
 *
 * <p>O método {@link #execute(Harness.Params, List, String, int, Path)} executa
 * uma execução completa. O esqueleto atual processa as sessões sequencialmente;
 * o laço deve ser substituído pelo <em>pipeline</em> concorrente descrito na 
 * especificação.</p>
 *
 * <p>A opção {@code --warmup N} executa {@code execute} <em>N</em> vezes com até 
 * as primeiras 100 sessões, sem gravar log, antes da execução medida sobre a carga
 * completa. Cada chamada deve criar serviço, <em>gateway</em> e listas novos e 
 * não deixar estado para a chamada seguinte.</p>
 */
public class Main {
    /** Cria a classe de entrada do programa */
    public Main() {}

    /**
     * Executa uma carga usando a implementação solicitada
     * @param params parâmetros do serviço
     * @param sessions sessões de compradores a executar
     * @param impl nome da implementação: {@code coarse} ou {@code fine}
     * @param workers quantidade de <em>threads</em>
     * @param out caminho do log, ou {@code null} para não gravá-lo
     * @return tempo decorrido em nanossegundos
     * @throws Exception se ocorrer uma falha durante a execução ou gravação do log
     */
    static long execute(Harness.Params params, List<Harness.Session> sessions, 
                        String impl, int workers, Path out) throws Exception {
        Harness.PaymentGateway gateway = new Harness.PaymentGateway(params);
        Harness.TicketService service = switch (impl) {
            case "coarse" -> new CoarseTicketService(params, gateway);
            case "fine" -> new FineTicketService(params, gateway);
            default -> 
                throw new IllegalArgumentException("--impl deve ser coarse ou fine");
        };
        service.start();

        // um SessionRunner e uma lista por thread
        List<Harness.Rec> recs = new ArrayList<>();
        Harness.SessionRunner runner = new Harness.SessionRunner(service, recs);

        long t0 = Harness.nowNs();

        // TODO: 
        // substituir pelo pipeline concorrente (porta de largada, produtor, fila limitada
        // de capacidade params.queueCapacity(), 'workers' threads, encerramento).
        for (Harness.Session s : sessions) runner.run(s);
        long wall = Harness.nowNs() - t0;

        service.close();
        if (out != null) {
            Harness.writeLog(out, List.of(recs), gateway, service.stats(), workers, wall);
        }
        return wall;
    }

    /**
     * Analisa os argumentos, carrega a carga, executa o aquecimento solicitado
     * e realiza uma execução medida
     * @param args argumentos da linha de comando
     * @throws Exception se a carga, a execução ou a gravação do log falhar
     */
    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("uso: Main <carga> [--workers N] [--impl coarse|fine] [--warmup N] [-o arquivo]");
            System.exit(1);
        }
        Path workloadPath = Path.of(args[0]);
        int workers = 16, warmup = 0;
        String impl = "coarse";
        Path output = Path.of("events.log");
        for (int i = 1; i < args.length; i++) {
            switch (args[i]) {
                case "--workers", "-w" -> workers = Integer.parseInt(args[++i]);
                case "--impl" -> impl = args[++i];
                case "--warmup" -> warmup = Integer.parseInt(args[++i]);
                case "-o" -> output = Path.of(args[++i]);
                default -> throw new IllegalArgumentException("argumento desconhecido: " + args[i]);
            }
        }

        Harness.Workload wl = Harness.loadWorkload(workloadPath);
        List<Harness.Session> prefix = 
            wl.sessions().subList(0, Math.min(100, wl.sessions().size()));
        for (int i = 0; i < warmup; i++) {
            execute(wl.params(), prefix, impl, workers, null);
        }

        long wall = execute(wl.params(), wl.sessions(), impl, workers, output);
        System.out.printf("%d sessoes em %.3f s -> %s%n", 
            wl.sessions().size(), wall / 1e9, output);
    }
}
