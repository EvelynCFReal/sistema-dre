# Manual do Sistema de DRE

## 1. Visao Geral

O **Sistema de DRE** (Demonstracao do Resultado do Exercicio) e uma aplicacao web para gestao financeira de multiplas lojas/empresas. Permite registrar faturamentos, despesas e gerar relatorios financeiros detalhados.

- **Periodo operacional:** 2026 a 2036
- **Idioma:** Portugues do Brasil (PT-BR)
- **Fuso horario:** America/Sao_Paulo (Brasilia, UTC-3)
- **Stack:** Python (Flask) + SQLite + Docker + Nginx + Gunicorn

---

## 2. Tipos de Usuario

O sistema possui 4 niveis de acesso:

### 2.1 Usuario Master
- Acesso total ao sistema
- Acessa todas as lojas
- Acessa todas as abas: Dashboards, Lancamentos, DRE Mensal, Usuarios e Empresas, Parametros Gerais, API
- Cria, edita, bloqueia e exclui usuarios
- Cria e gerencia lojas/empresas
- Gerencia todos os parametros gerais
- Exclui permanentemente itens dos parametros
- Altera porcentagens e taxas
- Alterna entre tema claro e escuro
- Gera e revoga chaves de API

### 2.2 Usuario Gestor
- Acessa apenas as lojas onde possui perfil de gestor
- Acessa: Dashboards, Lancamentos, DRE Mensal, Usuarios e Empresas, Parametros Gerais
- Pode criar usuarios do tipo Loja e Leitor **apenas nas lojas onde e gestor**
- Pode alterar porcentagens e taxas
- Pode incluir e excluir: categorias, marcas, tipos de faturamento, tipos de despesa
- Pode alterar senha e bloquear usuario loja
- Desativa itens (nao exclui permanentemente)

### 2.3 Usuario Loja
- Acessa apenas a aba de **Lancamentos** (tela inicial)
- **Nao acessa** Dashboards, DRE Mensal, Gestao ou Parametros Gerais
- Pode lancar apenas nas lojas e meses autorizados
- Nao pode excluir nada
- Nao pode alterar porcentagens ou parametros estruturais

### 2.4 Usuario Leitor
- Acesso apenas para **visualizacao**
- Pode visualizar Dashboards e DRE Mensal
- **Nao acessa** Lancamentos, Gestao ou Parametros Gerais
- Nao edita, cria ou exclui nada

---

## 3. Permissoes por Loja (Multilojas)

As permissoes sao aplicadas **por loja**, nunca de forma global.

- Um mesmo usuario pode ter perfis diferentes em lojas diferentes
- Exemplo: gestor na Loja A e leitor na Loja B
- O seletor de loja no topo da tela permite alternar entre lojas autorizadas
- A loja selecionada fica travada para todo o sistema ate que o usuario selecione outra
- Dados de uma loja **nunca** aparecem na visualizacao de outra

### Regras do Gestor na criacao de acessos:
- So pode vincular novos usuarios as lojas onde ele proprio e gestor
- Nao pode criar acesso para lojas onde nao tenha perfil de gestor

---

## 4. Como Cadastrar uma Empresa/Loja

1. Faca login como **Master**
2. Acesse **Gestao > Usuarios e Empresas**
3. Na secao "Empresas / Lojas", clique em **+ Criar Loja**
4. Preencha o nome e CNPJ
5. Apos criar, clique no botao de edicao para configurar:
   - Razao social, endereco, telefone, e-mail
   - Logo da empresa (imagem PNG/JPG)
   - Cores da identidade visual (primaria, secundaria, fundo, texto)
   - Tema (claro ou escuro)

---

## 5. Como Configurar Identidade Visual

Cada loja pode ter identidade visual propria:

1. Em **Usuarios e Empresas**, edite a loja desejada
2. Faca upload do logo
3. Defina as cores (primaria, secundaria, fundo, texto)
4. Quando a loja esta selecionada, o sistema adota suas cores
5. O usuario Master pode alternar entre tema claro e escuro no menu lateral

---

## 6. Como Cadastrar Usuarios

1. Acesse **Gestao > Usuarios e Empresas**
2. No formulario "Novo Usuario", preencha:
   - Nome completo
   - Login (unico no sistema)
   - Senha inicial (minimo 6 caracteres)
   - Tipo de usuario (Gestor, Loja ou Leitor)
3. Na secao **Vincular as Lojas**, adicione uma ou mais lojas:
   - Selecione a loja
   - Defina o perfil nessa loja (Gestor, Loja ou Leitor)
   - Clique em "+ Adicionar outra loja" para multilojas
4. Clique em **Criar Usuario**

---

## 7. Como Configurar Multilojas

O sistema permite que um usuario tenha acesso a multiplas lojas com perfis diferentes:

1. Na criacao do usuario, adicione multiplas linhas de vinculo
2. Para editar vinculos existentes, clique no botao de edicao do usuario
3. Cada loja pode ter um perfil diferente (gestor, loja ou leitor)
4. O sistema respeita o perfil separadamente em cada loja

---

## 8. Como Lancar Informacoes

1. Acesse **Lancamentos**
2. Selecione o tipo: Caixa, Despesa ou Aporte/Sangria
3. Preencha:
   - **Caixa:** data, turno, forma de pagamento, plataforma (opcional), valor
   - **Despesa:** data, categoria, valor, descricao (opcional)
   - **Aporte/Sangria:** data, tipo, valor, descricao (opcional)
4. A data deve estar dentro do intervalo do ano selecionado (2026-2036)
5. Usuarios do tipo Loja so podem lancar nos meses liberados pelo gestor/master

### Turnos disponiveis:
- Almoco (CX 1)
- Jantar (CX 2)
- Pos-meia-noite (CX 3)

---

## 9. Como Visualizar Dashboards

1. Acesse **Dashboards** (disponivel para Master, Gestor e Leitor)
2. O dashboard exibe dados do **ano selecionado** no seletor global
3. Use o seletor de loja no topo para alternar entre lojas
4. Graficos disponiveis:
   - Faturamento e Resultado por mes
   - Despesas por categoria
   - Faturamento por plataforma
   - Margem de resultado por mes
   - Comparativo multi-ano (2026 a 2036)
5. Visao geral dos 12 meses com cards clicaveis
6. Botao **Imprimir** para gerar relatorio resumido

---

## 10. Como Usar o DRE Mensal

1. No menu lateral, em **DRE Mensal**, clique no mes desejado
2. O DRE mostra:
   - KPIs: faturamento bruto, liquido, despesas e resultado
   - Faturamento por forma de pagamento com taxas
   - Faturamento por plataforma/app com detalhe por turno
   - Apuracao completa do resultado
   - Composicao das despesas em grafico
   - Detalhamento das despesas por categoria
3. Navegue entre meses com os botoes de seta
4. Botao de impressao para gerar relatorio do mes

---

## 11. Como Usar a API

1. Acesse **Gestao > Parametros Gerais** (como Master)
2. Na secao "Chaves de API", crie uma nova chave:
   - Defina nome, loja (opcional) e permissoes (leitura/escrita)
3. A chave gerada (formato `snm_xxx`) deve ser incluida em todas as requisicoes
4. Acesse **API** no menu lateral para ver a documentacao completa

### Autenticacao:
```
Header: X-API-Key: snm_sua_chave
Query:  ?api_key=snm_sua_chave
```

### Principais endpoints:
- `GET /api/v1/status` — Status do sistema
- `GET /api/v1/dre/{loja_id}/{ano}/{mes}` — DRE de um mes
- `GET /api/v1/resumo-anual/{loja_id}/{ano}` — Resumo anual
- `POST /api/v1/lancamentos/caixa` — Lancar caixa via API
- `POST /api/v1/lancamentos/despesa` — Lancar despesa via API
- `GET /api/v1/lojas` — Listar lojas
- `GET /api/v1/formas-pagamento` — Listar formas de pagamento
- `GET /api/v1/categorias-despesa` — Listar categorias
- `GET /api/v1/plataformas` — Listar plataformas

---

## 12. Como Imprimir Relatorios

### Relatorio Resumido (Dashboard)
1. Acesse o Dashboard
2. Clique no botao **Imprimir** no topo
3. O navegador abrira a tela de impressao com layout otimizado

### Relatorio Detalhado (DRE Mensal)
1. Acesse o DRE do mes desejado
2. Clique no botao de impressao no topo
3. O DRE completo sera formatado para impressao

---

## 13. Seletor Global de Ano

O seletor de ano fica no menu lateral, abaixo do logo:

- Permite navegar entre **2026 e 2036**
- O ano selecionado impacta **todas as telas** do sistema:
  - Dashboards mostram dados do ano selecionado
  - DRE Mensal exibe o mes dentro do ano selecionado
  - Lancamentos filtram pelo ano selecionado
- O comportamento e consistente em todas as areas

---

## 14. Parametros Gerais

Acessivel por Master e Gestor em **Gestao > Parametros Gerais**:

- **Configuracoes do DRE:** royalties, verba de marketing, meta de faturamento
- **Formas de Pagamento / Taxas:** criar, alterar taxa, excluir
- **Plataformas / Apps:** criar, excluir
- **Categorias de Despesa:** criar com tipo (CMV, Fixa, etc.), excluir
- **Marcas:** criar, excluir
- **Tipos de Faturamento:** criar, excluir
- **Tipos de Despesa:** criar, excluir
- **Tipos de Lancamento:** criar, excluir
- **Chaves de API:** criar, revogar (somente Master)

### Regras de exclusao:
- **Master:** exclui permanentemente
- **Gestor:** desativa (soft delete)
