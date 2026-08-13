# Histórico de versões

## 1.5.4 — 2026-08-13

- campos de data de vendas e relatórios alterados para o formato brasileiro `dd/mm/aa`;
- máscara mantém as barras visíveis mesmo quando os números são apagados;
- novo ícone de calendário abre um seletor mensal para escolher a data com o clique;
- datas continuam gravadas internamente no padrão ISO, preservando filtros e ordenação;
- históricos e cadastros exibem as datas no formato brasileiro.

## 1.5.3 — 2026-08-13

- rodapé da nova venda reorganizado para manter sempre visíveis os textos dos botões **Remover item**, **Limpar venda** e **Finalizar venda**;
- confirmação visual rápida após cada bipagem, destacando em verde a linha do produto adicionado;
- mensagem temporária mostra a quantidade e o nome do produto reconhecido, sem interromper a próxima leitura;
- novos testes verificam o encaixe dos botões e o retorno visual da bipagem.

## 1.5.2 — 2026-08-13

- banco SQLite otimizado com modo WAL, espera segura para gravações simultâneas e novos índices;
- sequência persistente de códigos de barras, impedindo reutilização mesmo após excluir um produto;
- backups com nomes sempre únicos e verificação automática de integridade;
- instalador agora testa a nova versão completa antes de fechar ou substituir o aplicativo atual;
- rollback protegido por SHA-256 e bloqueado se a cópia anterior estiver corrompida;
- atualizador reforçado com limite de tamanho, validação de executável Windows e redirecionamentos confiáveis;
- valores monetários, períodos de relatório, dados obrigatórios e edição de vendas antigas mais robustos;
- relatórios A4 preparados para nomes longos e caracteres especiais;
- correção de agendamento de foco da bipagem ao trocar temas ou fechar a janela;
- análise estática, teste do `.exe` e instalação completa obrigatórios antes de cada GitHub Release.

## 1.5.1 — 2026-08-13

- correção do executável que falhava ao iniciar por falta do módulo interno `reportlab.graphics.barcode.code93`;
- inclusão de todos os submódulos de código de barras no empacotamento;
- novo teste obrigatório inicia o `.exe` compilado e gera uma etiqueta antes de publicar a Release.

## 1.5.0 — 2026-08-13

- ícone de impressão adicionado ao lado do ícone de copiar em cada produto;
- etiqueta térmica individual em página física de 40 x 25 mm;
- nome do produto em destaque, Code 128 correspondente ao código cadastrado e numeração legível;
- abertura automática da etiqueta no navegador com orientação para imprimir em tamanho real.

## 1.4.2 — 2026-08-13

- ícone de cópia adicionado ao lado de cada produto na tabela;
- clique no ícone copia diretamente o código do produto correto e mostra uma confirmação discreta.

## 1.4.1 — 2026-08-13

- aba interna selecionada agora fica maior e recebe a cor de destaque do tema;
- abas internas não selecionadas ficam menores e em cinza, facilitando a identificação da tela ativa.

## 1.4.0 — 2026-08-13

- dois temas persistentes: Dark grafite com azul neon e Light off-white com verde-oliva;
- tipografia e componentes reorganizados com mais espaçamento e estados de interação;
- correção do instalador em monitores com escala/DPI elevada;
- botões **Instalar** e **Cancelar** com faixa própria, cores e dimensões explícitas;
- cabeçalhos e conteúdos de todas as tabelas centralizados por coluna;
- relatórios A4 abertos automaticamente no navegador após serem gerados;
- edição de produto com nome e preço reunidos no mesmo formulário;
- botão para copiar o código de barras do produto selecionado;
- novos testes de interface para temas, DPI, alinhamento e abertura de PDF.

## 1.3.0 — 2026-08-12

- atualização segura pelo GitHub Releases;
- comparação de versões com Semantic Versioning;
- janela com versão instalada, nova versão e descrição;
- progresso de download e validação SHA-256 obrigatória;
- confirmação separada antes da instalação;
- tela de Configurações com verificação manual;
- backup do banco antes de atualizar;
- recuperação e rollback da versão anterior;
- testes automatizados para atualização, integridade e rollback.

## 1.2.0

- interface adaptativa Full HD/4K e ícones em alta definição;
- menu inicial e área de clientes;
- instalador Windows preservando o banco local.
