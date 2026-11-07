# Laboratório Neural e overlays de mods — 11/10/2026

## Contexto operacional

O download de Safetensors Qwen3.5-9B Uncensored Vision foi retomado após falha de Xet/CAS. O usuário trabalha no computador durante o dia e pediu **treinamento apenas após 21:00 no horário local**. A automação v1.4 **não contém agendamento nativo**; ela carrega e tenta treinar o 9B logo após o download. Portanto foi preparado um controlador independente que pausa **somente o PID do orquestrador**, mantém o downloader filho ativo e agenda `SIGCONT` por `systemd-run --user` às 21h, verificando cmdline, UID e starttime. A operação deve ser instalada e executada pelo operador no PC; o ChatGPT não a controla remotamente.

## Entrega

Novo diretório de desenvolvimento **`laboratorio/`** com interface web local em `127.0.0.1:8787`, CLI, status dos logs/modelos, controle de agenda e sistema de mods por **cópia materializada** (snapshot de arquivos Git para `~/laboratorio-lora/overlays/builds/...`). A ativação seleciona substituições de arquivos em uma **cópia de execução**, e não modifica o projeto original. `overlays/current` é um link simbólico que aponta para o último snapshot; não há hardlinks nem bind mounts para arquivos originais. Suporta manifestos para arquivos permitidos em `app/`, `scripts/`, `testes/`, etc., valida caminhos e bloqueia credenciais, bancos, memórias, modelos e runtime.

**Status:** pacote offline entregue na conversa como `laboratorio_neural_painel_mods_v0_1.zip`; testes locais sintéticos de overlay/segurança passaram; **não foi instalado nem testado no PC do usuário**. Toda execução depende de copiar a pasta para o checkout local. A interface HTTP oferece estado, agenda, mods e build com autenticação de escrita via token efêmero (somente localhost). **Não é um sandbox para código Python malicioso**, nem hot-reload do processo em produção, nem substituição por cima da Central. A cópia não herda dados não versionados, por decisão de preservação.

## Instalar no projeto local

```bash
cd "$HOME/hoshino e lilith"
unzip -n "$HOME/Downloads/laboratorio_neural_painel_mods_v0_1.zip" -d .
python3 -m unittest discover -s laboratorio/tests -v
python3 laboratorio/labctl.py serve --port 8787
```

Painel: `http://127.0.0.1:8787`.

## Agendamento local às 21h

```bash
cd "$HOME/hoshino e lilith"
python3 laboratorio/labctl.py status
python3 laboratorio/labctl.py schedule --pid 66998 --at '2026-10-11 21:00:00'
systemctl --user list-timers --all | grep lab-retomar-9b
```

O PID `66998` é o último conhecido em 11/10 às 09h; **verifique no status antes**. Se o orquestrador já estiver pausado com SIGSTOP, agenda a retomada, sem parar o downloader. Se timer falhar, informa erro; se foi a própria ferramenta que pausou o processo, tenta revertê-lo. Se a máquina suspender/reiniciar, a retomada não é garantida; o sistema ainda não implementa persistência/reinício completo do otimizador.

## Limites e próximo marco

- A versão 0.1 não modifica o pipeline v1.4 existente nem resolve a compatibilidade multimodal LoRA/GGUF com Ollama.
- Os mods são *file overrides* em snapshot. A aplicação sobre executores reais, proxy runtime, interceptação de imports e integração com a Central exigirão testes específicos de isolamento de dados e portas. Não se deve apontar uma cópia de teste para os bancos reais das entidades.
- A conformidade com a política de congelamento de escopo passa a incluir **esta ferramenta de desenvolvimento autorizada explicitamente pelo usuário**, mas **nenhum novo executor de produção** foi autorizado por esse pedido.
- Observabilidade registra `estado.json` da v1.4, cujos campos de falha podem estar desatualizados enquanto o processo trabalha; a interface deve mostrar atividade separadamente.
