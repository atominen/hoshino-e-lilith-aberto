# Instalação privada — Alistair no PC2

> 06/11: para instalar **o painel da Central** no PC2 (só a janela, cérebro no PC1), veja
> [Painel no PC2](PAINEL_PC2_E_DESKTOP_LEVE_20261106.md#painel-da-central-no-pc2). Este documento trata do executor CPU do Alistair.

O repositório se chama **`atominen/hoshino-e-lilith`**, sem ponto final.
Renomeado em 07/10/2026, preservando o mesmo repositório e histórico.
Continua privado. Autentique o Git com sua própria conta no PC2; não coloque
senha/token na URL, código ou nesta documentação. Login no navegador do PC1
não autentica automaticamente o Git do PC2.

## 1. Obter o código

No Mint, com Git instalado e autenticado:

```bash
git clone https://github.com/atominen/hoshino-e-lilith.git
cd hoshino-e-lilith
```

O código não contém chaves, bancos, históricos, mentes atuais ou pesos.
Os seeds de identidade são exemplos novos, não cópias de experiências.
No PC2 só instalaremos o executor CPU; a entidade Alistair continua no PC1.

## 2. Transferir o pacote já existente

No PC principal, o pacote é:

`/home/gustavo/hoshino e lilith/pacotes/alistair_pc2.tar`

Tamanho: 2.565.345.280 bytes. SHA-256 verificado nesta rodada:

```text
95c624bb5f9baf86d5ee531a3ffa014bca31841607ca9da4a50dfa7acbeb14c6
```

Copie-o por pendrive/LAN para `~/Downloads/alistair_pc2.tar` do PC2.
Este pacote contém o motor CPU e o mesmo 4B, não um modelo novo.
Não está no Git. Transferência pela sua rede/pendrive é uma etapa necessária;
o clone sozinho não entrega os pesos.

## 3. Planejar e aplicar

Planejamento sem instalação, download, início de serviço ou firewall:

```bash
python3 instalar.py --perfil pc2 --pacote "$HOME/Downloads/alistair_pc2.tar"
```

Aplicar explicitamente:

```bash
python3 instalar.py --perfil pc2 \
  --pacote "$HOME/Downloads/alistair_pc2.tar" \
  --destino "$HOME/alistair_pc2" \
  --sha256 95c624bb5f9baf86d5ee531a3ffa014bca31841607ca9da4a50dfa7acbeb14c6 \
  --aplicar --dependencias
```

O instalador verifica hash, caminhos, integridade e espaço; mantém 4 GiB
de reserva **além** da extração. O arquivo tar já ocupa espaço: reserve cerca
de 9 GiB para ter tar + instalação + margem. Atualize o Python do Mint se o
filtro seguro `tarfile.data_filter` não estiver disponível; não o contorne.
Uma corrida de criação do destino também é recusada atomicamente.
Destino existente não é apagado/mesclado; staging de falha é preservado.

Dependências por apt podem usar rede e pedir sua senha **no terminal local**.
Nenhuma senha é lida/guardada pelo projeto. Nenhuma entidade inicia sozinha.

## 4. Iniciar e parear

```bash
bash "$HOME/alistair_pc2/iniciar.sh"
```

Siga [pc2/LEIA-ME.md](../pc2/LEIA-ME.md) para parear com o PC principal,
testar CPU/RAM/RPC e somente então habilitar a rota LAN. O pacote mantém
autenticação, allowlist, CPU limitado, fallback local e timeout existentes.
Não copiar identidade, memória, relações, estado psicológico ou banco ao PC2.

**Ainda pendente:** teste no Athlon real. O instalador foi validado com fixtures
e planejou o pacote real; isso não mede boot, HDD, inferência, LAN ou uso longo
do segundo computador.

## PC principal

`python3 instalar.py --perfil principal` planeja dependências. Com `--aplicar
--dependencias`, prepara o ambiente Python e pacotes existentes. Não é uma
instalação nova completa: modelos, daemons e configurações locais precisam ser
importados/configurados e validados separadamente. Nunca instalar por cima da
mente atual para atualizar código. Faça backup local antes de atualizar.
