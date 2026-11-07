# Alistair no segundo PC

Pacote para Athlon 3000G, 12 GB RAM, HD 150 GB, Linux Mint x86_64.
Precisa de Python 3.10+, bibliotecas normais do Linux e systemd com cgroup v2.
Mint 21/22 é candidato, não garantia: a versão exata e este hardware ainda
precisam passar pela verificação. Não há pip, Docker, CUDA ou download de modelo.

É **um executor textual**, não uma segunda mente. O PC principal conserva
identidade, bancos, correio, ferramentas e standby. Contextos enviados ao LLM
podem conter identidade e memória selecionada; não são copiados como bancos.
Pedidos ficam somente na RAM; não há log de prompts ou execução de comandos.
HTTP com assinatura HMAC protege autenticação/integridade, **não cifra o tráfego**:
use sua LAN confiável, sem encaminhamento de porta, VPN pública ou proxy.

## Transferência e início

1. Transfira a pasta `pacotes/alistair_pc2` completa. A seleção atual inclui
   `alistair-qwen3.5-4b:latest` Q4_K_M, sem memória da entidade.
   Se já tiver um `alistair_pc2.tar` atualizado, também pode transferi-lo e
   extrair. O tar duplicado não é mantido automaticamente no PC principal.
   Reserve cerca de 3 GiB para a pasta (6 GiB com tar + extração) e mantenha
   ao menos 4 GiB livres depois disso.
2. Na pasta extraída, abra um terminal e execute `bash iniciar.sh`.
   Primeiro são conferidos os hashes e as bibliotecas. Se houver biblioteca
   ausente, pare e envie o erro; não instale CUDA. Em Mint antigo, confira a
   versão antes de atualizar qualquer coisa.
3. Informe o IP LAN deste PC2 e o IP LAN do PC principal. A configuração é
   exclusiva e gera uma chave aleatória com permissão 600; não usa sua senha.
   Não muda firewall nem libera acesso para a Internet. Os dois relógios precisam
   estar sincronizados (tolerância de um minuto).
4. O terminal fica com o executor. Para parar, Ctrl+C ou `bash parar.sh`.
   Não habilitamos inicialização automática no login. Configuração existente
   não é sobrescrita: mudança de IP exige revisão e nova chave se necessário.

Se `systemd-run` falhar por limites/permissões, nada inicia sem os limites.
Não recomendamos contornar essa proteção; envie o erro para ajustar no Mint.

## Parear no PC principal — só depois de conferir o PC2

Copie a pasta `pareamento`, criada no PC2, para um local permanente no PC principal,
por exemplo `compartilhado/runtime/pareamento_pc2`. Preserve a permissão 600 da
chave (`chmod 600 lan.key` nessa pasta se a transferência não a preservou).
Não envie essa pasta em diagnóstico público nem recoloque-a em um pacote tar.

No projeto do PC principal, use:

```bash
compartilhado/ambientes/principal/bin/python scripts/conectar_alistair_pc2.py compartilhado/runtime/pareamento_pc2 --benchmark
```

Isso consulta saúde e mede uma inferência isolada (14 + 7), com fila e carga
incluídas no tempo de parede. Não cria conversas nas mentes. Faça uma rodada
com YouTube tocando e outra sem, para avaliar a convivência no Athlon/HD.
Essa medição não promete a mesma velocidade para contexto de 4096 ou ferramentas.

Só se estiver funcionando e você quiser usar o PC2:

```bash
compartilhado/ambientes/principal/bin/python scripts/conectar_alistair_pc2.py compartilhado/runtime/pareamento_pc2 --habilitar
```

Reinicie **Alistair** pela central. Hoshino/Lilith continuam nos seus motores.
O backend LAN fica desativado no projeto entregue. Para voltar ao local,
defina `enabled: false` em `compartilhado/config/alistair_pc2.json` e reinicie Alistair.

## Recursos e falhas

- Mesmo modelo 4B existente; não se acrescenta um quarto LLM. Cópia física
  do peso para execução externa, sem personalidade redefinida no PC2.
- Duas threads, uma inferência ativa, até duas aguardando. Contexto até 4096,
  resposta até 768 tokens. Valores acima do contrato são rejeitados, não cortados.
- Scope de usuário: CPU até 150% (1,5 CPUs lógicas), RAM até 7 GiB, swap do scope
  desativado e prioridade Nice 10. Isso limita consumo, não garante YouTube fluido
  nem que o kernel nunca mate o processo ao atingir o limite.
- Exige RAM disponível observada: 5 GiB para primeira carga, 1 GiB adicional
  quando aquecido. Libera residência do modelo após dez minutos ocioso.
- Motor Ollama próprio em loopback 11438; serviço assinado só no IP LAN escolhido,
  porta 8770 e apenas para o IP do PC principal. Não usa nem encerra outros Ollamas.
- Idempotência por id enquanto o cache vive (15 min, até 32 resultados). Não há
  persistência remota dos pedidos. Após queda/expiração, término incerto não vira
  sucesso nem fallback cego. A mensagem continua pendente para revisão/retry.
- Falha **confirmada** antes de efeitos permite fallback local. Pedido aceito sem
  término confirmado é consultado/cancelado pelo mesmo id. Ferramentas só rodam
  no PC principal após validar o resultado, com recibo durável local.
- O planejador geral de quatro destinos continua apenas consultivo. Este backend
  é uma escolha explícita de Alistair; não ativa cloud nem roteamento automático.

Os scripts de verificação não acessam microfone, Discord, Minecraft ou mentes.
`manifesto.json` registra origem e integridade; `licenses/` contém as licenças.
