# Vendas PRO — Controle de Vendas

Aplicativo desktop para Windows com interface adaptativa para Full HD e 4K, temas Dark/Light, menu inicial, cadastro de produtos e clientes, etiquetas térmicas 40 x 25 mm com Code 128, vendas por bipagem, histórico editável, faturamento bruto, relatórios A4 em PDF, backup e atualização segura pelo GitHub Releases.

## Desenvolvimento e testes

```powershell
python -m pip install -r requirements.txt
python -m ruff check --select E4,E7,E9,F,I,UP,B,C4 main.py installer_launcher.py sales_control tests
python -m unittest discover -v
python main.py
```

## Gerar o instalador Windows

```powershell
.\build_exe.ps1
```

O instalador será criado em `outputs\ControleDeVendas-Setup.exe`, acompanhado de `outputs\SHA256.txt`.

O banco SQLite é salvo em `%LOCALAPPDATA%\ControleDeVendas\controle_vendas.db`, fora da pasta do programa. Atualizações, reinstalações, desinstalações e rollback não apagam clientes, produtos ou vendas.

## Dados online entre computadores

O aplicativo usa o Supabase como cópia central sincronizada e mantém o SQLite como base local. Em **Configurações → Dados online — Supabase**, conecte a conta `vendasldesmmedeiros@gmail.com`. A senha é usada somente para autenticar e não é salva; a sessão fica criptografada para o usuário atual do Windows.

- cada cadastro, edição ou venda entra primeiro no SQLite e é enviado ao Supabase em segundo plano;
- sem internet, as alterações ficam na fila e são enviadas quando a conexão retornar;
- ao iniciar e a cada 60 segundos, o aplicativo confere os dados da outra máquina;
- duas máquinas podem registrar vendas diferentes simultaneamente;
- se ambas editarem exatamente o mesmo registro, o aplicativo preserva a alteração local e solicita qual versão deve ser mantida;
- somente a conta autorizada pelas políticas RLS consegue ler ou alterar as tabelas do Vendas PRO.

Detalhes técnicos e procedimento de conexão: [docs/SUPABASE_SYNC.md](docs/SUPABASE_SYNC.md).

## Atualizações

O aplicativo consulta a última versão estável do repositório público `L-DE-S-M-MEDEIROS/CONTROLE-DE-VENDAS`. Ele aceita somente os anexos oficiais `ControleDeVendas-Setup.exe` e `SHA256.txt`, valida a integridade antes de solicitar autorização para instalar e mantém uma cópia recuperável da versão anterior.

- [Arquitetura e segurança](docs/ATUALIZACOES_SEGURAS.md)
- [Como publicar uma nova versão](docs/PUBLICAR_ATUALIZACAO.md)

Datas são digitadas no formato `AAAA-MM-DD`. O leitor de código de barras funciona como teclado: informe a quantidade, bipe o código e pressione Enter (normalmente enviado automaticamente pelo leitor).

Os temas ficam em **Configurações → Aparência**. Ao gerar qualquer relatório A4, o PDF é salvo e aberto automaticamente no navegador padrão para impressão.
