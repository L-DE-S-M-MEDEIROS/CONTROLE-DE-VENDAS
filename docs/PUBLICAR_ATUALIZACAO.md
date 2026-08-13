# Como publicar uma nova versão

O GitHub Releases é a única fonte oficial das atualizações.

## Publicação automática

1. Escolha um número Semantic Versioning ainda não usado, por exemplo `1.4.0`.
2. Altere `__version__` em `sales_control/__init__.py`.
3. Registre as novidades em `CHANGELOG.md` e faça os testes locais:

   ```powershell
   python -m unittest discover -v
   .\build_exe.ps1
   Get-FileHash outputs\ControleDeVendas-Setup.exe -Algorithm SHA256
   Get-Content outputs\SHA256.txt
   ```

4. Envie as alterações para a branch `main` do repositório `L-DE-S-M-MEDEIROS/CONTROLE-DE-VENDAS`.
5. O workflow `.github/workflows/release.yml` executará os testes, gerará o aplicativo, criará a tag `v1.4.0` e publicará uma Release com notas automáticas.
6. Confirme na página da Release que existem exatamente estes anexos:

   - `ControleDeVendas-Setup.exe`
   - `SHA256.txt`

7. Abra `SHA256.txt`, calcule o SHA-256 do instalador baixado e confira se os valores coincidem.
8. Edite a descrição da Release se quiser complementar o changelog gerado automaticamente.

É obrigatório aumentar a versão antes de uma nova publicação. Não reutilize uma tag já distribuída.

## Publicação manual de recuperação

Se o workflow não puder ser usado:

1. Execute `.\build_exe.ps1` em Windows.
2. No GitHub, abra **Releases → Draft a new release**.
3. Crie uma tag nova no formato `vMAIOR.MENOR.CORREÇÃO`, igual à versão do código; exemplo: `v1.4.0`.
4. Preencha o título e a descrição/changelog.
5. Anexe somente o instalador gerado e o respectivo `SHA256.txt`.
6. Marque como Release estável, não como pre-release, e publique.

O aplicativo ignora os links automáticos “Source code” e recusa uma Release sem os dois anexos exigidos.

## Teste de ponta a ponta

1. Instale a versão anterior em uma máquina de teste e cadastre cliente, produto e venda.
2. Publique uma versão maior.
3. Abra a versão anterior ou use **Configurações → Verificar atualizações**.
4. Confira as duas versões e o changelog, baixe e observe o progresso.
5. Autorize a instalação somente após a mensagem de SHA-256 validado.
6. Verifique que clientes, produtos e vendas continuam disponíveis.
7. Use **Restaurar versão anterior** para validar a recuperação e confirme novamente os dados.
