# Vendas PRO 1.5.4 — instalação e atualizações

## Instalar em outro computador

1. Copie `ControleDeVendas-Setup.exe` e `SHA256.txt` para o computador.
2. Se quiser conferir a integridade antes de instalar, abra o PowerShell na pasta e execute:

   ```powershell
   Get-FileHash .\ControleDeVendas-Setup.exe -Algorithm SHA256
   ```

3. Compare o resultado com `SHA256.txt`.
4. Execute `ControleDeVendas-Setup.exe` e clique em **Instalar**.

Clientes, produtos, vendas e backups ficam em `%LOCALAPPDATA%\ControleDeVendas`, separados dos arquivos do programa.

## Atualização no aplicativo

- O aplicativo verifica a última versão estável do GitHub Releases na abertura.
- A verificação manual fica em **Configurações → Verificar atualizações**.
- A janela mostra versão instalada, nova versão, descrição, **Baixar atualização** e **Agora não**.
- O download usa somente `ControleDeVendas-Setup.exe` anexado à Release oficial.
- `SHA256.txt` é obrigatório; qualquer diferença cancela e apaga o download.
- Depois da validação, o usuário precisa autorizar a instalação.
- Antes de instalar, o banco recebe um backup.
- A versão anterior pode ser restaurada em **Configurações → Restaurar versão anterior**.

## Publicar a próxima versão

1. Altere `__version__` em `sales_control/__init__.py`, usando Semantic Versioning, por exemplo `1.5.3`.
2. Atualize `CHANGELOG.md`.
3. Execute:

   ```powershell
   python -m unittest discover -v
   .\build_exe.ps1
   ```

4. Envie o código para a branch `main` do repositório `L-DE-S-M-MEDEIROS/CONTROLE-DE-VENDAS`.
5. O GitHub Actions criará a tag da nova versão, a Release, o changelog automático e os anexos:

   - `ControleDeVendas-Setup.exe`
   - `SHA256.txt`

6. Confira a Release e não reutilize uma tag já distribuída.

O repositório está público, portanto o aplicativo não precisa e não contém token. Se ele se tornar privado, use um serviço intermediário com GitHub App e token de instalação temporário; nunca coloque PAT, senha ou chave administrativa dentro do EXE.

## Novidades da versão 1.5.4

- datas visíveis no formato `dd/mm/aa` em vendas e relatórios;
- barras da máscara permanecem no campo durante a digitação e exclusão;
- ícone de calendário abre um seletor visual de data compatível com os temas claro e escuro.

## Novidades da versão 1.5.3

- botões inferiores da tela de venda sempre visíveis, com texto e contraste corretos;
- animação verde rápida na linha do produto após a bipagem;
- confirmação temporária com quantidade e nome do produto reconhecido.

## Revisão de estabilidade da versão 1.5.2

- banco local com melhor concorrência, sequência persistente de códigos e backups verificados;
- nova versão testada antes de substituir o aplicativo instalado;
- rollback com conferência de integridade;
- instalador validado de ponta a ponta antes da publicação;
- download limitado, verificado como executável Windows e protegido por SHA-256.

## Correção da versão 1.5.1

- executável corrigido para incluir todos os módulos internos do gerador de códigos de barras;
- teste do `.exe` empacotado obrigatório antes da publicação.

## Novidades da versão 1.5.0

- ícone clicável de impressão ao lado do ícone de copiar em cada produto;
- etiqueta individual em PDF com tamanho exato de 40 x 25 mm;
- nome do produto, Code 128 correspondente ao código cadastrado e número legível;
- abertura automática no navegador para imprimir em tamanho real.

## Novidades da versão 1.4.2

- ícone clicável de cópia ao lado de cada produto;
- cópia direta do código correto com confirmação discreta na tela.

## Novidades da versão 1.4.1

- aba selecionada maior e colorida com a cor de destaque do tema;
- abas não selecionadas menores e em cinza.

## Novidades da versão 1.4.0

- Dark Mode grafite/azul-neon e Light Mode off-white/verde-oliva em **Configurações → Aparência**.
- Botões do instalador corrigidos para escalas elevadas do Windows.
- Todas as colunas das tabelas centralizadas.
- Relatórios A4 abertos automaticamente no navegador para impressão.
- Edição conjunta de nome e preço e botão para copiar o código de barras do produto.
