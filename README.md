# Vendas PRO — Controle de Vendas

Aplicativo desktop para Windows com interface adaptativa para Full HD e 4K, menu inicial, cadastro de produtos e clientes, vendas por bipagem, histórico editável, faturamento bruto, relatórios A4 em PDF, backup e atualização segura pelo GitHub Releases.

## Desenvolvimento e testes

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -v
python main.py
```

## Gerar o instalador Windows

```powershell
.\build_exe.ps1
```

O instalador será criado em `outputs\ControleDeVendas-Setup.exe`, acompanhado de `outputs\SHA256.txt`.

O banco SQLite é salvo em `%LOCALAPPDATA%\ControleDeVendas\controle_vendas.db`, fora da pasta do programa. Atualizações, reinstalações, desinstalações e rollback não apagam clientes, produtos ou vendas.

## Atualizações

O aplicativo consulta a última versão estável do repositório público `L-DE-S-M-MEDEIROS/CONTROLE-DE-VENDAS`. Ele aceita somente os anexos oficiais `ControleDeVendas-Setup.exe` e `SHA256.txt`, valida a integridade antes de solicitar autorização para instalar e mantém uma cópia recuperável da versão anterior.

- [Arquitetura e segurança](docs/ATUALIZACOES_SEGURAS.md)
- [Como publicar uma nova versão](docs/PUBLICAR_ATUALIZACAO.md)

Datas são digitadas no formato `AAAA-MM-DD`. O leitor de código de barras funciona como teclado: informe a quantidade, bipe o código e pressione Enter (normalmente enviado automaticamente pelo leitor).
