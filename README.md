# Registro de ocorrências em laboratórios — MVP didático

Aplicação demonstrativa da disciplina **Transformação Digital**. O projeto permite registrar ocorrências, acompanhar o atendimento e mostrar como as telas se conectam ao backend e ao banco PostgreSQL.

Os nomes, chamados, contatos, locais e demais registros que aparecem no sistema são fictícios. Use o MVP apenas para aprendizado, sem dados reais.

## Como o projeto está organizado

- `backend/`: aplicação web e API em Python/Flask; conexão e criação das tabelas no PostgreSQL existente.
- `frontend/`: páginas HTML, estilos CSS e JavaScript. O Flask serve essas páginas, portanto não é necessário iniciar um servidor de frontend separado.
- `backend/.env.example`: modelo das configurações locais. Cada pessoa cria seu próprio arquivo `.env` a partir dele.

## Requisitos

Os comandos de instalação e execução abaixo são para **Windows com PowerShell**.

Instale antes de começar:

1. **Git for Windows**, para baixar o repositório ([instalador oficial](https://git-scm.com/install/windows)).
2. **Python 3.10 ou superior**, incluindo o `py` launcher ([downloads oficiais para Windows](https://www.python.org/downloads/windows/)).
3. **PostgreSQL Server** instalado e em execução ([downloads oficiais](https://www.postgresql.org/download/)). Durante a instalação, defina e guarde a senha do usuário `postgres`. O padrão usado neste guia é host `127.0.0.1`, porta `5432`.
4. Acesso à internet para instalar as dependências Python e carregar o Bootstrap pelo CDN.

O **DBeaver é opcional**: pode ser usado para inspecionar as tabelas e o diagrama do banco. O projeto usa Psycopg 3 com pacote binário, então não é necessário instalar compilador ou bibliotecas PostgreSQL de desenvolvimento. Consulte os guias oficiais de [instalação do Psycopg](https://www.psycopg.org/psycopg3/docs/basic/install.html) e [instalação do Flask](https://flask.palletsprojects.com/en/stable/installation/).

## 1. Baixar o código do GitHub

Na página do repositório público, clique em **Code → HTTPS** e copie o endereço. No PowerShell, execute:

```powershell
git clone https://github.com/cristianooliveirafasam/transformacao_digital_mvp.git
cd transformacao_digital_mvp
```

O repositório público é `cristianooliveirafasam/transformacao_digital_mvp`.

## 2. Configurar a conexão com o PostgreSQL

Verifique se o serviço PostgreSQL está em execução. Se necessário, abra **Serviços** no Windows e inicie o serviço PostgreSQL instalado. O padrão do projeto é:

- Host: `127.0.0.1`
- Porta: `5432`
- Banco: `transformacao_digital_mvp`
- Usuário inicial: `postgres`

Abra uma conexão administrativa no PostgreSQL e confirme que a senha do usuário está disponível. O backend cria as tabelas e os registros fictícios na primeira execução, mas não cria o banco. Crie `transformacao_digital_mvp` previamente no PostgreSQL local ou use um banco já existente.

Para criar o banco pelo DBeaver, conecte-se ao banco padrão postgres e execute:

``sql
CREATE DATABASE transformacao_digital_mvp;
``



### Criar o arquivo local `.env`

Abra o PowerShell na pasta do repositório e entre no backend:

```powershell
cd backend
Copy-Item .env.example .env
notepad .env
```

No `.env`, configure os dados do **seu PostgreSQL local**. Exemplo:

```dotenv
PGHOST=127.0.0.1
PGPORT=5432
PGDATABASE=transformacao_digital_mvp
PGUSER=postgres
PGPASSWORD=sua_senha_local_do_postgres
```

Troque `sua_senha_local_do_postgres` pela senha definida na instalação do PostgreSQL. Não coloque essa senha no README, no código ou em commits públicos. O arquivo `backend/.env` está listado no `.gitignore`.

Também substitua `FLASK_SECRET_KEY` por uma chave aleatória. Gere uma no PowerShell:

```powershell
py -c "import secrets; print(secrets.token_hex(32))"
```

Copie o valor gerado para `FLASK_SECRET_KEY` no `.env`. As configurações SMTP podem ficar vazias: o MVP continua exibindo avisos dentro do sistema.

## 3. Instalar as dependências Python

Ainda na pasta `backend`, crie um ambiente virtual e instale as dependências:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

O ambiente virtual mantém as bibliotecas deste projeto separadas das demais instalações Python da máquina. Não é necessário ativá-lo: os comandos abaixo chamam diretamente o Python instalado em `.venv`.

## 4. Iniciar o sistema

Com o terminal ainda na pasta `backend`, execute:

```powershell
.\.venv\Scripts\python.exe app.py
```

Na primeira inicialização, o backend conecta ao banco já existente, cria as tabelas e insere os registros fictícios iniciais. Quando o servidor indicar que está em execução, abra:

**http://127.0.0.1:5000**

O frontend é carregado pelo próprio backend Flask. Para encerrar o servidor, volte ao terminal e pressione `Ctrl+C`.

## 5. Entrar com as contas de demonstração

| Perfil | E-mail | Senha |
| --- | --- | --- |
| Aluna | `aluna@example.test` | `aluno123` |
| Aluno | `cristiano@example.test` | `aluno123` |
| Técnico | `tecnico@example.test` | `tecnico123` |

As senhas das contas de demonstração são diferentes da senha do PostgreSQL. Elas são apenas para navegar pelo MVP local.

## 6. Consultar as tabelas no DBeaver (opcional)

Crie uma conexão PostgreSQL com os valores configurados no `.env`. Na árvore do banco `transformacao_digital_mvp`, as tabelas principais são:

- `users`: contas e papéis de acesso.
- `tickets`: chamados, status e responsável.
- `ticket_events`: histórico das ações em cada chamado.
- `notifications`: avisos exibidos aos usuários.

No DBeaver, clique com o botão direito em uma tabela ou no esquema e escolha **ER Diagram** para visualizar as relações. Os registros são todos fictícios.

## Atualizar o código depois

Para baixar mudanças publicadas no GitHub, pare o servidor com `Ctrl+C`, abra o terminal na pasta principal do repositório e execute:

```powershell
git pull
```

Se o arquivo `requirements.txt` mudou, atualize também as dependências, a partir da pasta `backend`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Depois, inicie novamente com `.\.venv\Scripts\python.exe app.py`.

## Problemas comuns

### Não foi possível conectar ao servidor PostgreSQL

Confirme que o serviço está rodando e que `PGHOST` e `PGPORT` no `.env` correspondem à instalação local. O padrão é `127.0.0.1:5432`.

### Falha de autenticação ou senha incorreta

Revise `PGUSER` e `PGPASSWORD` no arquivo `.env`. Essa é a senha do PostgreSQL local, não uma das senhas das contas de demonstração.

### O backend informa que não existe o banco

Confirme que `PGDATABASE` aponta para um banco PostgreSQL já criado e que as credenciais configuradas podem criar tabelas nele.

### A porta 5000 já está em uso

Altere `APP_PORT` no `.env` para outra porta livre, por exemplo `5001`, reinicie o backend e abra `http://127.0.0.1:5001`.

## Limites e cuidados

- O projeto é um MVP didático e não está preparado para uso institucional ou produção.
- Não use dados reais, senhas pessoais ou informações sensíveis.
- Os avisos são internos ao sistema; e-mail depende de configuração SMTP. Não há integração com SMS ou WhatsApp.
- Não publique o arquivo `.env`. Se ele for enviado ao GitHub por engano, remova-o do repositório e troque as credenciais expostas.

## Publicar no Cloud Run com GitHub Actions

O repositório também contém um `Dockerfile` e dois workflows do GitHub Actions:

- **Build container**: monta a imagem em pull requests e em atualizações da branch `main`.
- **Deploy to Cloud Run**: publica a imagem no Artifact Registry e atualiza o serviço Cloud Run quando as variáveis de autenticação OIDC do Google estiverem configuradas.

A publicação usa Workload Identity Federation (OIDC), sem chave permanente de conta de serviço. O passo a passo de APIs, contas de serviço, permissões e configuração do Supabase está em [`docs/deploy-cloud-run.md`](docs/deploy-cloud-run.md).

O container cria as tabelas ao iniciar, no banco indicado por `PGDATABASE`. Para o Supabase, use a conexão **Session Pooler** exibida no painel do projeto, configure `PGSSLMODE=require` e cadastre os valores como segredos do Secret Manager. Nunca copie o conteúdo de `backend/.env` para o repositório.

O serviço é público para permitir que os alunos abram a tela de login; os dados de demonstração são fictícios e as contas de exemplo são compartilhadas. Use apenas como demonstração didática, não para dados reais.



