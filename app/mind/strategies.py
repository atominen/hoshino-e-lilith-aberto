"""
Tentar de outro jeito.

"Tentar diferentes abordagens caso dê errado" parece simples e quase nunca
funciona na prática, porque o modelo não lembra do que já tentou: sem registro, a
segunda tentativa é a primeira de novo, com outras palavras. É o laço clássico de
agente batendo na mesma pedra até o usuário desistir.

A correção vem do Reflexion (Shinn et al., 2023): depois de uma falha, escreva em
linguagem natural *o que* falhou e *por quê*, guarde isso, e injete no contexto da
próxima tentativa. Aqui o registro é estruturado — objetivo, abordagem, resultado,
lição — e o catálogo de abordagens é explícito, então dá para responder em Python
"quais caminhos ainda não foram tentados" em vez de esperar criatividade do modelo.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import bd  # noqa: E402

# Caminhos genéricos, ordenados do mais barato ao mais caro. Não são específicos
# de domínio de propósito: servem para "consertar o áudio" e para "descobrir quem
# é o Gustavo" igualmente.
CATALOGO = [
    ("recordar", "procurar na memória se já resolvi isso antes"),
    ("observar", "olhar o estado real (arquivos, tela, saída do último comando)"),
    ("minimo", "reduzir a um caso mínimo e testar isolado na oficina"),
    ("ler_erro", "ler o erro inteiro e atacar a causa, não o sintoma"),
    ("outra_ferramenta", "usar outra ferramenta para o mesmo fim"),
    ("quebrar", "quebrar em passos menores e resolver um de cada vez"),
    ("pesquisar", "pesquisar na web como outras pessoas resolveram"),
    ("perguntar", "perguntar à pessoa o que está faltando"),
    ("adiar", "reconhecer que agora não dá e deixar registrado para depois"),
]
ABORDAGENS = {chave for chave, _ in CATALOGO}


def registrar_tentativa(goal_id: str, abordagem: str, detalhe: str = "") -> str:
    numero = len(tentativas_de(goal_id)) + 1
    tid = bd.novo_id("tent", 6)
    bd.executar(
        "INSERT INTO attempts (id, goal_id, created_at, abordagem, detalhe, resultado, numero) "
        "VALUES (?,?,?,?,?,'em_andamento',?)",
        (tid, goal_id, bd.agora(), abordagem[:60], detalhe[:400], numero))
    bd.executar("UPDATE goals SET tentativas = ?, ultima_tentativa = ? WHERE id = ?",
                (numero, bd.agora(), goal_id))
    return tid


def concluir_tentativa(tentativa_id: str, deu_certo: bool, licao: str = "") -> str:
    bd.executar("UPDATE attempts SET resultado = ?, licao = ? WHERE id = ?",
                ("sucesso" if deu_certo else "falha", licao[:400], tentativa_id))
    return f"Tentativa {tentativa_id}: {'deu certo' if deu_certo else 'falhou'}."


def tentativas_de(goal_id: str) -> list:
    return bd.consultar("SELECT * FROM attempts WHERE goal_id = ? ORDER BY numero", (goal_id,))


def abordagens_usadas(goal_id: str) -> set:
    return {t["abordagem"] for t in tentativas_de(goal_id) if t["resultado"] != "sucesso"}


def proxima_abordagem(goal_id: str):
    """O caminho mais barato que ainda não foi tentado neste objetivo."""
    usadas = abordagens_usadas(goal_id)
    for chave, descricao in CATALOGO:
        if chave not in usadas:
            return {"abordagem": chave, "descricao": descricao}
    return None


def bloco_para_prompt(goal_id: str) -> str:
    """A memória de falhas que entra no contexto da próxima tentativa."""
    anteriores = [t for t in tentativas_de(goal_id) if t["resultado"] == "falha"]
    if not anteriores:
        return ""
    linhas = [f"- [{t['abordagem']}] {t['detalhe'][:160]}"
              + (f" -> lição: {t['licao'][:160]}" if t["licao"] else " -> não funcionou")
              for t in anteriores[-4:]]
    proxima = proxima_abordagem(goal_id)
    sugestao = (f"\nCaminho que eu ainda não tentei: {proxima['descricao']}."
                if proxima else
                "\nJá tentei todos os caminhos que eu conheço. Melhor eu dizer "
                "claramente que travei do que repetir o que já falhou.")
    return ("[O QUE EU JÁ TENTEI NESTE OBJETIVO — não vou repetir]\n"
            + "\n".join(linhas) + sugestao)


def objetivos_travados(min_falhas: int = 1) -> list:
    """Objetivos ativos com tentativa falha: alimentam o impulso de competência."""
    return bd.consultar("""
        SELECT g.id, g.description, g.tentativas, COUNT(a.id) AS falhas
        FROM goals g JOIN attempts a ON a.goal_id = g.id AND a.resultado = 'falha'
        WHERE g.status = 'active'
        GROUP BY g.id HAVING falhas >= ?
        ORDER BY falhas DESC""", (min_falhas,))


def proximo_objetivo_novo():
    """Um objetivo ativo que ela ainda nem começou — sem isto, um objetivo novo
    só entrava na fila de trabalho dela depois de já ter falhado uma vez, porque
    objetivos_travados() exige falha registrada. 'origem' fica de fora porque já
    tem tratamento próprio (curiosidade + bloco fixo no prompt), e diretiva
    sustentada (sustentar=1) também, porque essa é tratada no kernel antes do
    impulso de competência, não por aqui."""
    return bd.um("""
        SELECT id, description, priority FROM goals
        WHERE status = 'active' AND tentativas = 0
          AND tipo != 'origem' AND COALESCE(sustentar, 0) = 0
        ORDER BY priority ASC, project_epoch(created_at) ASC LIMIT 1""")


def resumo(goal_id: str) -> str:
    tentativas = tentativas_de(goal_id)
    if not tentativas:
        return "Nenhuma tentativa registrada para este objetivo."
    linhas = [f"{t['numero']}. [{t['abordagem']}] {t['resultado']}"
              + (f" — {t['licao'][:120]}" if t["licao"] else "") for t in tentativas]
    return "\n".join(linhas)
