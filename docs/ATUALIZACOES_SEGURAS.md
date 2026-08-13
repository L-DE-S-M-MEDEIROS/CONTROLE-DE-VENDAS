# Arquitetura de atualização segura

## Fluxo implementado

1. Na abertura do aplicativo e pelo botão **Configurações → Verificar atualizações**, o programa consulta `releases/latest` da API pública do GitHub.
2. A versão instalada e a tag publicada são comparadas com Semantic Versioning usando a biblioteca `packaging`.
3. O programa procura exclusivamente os anexos exatos `ControleDeVendas-Setup.exe` e `SHA256.txt`. Os arquivos automáticos de código-fonte do GitHub não são usados.
4. A janela de atualização mostra versão instalada, nova versão, descrição, **Baixar atualização** e **Agora não**.
5. O download mostra progresso. O instalador fica com extensão temporária `.part` e só recebe o nome final depois que seu SHA-256 coincide com o valor publicado.
6. Depois da validação há uma segunda confirmação: a instalação nunca começa sem autorização do usuário.
7. Antes de iniciar o instalador, o banco SQLite recebe um backup adicional.
8. O instalador preserva o executável anterior como `ControleDeVendas.rollback.exe`. Em caso de falha durante a troca, restaura automaticamente essa cópia. Quando disponível, **Configurações → Restaurar versão anterior** executa o rollback.

Os dados da empresa permanecem em `%LOCALAPPDATA%\ControleDeVendas`, enquanto o programa fica em `%LOCALAPPDATA%\Programs\Vendas PRO`. Assim, substituir ou recuperar o programa não substitui o banco.

## Repositório público

O repositório atual é público. Por isso, consultar a Release e baixar seus anexos não exige token. O aplicativo não contém senha, token do GitHub, credencial do Google ou outro segredo.

## Se o repositório se tornar privado

Não se deve inserir um Personal Access Token ou token administrativo no EXE: qualquer segredo embutido em um aplicativo desktop pode ser extraído.

A solução segura é um pequeno serviço intermediário autenticado:

- a chave privada do GitHub App fica somente no servidor/gerenciador de segredos;
- o serviço gera um token de instalação de curta duração e com permissão mínima apenas para ler Releases;
- após autenticar o usuário, o serviço entrega o arquivo ou uma URL temporária;
- o aplicativo continua exigindo SHA-256 e autorização antes de instalar;
- nenhum token permanente chega ao computador do usuário.

Também é recomendável assinar digitalmente o instalador com um certificado de assinatura de código antes de distribuir em produção. SHA-256 verifica integridade; assinatura de código também permite ao Windows verificar a identidade do publicador.

## Falhas tratadas

- sem internet, timeout e erros HTTP;
- Release ausente ou ainda em pré-lançamento;
- versão fora do padrão;
- instalador ou SHA-256 ausente;
- endereço de download fora dos domínios oficiais do GitHub;
- download incompleto;
- arquivo adulterado ou hash malformado;
- falha de instalação, com restauração da cópia anterior.
