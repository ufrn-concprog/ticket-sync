/**
 * @file    coarse_service.h * @brief   Declara a implementação de referência com sincronização (coarse) 
 *          do serviço de bilheteria.
 * @details Esta implementação deve usar uma estratégia simples para proteger o 
 *          estado compartilhado.
 */

#ifndef COARSE_SERVICE_H
#define COARSE_SERVICE_H

#include "harness.h"

/**
 * @class   CoarseTicketService
 * @brief   Implementação de referência do serviço de bilheteria (coarse).
 * @details Deve usar uma estratégia simples para proteger o estado compartilhado.
 */
class CoarseTicketService : public harness::TicketService {
public:
    /**
     * @brief Cria o serviço com os parâmetros da carga e um gateway de pagamento.
     * @param params Configuração imutável do serviço.
     * @param gateway Gateway usado para processar pagamentos; 
     *                deve existir enquanto o serviço existir.
     */
    CoarseTicketService(const harness::Params& params, harness::PaymentGateway& gateway)
        : params_(params), gateway_(gateway) {}

    /**
     * @brief Tenta reservar um assento para uma pessoa compradora
     * @param buyer Identificador da pessoa compradora
     * @param seat Índice do assento, começando em zero
     * @return `HELD`, `TAKEN`, `LIMIT` ou `ALREADY`.
     * @throws std::logic_error Enquanto o método não estiver implementado.
     */
    std::string_view hold(int buyer, int seat) 
        override { throw std::logic_error("TODO"); }

    /**
     * @brief Tenta efetuar o pagamento de um assento reservado pela pessoa compradora
     * @param buyer Identificador da pessoa compradora
     * @param seat Índice do assento, começando em zero
     * @param card_ok Indica se o gateway deve aceitar o pagamento
     * @return `SOLD`, `NOHOLD` ou `DECLINED`
     * @throws std::logic_error Enquanto o método não estiver implementado
     */
    std::string_view purchase(int buyer, int seat, bool card_ok) 
        override { throw std::logic_error("TODO"); }

    /**
     * @brief Libera a reserva de um assento pertencente à pessoa compradora
     * @param buyer Identificador da pessoa compradora
     * @param seat Índice do assento, começando em zero
     * @return `RELEASED` se liberar a reserva; caso contrário, `NOHOLD`
     * @throws std::logic_error Enquanto o método não estiver implementado
     */
    std::string_view release(int buyer, int seat) 
        override { throw std::logic_error("TODO"); }

    /**
     * @brief Retorna as quantidades de assentos disponíveis, reservados e vendidos
     * @param section Índice do setor, começando em zero
     * @return Quantidades de assentos do setor
     * @throws std::logic_error Enquanto o método não estiver implementado
     */
    harness::SectionView view(int section) 
        override { throw std::logic_error("TODO"); }

    /**
     * @brief Retorna os contadores agregados do serviço
     * @return Estatísticas atuais do serviço
     * @throws std::logic_error Enquanto o método não estiver implementado
     */
    harness::Stats stats() override { throw std::logic_error("TODO"); }

private:
    /** @brief Cópia dos parâmetros usados pelo serviço */
    harness::Params params_;

    /** @brief Referência ao gateway utilizado para processar pagamentos */
    harness::PaymentGateway& gateway_;
    
    // TODO: implementar o estado compartilhado e os mecanismos de sincronização
};

#endif
