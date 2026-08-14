# Sincronização do Vendas PRO com Supabase

## Conta autorizada

O projeto está configurado para aceitar exclusivamente o usuário autenticado:

`vendasldesmmedeiros@gmail.com`

Outros usuários existentes no mesmo projeto Supabase não recebem acesso às tabelas `vendas_pro_*`. A restrição é aplicada no PostgreSQL por Row Level Security (RLS), além da validação feita na interface.

## Conectar uma máquina

1. Instale e abra o Vendas PRO.
2. Acesse **Configurações → Dados online — Supabase**.
3. Informe a senha da conta autorizada e clique em **Conectar conta**.
4. Aguarde a confirmação de sincronização.

A senha não é armazenada. O token de renovação da sessão é protegido pelo Windows DPAPI e só pode ser descriptografado pelo mesmo usuário do Windows naquela máquina.

## Funcionamento offline

O SQLite continua sendo gravado primeiro. Cada alteração gera uma entrada na fila `sync_outbox`. Quando houver internet, a fila é enviada na ordem produtos, clientes e vendas, preservando as chaves estrangeiras. A sincronização acontece:

- depois de cada alteração;
- ao iniciar o aplicativo com uma sessão válida;
- manualmente pelo botão **Sincronizar agora**;
- automaticamente a cada 60 segundos.

## Edições simultâneas

Cada registro remoto possui um número de revisão. Uma alteração só é aceita se a revisão conhecida pela máquina ainda for a mais recente. Se duas máquinas alterarem o mesmo registro, a segunda não sobrescreve a primeira silenciosamente. O aplicativo guarda a alteração local e oferece:

- **manter este computador**: reaplica conscientemente a versão local sobre a revisão mais recente;
- **manter o Supabase**: descarta somente a alteração conflitante e baixa a versão já sincronizada.

Vendas novas usam UUIDs, e os códigos de barras usam um espaço aleatório amplo com validação EAN-13, evitando colisões entre máquinas mesmo durante trabalho offline.

## Segurança

- o EXE contém apenas a chave publicável do Supabase, própria para aplicativos desktop;
- nenhuma chave `secret` ou `service_role` é distribuída;
- o papel `anon` não possui acesso às tabelas;
- o papel `authenticated` ainda precisa passar pela política que confere UUID e e-mail;
- as funções de gravação também validam a conta e a revisão do registro;
- as tabelas têm prefixo `vendas_pro_` para não interferir nos outros sistemas do projeto.
