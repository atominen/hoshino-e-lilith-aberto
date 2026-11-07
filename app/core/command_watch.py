"""Espera cooperativa de uma consulta já vinculada, sem repetir a ação."""
import asyncio
import time


async def wait_for_command(initial, read, checkpoint, deadline):
    """read só consulta o mesmo job; checkpoint pode interromper por revisão.

    Orçamento de parede compartilhado pelo turno, sem chamadas ao modelo
    durante a espera. Não é um scheduler nem promete retomada após reinício.
    """
    result = initial
    while result.get('status') == 'pending':
        checkpoint()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(2.0, remaining))
        checkpoint()
        result = await read()
    return result
