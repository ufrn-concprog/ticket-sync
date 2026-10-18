"""
Implementações do contrato do serviço de bilheteria.

O módulo disponibiliza duas classes selecionáveis (``IMPLEMENTATIONS``), 
uma versão com sincronização simples (coarse) e outra com sincronização fina (fine). 
Os métodos de ambas ainda são esqueletos e precisam ser implementados.
"""

from harness import (HELD, TAKEN, LIMIT, ALREADY, SOLD, NOHOLD, DECLINED, RELEASED,
                     TicketService, now_ns)

class CoarseTicketService(TicketService):
    """Esqueleto de serviço com estratégia de sincronização simples

    Attributes:
        params: Parâmetros imutáveis da carga e do serviço
        gateway: Gateway usado para processar pagamentos
    """

    def __init__(self, params, gateway):
        """Inicializa o serviço com os parâmetros e o gateway compartilhado

        Args:
            params: Parâmetros da carga
            gateway: Gateway de pagamento simulado
        """
        self.params = params
        self.gateway = gateway

        # TODO: estado compartilhado e mecanismos de sincronização

    def hold(self, buyer, seat):
        """Tenta reservar um assento para uma pessoa compradora

        Args:
            buyer: Identificador da pessoa compradora
            seat: Índice do assento

        Returns:
            Um dos resultados definidos pelo contrato de :class:`TicketService`

        Raises:
            NotImplementedError: A operação ainda não foi implementada
        """
        raise NotImplementedError("TODO")

    def purchase(self, buyer, seat, card_ok):
        """Tenta comprar um assento reservado

        Args:
            buyer: Identificador da pessoa compradora
            seat: Índice do assento
            card_ok: Indica se o pagamento deve ser aceito pelo gateway

        Returns:
            Um dos resultados definidos pelo contrato de :class:`TicketService`

        Raises:
            NotImplementedError: A operação ainda não foi implementada
        """
        raise NotImplementedError("TODO")

    def release(self, buyer, seat):
        """Libera a reserva de um assento

        Args:
            buyer: Identificador da pessoa compradora
            seat: Índice do assento

        Returns:
            Um dos resultados definidos pelo contrato de :class:`TicketService`

        Raises:
            NotImplementedError: A operação ainda não foi implementada
        """
        raise NotImplementedError("TODO")

    def view(self, section):
        """Consulta os assentos de um setor

        Args:
            section: Índice do setor

        Returns:
            Tupla de contagens de assentos disponíveis, reservados e vendidos

        Raises:
            NotImplementedError: A operação ainda não foi implementada
        """
        raise NotImplementedError("TODO")

    def stats(self):
        """Obtém os contadores agregados do serviço

        Returns:
            Dicionário com os contadores definidos pelo contrato

        Raises:
            NotImplementedError: A operação ainda não foi implementada
        """
        raise NotImplementedError("TODO")


class FineTicketService(TicketService):
    """
    Esqueleto de serviço com estratégia de sincronização fina.

    Attributes:
        params: Parâmetros imutáveis da carga e do serviço.
        gateway: Gateway usado para processar pagamentos.
    """

    def __init__(self, params, gateway):
        """Inicializa o serviço com os parâmetros e o gateway compartilhado

        Args:
            params: Parâmetros da carga
            gateway: Gateway de pagamento simulado
        """
        self.params = params
        self.gateway = gateway

        # TODO

    def hold(self, buyer, seat):
        """Tenta reservar um assento para uma pessoa compradora

        Args:
            buyer: Identificador da pessoa compradora
            seat: Índice do assento

        Returns:
            Um dos resultados definidos pelo contrato de :class:`TicketService`

        Raises:
            NotImplementedError: A operação ainda não foi implementada
        """
        raise NotImplementedError("TODO")

    def purchase(self, buyer, seat, card_ok):
        """Tenta comprar um assento reservado

        Args:
            buyer: Identificador da pessoa compradora
            seat: Índice do assento
            card_ok: Indica se o cartão deve ser aceito pelo gateway

        Returns:
            Um dos resultados definidos pelo contrato de :class:`TicketService`

        Raises:
            NotImplementedError: A operação ainda não foi implementada
        """
        raise NotImplementedError("TODO")

    def release(self, buyer, seat):
        """Libera a reserva de um assento

        Args:
            buyer: Identificador da pessoa compradora
            seat: Índice do assento

        Returns:
            Um dos resultados definidos pelo contrato de :class:`TicketService`

        Raises:
            NotImplementedError: A operação ainda não foi implementada
        """
        raise NotImplementedError("TODO")

    def view(self, section):
        """Consulta os assentos de um setor

        Args:
            section: Índice do setor

        Returns:
            Tupla de contagens de assentos disponíveis, reservados e vendidos

        Raises:
            NotImplementedError: A operação ainda não foi implementada
        """
        raise NotImplementedError("TODO")

    def stats(self):
        """Obtém os contadores agregados do serviço

        Returns:
            Dicionário com os contadores definidos pelo contrato

        Raises:
            NotImplementedError: A operação ainda não foi implementada
        """
        raise NotImplementedError("TODO")


#: Implementações disponíveis para seleção por nome.
IMPLEMENTATIONS = {
    "coarse": CoarseTicketService,
    "fine": FineTicketService,
}
