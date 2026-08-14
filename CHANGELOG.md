# Histórico de versões

## 1.7.3 — 2026-08-14

- dados online movidos para o schema exclusivo **controle_vendas** no Supabase;
- tabelas do outro projeto permanecem separadas e não são alteradas pelo aplicativo;
- sincronização passa a usar uma API autenticada própria, sem expor o novo schema diretamente;
- produtos, clientes e vendas já sincronizados são preservados durante a migração.

## 1.7.2 — 2026-08-14

- e-mail da conta Supabase removido da área visível de Configurações;
- identificação substituída pelo texto neutro **Conta autorizada da empresa**;
- senha continua sendo validada exclusivamente pelo Supabase Auth e não é gravada no aplicativo;
- teste de interface impede que um endereço de e-mail volte a aparecer nesse componente.

## 1.7.1 — 2026-08-14

- janelas secundárias passam a abrir centralizadas sobre o aplicativo, inclusive em monitores com DPI elevado;
- tela **Editar produto** corrigida para não surgir no canto superior esquerdo;
- telas de atualização disponível e progresso do download recebem o mesmo posicionamento central;
- janela secundária permanece oculta até o Windows concluir o cálculo de tamanho e posição, evitando a piscada no canto da tela;
- confirmações nativas do fluxo de atualização agora ficam explicitamente vinculadas à janela principal;
- novo teste de interface valida o centro das três janelas em escala de 150%.

## 1.7.0 — 2026-08-14

- sincronização segura de clientes, produtos e vendas pelo Supabase entre duas ou mais máquinas;
- acesso remoto restrito exclusivamente a `vendasldesmmedeiros@gmail.com` por autenticação e políticas RLS;
- SQLite local mantido para continuar trabalhando quando a internet estiver indisponível;
- fila automática envia alterações pendentes ao conectar, a cada operação e periodicamente;
- sessão protegida pelo Windows DPAPI, sem armazenar a senha e sem incluir chave administrativa no EXE;
- identificadores UUID e códigos de barras aleatórios evitam colisões entre cadastros feitos em computadores diferentes;
- controle de revisão detecta quando duas máquinas editam exatamente o mesmo registro;
- conflitos ficam preservados e podem ser resolvidos escolhendo a versão local ou a versão do Supabase;
- nova área **Dados online — Supabase** em Configurações, com conectar, sincronizar e desconectar;
- esquema remoto isolado das tabelas dos outros sistemas já existentes no projeto Supabase.

## 1.6.2 — 2026-08-14

- animação de navegação refeita para não trocar o gerenciador de layout das páginas;
- correção da piscada rápida observada ao abrir os módulos pelo menu lateral;
- ciclo visual solicitado a cada 5 ms, equivalente a até 200 atualizações por segundo;
- transição de 180 ms com aceleração e desaceleração suaves;
- primeira posição preparada antes de exibir a nova página, evitando saltos visuais.

## 1.6.1 — 2026-08-14

- navegação lateral redesenhada com deslocamento mínimo de 9 px em apenas 130 ms;
- removidos a cortina, a faixa e os destaques coloridos das novas animações;
- cadastros passam a usar somente um realce curto e neutro na linha salva;
- avisos de confirmação menores, mais rápidos e sem barra colorida;
- troca das abas internas permanece direta, preservando o visual selecionado do tema.

## 1.6.0 — 2026-08-14

- transição fluida e curta ao navegar entre todos os módulos do aplicativo;
- indicador animado ao alternar entre **Nova venda** e **Histórico de vendas**;
- produtos e clientes cadastrados ou editados recebem um pulso visual na tabela;
- avisos de sucesso passam a surgir suavemente sem bloquear a operação diária;
- vendas finalizadas também recebem confirmação animada, preservando a bipagem rápida;
- animações anteriores são canceladas com segurança em cliques rápidos e ao trocar o tema.

## 1.5.6 — 2026-08-13

- novo ícone clean de vendas, com sacola, gráfico e indicação de crescimento;
- o mesmo desenho passa a ser usado na janela, no EXE, no instalador e nos atalhos;
- PNG principal em 1024 px e ICO com nove resoluções entre 16 e 256 px;
- empacotamento atualizado para preservar o ícone em monitores Full HD e 4K.

## 1.5.5 — 2026-08-13

- relatório de faturamento passa a somar e exibir a quantidade total de produtos comprados por cliente;
- período do PDF simplificado para o nome do mês, como **AGOSTO**;
- linha de filtro removida do relatório impresso;
- contas ordenadas e agrupadas pelo nome da pessoa e, dentro do grupo, pela plataforma;
- fonte incorporada ao PDF para preservar corretamente nomes acentuados, como **JOÃO**.

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
