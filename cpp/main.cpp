/**
 * @file    main.cpp
 * @brief   Ponto de entrada da aplicação.
 * @details Carrega a carga de trabalho, inicializa o serviço de bilheteria e executa
 *          o pipeline de processamento das sessões. Ao final, grava o log das 
 *          operações, cobranças e estatísticas.
 * @note    O esqueleto abaixo executa as sessões sequencialmente, na thread principal. 
 *          O laço deve ser substiuído pelo pipeline concorrente descrito na 
 *          especificação.
 */

#include <cstdio>
#include <cstdlib>
#include <memory>
#include <string>

#include "coarse_service.h"
#include "fine_service.h"
#include "harness.h"

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr, "uso: %s <carga> [--workers N] [--impl coarse|fine] [-o arquivo]\n", argv[0]);
        return 1;
    }
    std::string workload_path = argv[1], impl = "coarse", output = "events.log";
    int workers = 0;
    for (int i = 2; i < argc; ++i) {
        std::string a = argv[i];
        if ((a == "--workers" || a == "-w") && i + 1 < argc) 
            workers = std::atoi(argv[++i]);
        else if (a == "--impl" && i + 1 < argc) impl = argv[++i];
        else if (a == "-o" && i + 1 < argc) output = argv[++i];
        else { 
            std::fprintf(stderr, "argumento desconhecido: %s\n", a.c_str()); 
            return 1; 
        }
    }

    harness::Workload wl = harness::load_workload(workload_path);
    harness::PaymentGateway gateway(wl.params);
    std::unique_ptr<harness::TicketService> service;
    if (impl == "coarse") 
        service = std::make_unique<CoarseTicketService>(wl.params, gateway);
    else if (impl == "fine") 
        service = std::make_unique<FineTicketService>(wl.params, gateway);
    else { 
        std::fprintf(stderr, "--impl deve ser coarse ou fine\n"); 
        return 1; 
    }
    service->start();

    // Um SessionRunner e um vetor por thread
    std::vector<std::vector<harness::Rec>> outs(1);
    harness::SessionRunner runner(*service, outs[0]);

    int64_t t0 = harness::now_ns();
    
    // TODO: 
    // Substituir pelo pipeline concorrente (porta de largada, produtor, fila limitada
    // de capacidade wl.params.queue_capacity, 'workers' threads, encerramento).
    for (const auto& s : wl.sessions) runner.run(s);
    int64_t wall = harness::now_ns() - t0;

    service->close();
    harness::write_log(output, outs, gateway, service->stats(), workers, wall);
    std::printf("%zu sessoes em %.3f s -> %s\n", wl.sessions.size(), wall / 1e9, output.c_str());
}
