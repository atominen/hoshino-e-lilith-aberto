"""Port/adaptação da fila AIRI (MIT, Neko Ayaka; licença em third_party/licenses).

Origem: load-queue.ts / priority.ts, commit 94fa5d7cc5bcfb927a65d78c25ae20377802bc32.
Python bloqueante, capacidade limitada, FIFO no empate, envelhecimento e remoção
de pendentes. Um cancelamento nunca afirma que interrompeu um trabalho ativo.
"""
import itertools
import math
import queue
import time

PRIORITY = {"critical": 300, "high": 200, "normal": 100, "low": 0}


class WorkQueue(queue.Queue):
    def __init__(self, maxsize=4, *, clock=time.monotonic, aging_seconds=1):
        if maxsize <= 0 or aging_seconds <= 0 or not math.isfinite(aging_seconds):
            raise ValueError("Fila deve ter capacidade e envelhecimento limitados.")
        self.clock, self.aging_seconds = clock, aging_seconds
        self.sequence = itertools.count()
        super().__init__(maxsize)

    def _init(self, maxsize):
        self.queue = []

    def put(self, item, block=True, timeout=None, *, priority="normal"):
        value = PRIORITY.get(priority) if isinstance(priority, str) else priority
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Prioridade inválida.")
        super().put((value, next(self.sequence), self.clock(), item), block, timeout)
        with self.not_empty:self.not_empty.notify_all()

    def get_matching(self, predicate, timeout=None):
        """Consumidores fixos por tipo, com a mesma capacidade e join global."""
        deadline=None if timeout is None else time.monotonic()+timeout
        with self.not_empty:
            while True:
                candidates=[i for i,entry in enumerate(self.queue) if predicate(entry[3])]
                if candidates:
                    now=self.clock()
                    index=max(candidates,key=lambda i:(self.queue[i][0]+max(0,now-self.queue[i][2])/self.aging_seconds,-self.queue[i][1]))
                    item=self.queue.pop(index)[3];self.not_full.notify();return item
                remaining=None if deadline is None else deadline-time.monotonic()
                if remaining is not None and remaining<=0:raise queue.Empty
                self.not_empty.wait(remaining)

    def _put(self, entry):
        self.queue.append(entry)

    def _get(self):
        now = self.clock()
        index = max(range(len(self.queue)), key=lambda i: (
            self.queue[i][0] + max(0, now - self.queue[i][2]) / self.aging_seconds,
            -self.queue[i][1]))
        return self.queue.pop(index)[3]

    def discard(self, predicate):
        """Remove só pendentes e ajusta join/task_done; devolve os itens removidos."""
        with self.mutex:
            removed = [entry for entry in self.queue if predicate(entry[3])]
            removed_ids = {entry[1] for entry in removed}
            self.queue[:] = [entry for entry in self.queue if entry[1] not in removed_ids]
            self.unfinished_tasks -= len(removed)
            if removed:
                self.not_full.notify_all()
            if not self.unfinished_tasks:
                self.all_tasks_done.notify_all()
            return [entry[3] for entry in removed]
