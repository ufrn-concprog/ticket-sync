/**
 * Implementação de referência do serviço de bilheteria.
 *
 * <p>Esta versão deve usar uma estratégia simples e correta para proteger o
 * estado compartilhado.</p>
 */
public class CoarseTicketService implements Harness.TicketService {
    /** Parâmetros imutáveis da execução do serviço */
    private final Harness.Params params;

    /** <em>Gateway</em> usado para processar os pagamentos */
    private final Harness.PaymentGateway gateway;

    // TODO: estado compartilhado e mecanismos de sincronização

    /**
     * Cria o serviço de sincronização
     * @param params parâmetros da carga de trabalho
     * @param gateway <em>gateway</em> de pagamento usado pelo serviço
     */
    public CoarseTicketService(Harness.Params params, Harness.PaymentGateway gateway) {
        this.params = params;
        this.gateway = gateway;
    }

    /**
     * Tenta reservar um assento para uma pessoa compradora
     * @param buyer identificador da pessoa compradora
     * @param seat índice do assento
     * @return {@code HELD}, {@code TAKEN}, {@code LIMIT} ou {@code ALREADY}
     */
    @Override
    public String hold(int buyer, int seat) {
        throw new UnsupportedOperationException("TODO");
    }

    /**
     * Tenta efetuar o pagamento de um assento reservado
     * @param buyer identificador da pessoa compradora
     * @param seat índice do assento
     * @param cardOk indica se o cartão deve ser aprovado pelo gateway
     * @return {@code SOLD}, {@code NOHOLD} ou {@code DECLINED}
     */
    @Override
    public String purchase(int buyer, int seat, boolean cardOk) {
        throw new UnsupportedOperationException("TODO");
    }

    /**
     * Libera a reserva de um assento
     * @param buyer identificador da pessoa compradora
     * @param seat índice do assento
     * @return {@code RELEASED} se a reserva for liberada; caso contrário, {@code NOHOLD}
     */
    @Override
    public String release(int buyer, int seat) {
        throw new UnsupportedOperationException("TODO");
    }

    /**
     * Consulta as quantidades de assentos disponíveis, reservados e vendidos em um setor
     * @param section índice do setor
     * @return Resumo dos assentos do setor
     */
    @Override
    public Harness.SectionView view(int section) {
        throw new UnsupportedOperationException("TODO");
    }

    /**
     * Retorna os contadores agregados do serviço
     * @return Estatísticas atuais do serviço
     */
    @Override
    public Harness.Stats stats() {
        throw new UnsupportedOperationException("TODO");
    }
}
