/**
 * @file    harness.h
 * @brief   Infraestrutura de execução do serviço de bilheteria.
 * @details Fornece leitura da carga, relógio, gateway de pagamento, execução
 *          das sessões e gravação do log consumido pelo validador.
 */

#ifndef HARNESS_H
#define HARNESS_H

#include <chrono>
#include <cstdint>
#include <fstream>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

namespace harness {

/** @brief Códigos de resultado usados pelo serviço e registrados no log  */
inline constexpr std::string_view HELD = "HELD";
inline constexpr std::string_view TAKEN = "TAKEN";
inline constexpr std::string_view LIMIT = "LIMIT";
inline constexpr std::string_view ALREADY = "ALREADY";
inline constexpr std::string_view SOLD = "SOLD";
inline constexpr std::string_view NOHOLD = "NOHOLD";
inline constexpr std::string_view DECLINED = "DECLINED";
inline constexpr std::string_view RELEASED = "RELEASED";

/** 
 * @brief Instante inicial do relógio monotônico usado pelo processo.
 * @details Este instante é usado como referência para calcular o tempo decorrido
 *          desde o início do processo.
 */
inline const auto ORIGIN = std::chrono::steady_clock::now();

/**
 * @brief Retorna o tempo monotônico decorrido desde o início do processo
 * @return Tempo decorrido em nanossegundos
 * @note Este relógio deve ser utilizado para verificar o 
 *       time-to-live (TTL) das reservas
 */
inline int64_t now_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now() - ORIGIN
    ).count();
}

/**
 * @brief Suspende a thread chamadora pelo intervalo solicitado
 * @param ms Duração da suspensão em milissegundos
 */
inline void sleep_ms(int64_t ms) { 
    std::this_thread::sleep_for(std::chrono::milliseconds(ms)); 
}

/** 
 * @struct  Params
 * @brief   Parâmetros do serviço de bilheteria definidos pela carga.
 * @details Estes parâmetros são lidos do arquivo de carga e não mudam 
 *          durante a execução
*/
struct Params {
    /** @brief Quantidade de assentos do evento  */
    int seats = 0;
    
    /** @brief Quantidade de assentos em cada setor */
    int section_size = 0;

    /** @brief Limite de reservas simultâneas válidas por pessoa compradora */
    int max_holds = 0;
    
    /** @brief Validade da reserva em milissegundos */
    int ttl_ms = 0;

    /** @brief Duração de uma cobrança no gateway, em milissegundos */
    int payment_ms = 0;

    /** @brief Número máximo de cobranças simultâneas permitido ao serviço */
    int max_payments = 0;

    /** @brief Atraso máximo para reconhecer uma reserva vencida, em milissegundos */
    int grace_ms = 0;

    /** @brief Número máximo de sessões aguardando na fila de trabalho */
    int queue_capacity = 0;

    /** @brief Retorna a validade da reserva em nanossegundos */
    int64_t ttl_ns() const { return ttl_ms * 1'000'000LL; }

    /**
     * @brief Retorna o setor que contém determinado assento
     * @details O setor é determinado pela divisão inteira do índice do assento
     * @param seat Índice do assento, começando em zero
     * @return Índice do setor, começando em zero
     */
    int section_of(int seat) const { return seat / section_size; }

    /**
     * @brief Retorna o índice do primeiro assento de um setor
     * @param section Índice do setor, começando em zero
     * @return Índice do primeiro assento do setor, começando em zero
     */
    int section_lo(int section) const { return section * section_size; }

    /**
     * @brief Retorna o limite superior exclusivo dos assentos de um setor
     * @details O limite é reduzido se o setor final tiver menos assentos
     * @param section Índice do setor, começando em zero
     * @return Índice do último assento do setor, começando em zero
     */
    int section_hi(int section) const { 
        return std::min(section * section_size + section_size, seats); 
    }
};

/**
 * @struct  Op
 * @brief   Operação pertencente à sessão de um comprador
 * @details Cada operação é representada por um código de operação, um argumento
 *          e, no caso de pagamento, um indicador se o pagamento será efetivado
 *          ou recusado pelo gateway. As operações são executadas na ordem em
 *          que aparecem.
 */
struct Op {
    /** @brief Código da operação: `V`, `H`, `P`, `R` ou `T` */
    char kind;

    /** @brief Setor em `V`, assento em `H`/`P`/`R` ou duração em `T` */
    int arg;

    /** @brief Indica se o cartão será aceito; usado por `P` */
    bool card_ok;
};

/** 
 * @struct Session
 * @brief  Sessão de uma pessoa compradora, contendo suas operações
 * @details Cada sessão representa as operações de uma única pessoa compradora, 
 *          executadas na ordem apresentada
 */
struct Session {
    /** @brief Identificador da pessoa compradora */
    int id;

    /** @brief Operações ordenadas da pessoa compradora */
    std::vector<Op> ops;
};

/** 
 * @struct  Workload
 * @brief   Parâmetros e sessões de compradores lidos de uma carga
 * @details Os parâmetros definem o comportamento do serviço, enquanto as sessões
 *          representam as operações de cada pessoa compradora
 */
struct Workload {
    /** @brief Parâmetros do serviço definidos pela carga */
    Params params;

    /** @brief Sessões dos compradores na ordem do arquivo */
    std::vector<Session> sessions;
};

/** 
 * @struct  SectionView
 * @brief   Quantidades de assentos retornadas pela consulta de um setor
 */
struct SectionView {
    /** @brief Quantidade de assentos disponíveis */
    int available;

    /** @brief Quantidade de assentos reservados ou em pagamento */
    int held;
    
    /** @brief Quantidade de assentos vendidos */
    int sold;
};

/** 
 * @struct  Stats
 * @brief   Contadores agregados do serviço, coletados ao final da execução
 */
struct Stats {
    /** @brief Quantidade de assentos vendidos */
    int64_t sold;

    /** @brief Quantidade de reservas concedidas */
    int64_t holds_granted;
    
    /** @brief Quantidade de reservas rejeitadas */
    int64_t holds_rejected;
    
    /** @brief Quantidade de pagamentos recusados */
    int64_t purchases_declined;
    
    /** @brief Quantidade de consultas ao mapa de assentos. */
    int64_t views;
};

/** 
 * @brief Lê os parâmetros e as sessões de um arquivo de carga
 * @param path Caminho do arquivo de carga
 * @return Carga analisada
 * @throws std::runtime_error Se o arquivo não puder ser aberto ou não 
 *         tiver registro `PARAMS`.
 */
inline Workload load_workload(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("não foi possível abrir " + path);
    Workload wl;
    bool have_params = false;
    std::string line;
    while (std::getline(in, line)) {
        std::istringstream ss(line);
        std::string tag;
        if (!(ss >> tag) || tag[0] == '#') continue;
        if (tag == "PARAMS") {
            std::string kv;
            while (ss >> kv) {
                auto eq = kv.find('=');
                std::string k = kv.substr(0, eq);
                int v = std::stoi(kv.substr(eq + 1));
                Params& p = wl.params;
                if (k == "seats") p.seats = v;
                else if (k == "section_size") p.section_size = v;
                else if (k == "max_holds") p.max_holds = v;
                else if (k == "ttl_ms") p.ttl_ms = v;
                else if (k == "payment_ms") p.payment_ms = v;
                else if (k == "max_payments") p.max_payments = v;
                else if (k == "grace_ms") p.grace_ms = v;
                else if (k == "queue_capacity") p.queue_capacity = v;
            }
            have_params = true;
        } else if (tag == "SESSION") {
            Session s;
            ss >> s.id;
            std::string k;
            while (ss >> k) {
                int arg;
                ss >> arg;
                if (k == "P") {
                    std::string card;
                    ss >> card;
                    s.ops.push_back({'P', arg, card == "ok"});
                } else {
                    s.ops.push_back({k[0], arg, true});
                }
            }
            wl.sessions.push_back(std::move(s));
        }
    }
    if (!have_params) throw std::runtime_error("carga sem linha PARAMS");
    return wl;
}

/** 
 * @class   PaymentGateway
 * @brief   Gateway simulado que registra cada cobrança.
 * @details Cada cobrança dura `payment_ms`. O gateway não limita a quantidade
 *          de cobranças simultâneas; essa restrição deve ser imposta pelo serviço.
 */
class PaymentGateway {
public:
    /** 
     * @struct  Charge
     * @brief   Registro de uma tentativa de pagamento.
     * @details Cada cobrança é registrada com o identificador da pessoa compradora,
     *          o assento, e os instantes inicial e final da cobrança.
     */
    struct Charge {
        /** @brief Identificador da pessoa compradora */
        int buyer;

        /** @brief Assento cuja compra está sendo processada */
        int seat;

        /** @brief Instante inicial da cobrança, em nanossegundos */
        int64_t start;

        /** @brief Instante final da cobrança, em nanossegundos */
        int64_t end;

        /** @brief Indica se o pagamento foi aceito */
        bool ok;
    };

    /** 
     * @brief Cria um gateway com a duração de pagamento definida pela carga
     * @param p Parâmetros da carga; utiliza somente `payment_ms`
     */
    explicit PaymentGateway(const Params& p) : delay_ms_(p.payment_ms) {}

    /** 
     * @brief Simula e registra uma tentativa de pagamento
     * @param buyer Identificador da pessoa compradora
     * @param seat Assento cuja compra está sendo processada
     * @param card_ok Indica se o cartão deve ser aceito
     * @return `true` se o pagamento for aceito; caso contrário, `false`
     */
    bool charge(int buyer, int seat, bool card_ok) {
        int64_t start = now_ns();
        sleep_ms(delay_ms_);
        int64_t end = now_ns();
        {
            std::lock_guard<std::mutex> g(mu_);
            charges_.push_back({buyer, seat, start, end, card_ok});
        }
        return card_ok;
    }

    /** 
     * @brief Retorna uma cópia protegida das cobranças registradas
     * @return Cobranças na ordem em que foram registradas
     */
    std::vector<Charge> charges() const {
        std::lock_guard<std::mutex> g(mu_);
        return charges_;
    }

private:
    /** @brief Duração simulada de cada cobrança, em milissegundos */
    int64_t delay_ms_;

    /** @brief Mutex que protege o vetor de cobranças registradas */
    mutable std::mutex mu_;

    /** @brief Cobranças realizadas pelo gateway */
    std::vector<Charge> charges_;
};

/**
 * @class   TicketService
 * @brief   Interface do serviço de bilheteria
 * @details Esta interface define os métodos que devem ser implementados por 
 *          qualquer versão do serviço de bilheteria. As operações podem ser 
 *          chamadas concorrentemente por várias threads, e a implementação deve 
 *          garantir a consistência dos dados e o cumprimento das regras de negócio.
 */
class TicketService {
public:
    /** @brief Destrói o serviço por meio de sua interface */
    virtual ~TicketService() = default;

    /** 
     * @brief Inicializa os recursos do serviço antes das operações
     * @note Chamado uma vez antes de qualquer operação
     */
    virtual void start() {}

    /** 
     * @brief Encerra e libera os recursos após as operações das threads
     * @note Chamado uma vez depois da última operação
     */
    virtual void close() {}

    /** 
     * @brief Tenta reservar um assento para uma pessoa compradora
     * @param buyer Identificador da pessoa compradora
     * @param seat Índice do assento, começando em zero
     * @return @ref HELD, @ref TAKEN, @ref LIMIT ou @ref ALREADY.
     */
    virtual std::string_view hold(int buyer, int seat) = 0;

    /** 
     * @brief Tenta efetuar o pagamento de um assento reservado pela pessoa compradora
     * @param buyer Identificador da pessoa compradora
     * @param seat Índice do assento, começando em zero
     * @param card_ok Indica se o gateway deve aceitar o pagamento
     * @return @ref SOLD, @ref NOHOLD ou @ref DECLINED
     */
    virtual std::string_view purchase(int buyer, int seat, bool card_ok) = 0;

    /** 
     * @brief Libera a reserva de um assento pertencente à pessoa compradora
     * @param buyer Identificador da pessoa compradora
     * @param seat Índice do assento, começando em zero
     * @return @ref RELEASED se liberar a reserva; caso contrário, @ref NOHOLD
     */
    virtual std::string_view release(int buyer, int seat) = 0;

    /** 
     * @brief Consulta as quantidades de assentos disponíveis, reservados e vendidos
     * @param section Índice do setor, começando em zero
     * @return Retrato das quantidades atuais de assentos no setor
     */
    virtual SectionView view(int section) = 0;

    /** 
     * @brief Retorna os contadores agregados do serviço
     * @return Estatísticas atuais do serviço
     */
    virtual Stats stats() = 0;
};

/**
 * @struct Rec
 * @brief   Estrutura que representa o resultado de uma operação do serviço, incluindo
 *          o instante inicial e final da operação, o código de resultado e informações
 *          adicionais para o log
 * @details Cada thread deve ter seu próprio vetor de registros, que
 *          será preenchido pelo executor de sessões. O vetor de registros é
 *          posteriormente usado para gerar o log final da execução.
 */
struct Rec {
    /** @brief Identificador da pessoa compradora */
    int buyer;

    /** 
     * @brief Índice da operação na sessão da pessoa compradora
     * @details O índice é usado para ordenar as operações na sessão
     */
    int idx;

    /** @brief Código da operação */
    char kind;

    /** @brief Argumento da operação */
    int arg;

    /** @brief Instante inicial da operação, em nanossegundos */
    int64_t start;

    /** @brief Instante final da operação, em nanossegundos */
    int64_t end;

    /** @brief Código de resultado do serviço */
    std::string_view result;

    /** @brief Informações adicionais da operação, gravadas no log */
    std::string info;
};

/**
 * @class   SessionRunner
 * @brief   Executor de sessões de compradores, registrando os resultados das operações
 * @details Cada thread deve ter seu próprio `SessionRunner` e vetor de saída
 */
class SessionRunner {
public:
    /** 
     * @brief Cria um executor associado ao serviço e ao vetor de saída da thread
     * @param svc Serviço usado para executar as operações; deve existir enquanto o executor existir
     * @param out Vetor que receberá os registros das operações executadas
     */
    SessionRunner(TicketService& svc, std::vector<Rec>& out) : svc_(svc), out_(out) {}

    /** 
     * @brief Executa sequencialmente uma sessão e acrescenta seus registros ao vetor
     * @param session Sessão a ser executada
     * @throws std::runtime_error Se a sessão contiver uma operação desconhecida
     */
    void run(const Session& session) {
        int b = session.id;
        for (std::size_t i = 0; i < session.ops.size(); ++i) {
            const Op& op = session.ops[i];
            if (op.kind == 'T') { sleep_ms(op.arg); continue; }
            int64_t s = now_ns();
            std::string_view res;
            std::string info;
            switch (op.kind) {
                case 'V': {
                    SectionView v = svc_.view(op.arg);
                    res = "OK";
                    info = "avail=" + std::to_string(v.available) + 
                           ",held=" + std::to_string(v.held) +
                           ",sold=" + std::to_string(v.sold);
                    break;
                }
                case 'H': res = svc_.hold(b, op.arg); break;
                case 'P': res = svc_.purchase(b, op.arg, op.card_ok); break;
                case 'R': res = svc_.release(b, op.arg); break;
                default: throw std::runtime_error("operação desconhecida");
            }
            int64_t e = now_ns();
            out_.push_back({b, static_cast<int>(i), op.kind, op.arg, s, e, res, 
                std::move(info)});
        }
    }

private:
    /** @brief Serviço ao qual o executor encaminha as operações */
    TicketService& svc_;

    /** @brief Vetor de registros pertencente à thread deste executor */
    std::vector<Rec>& out_;
};

/** 
 * @brief Grava no log as operações, cobranças, estatísticas e dados da execução
 * @param path Caminho do arquivo de destino
 * @param outs Vetores de registros das operações, um por thread
 * @param gw Gateway que contém as cobranças registradas
 * @param st Estatísticas finais do serviço
 * @param workers Quantidade de threads utilizadas
 * @param wall_ns Tempo total da execução, em nanossegundos
 */
inline void write_log(const std::string& path, const std::vector<std::vector<Rec>>& outs,
                      const PaymentGateway& gw, const Stats& st, int workers, 
                      int64_t wall_ns) {
    std::ofstream f(path);
    for (const auto& out : outs)
        for (const Rec& r : out)
            f << "OP\t" << r.buyer << '\t' << r.idx << '\t' << r.kind << '\t' 
              << r.arg << '\t' << r.start << '\t' << r.end << '\t' << r.result << '\t' 
              << r.info << '\n';
    for (const auto& c : gw.charges())
        f << "CHG\t" << c.buyer << '\t' << c.seat << '\t' << c.start << '\t' 
          << c.end << '\t' << (c.ok ? "ok" : "declined") << '\n';
        f << "STATS\tsold=" << st.sold << "\tholds_granted=" << st.holds_granted 
          << "\tholds_rejected=" << st.holds_rejected << "\tpurchases_declined=" 
          << st.purchases_declined << "\tviews=" << st.views << '\n';
        f << "RUN\tworkers=" << workers << "\twall_ns=" << wall_ns << '\n';
    }
}

#endif
