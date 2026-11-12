# Configurar a publicação no Google Cloud

Este guia prepara o serviço demonstrativo para publicar uma imagem Docker no Cloud Run quando uma alteração chega à branch `main`. O workflow usa GitHub Actions OIDC (Workload Identity Federation), sem armazenar uma chave permanente do Google no repositório.

## 1. Confirmar acesso ao projeto

No Google Cloud CLI, confira que a conta ativa tem acesso ao projeto `transformacao-digital-mvp`:

```powershell
gcloud auth list
gcloud projects describe transformacao-digital-mvp
```

Se o segundo comando retornar `PERMISSION_DENIED`, selecione a conta que tem acesso ou peça ao administrador do projeto que conceda as permissões de implantação descritas abaixo. Nome de usuário e senha de uma conta Google não substituem autenticação do gcloud e não devem ser salvos no GitHub.

## 2. Preparar variáveis do GitHub

No repositório `cristianooliveirafasam/transformacao_digital_mvp`, abra **Settings → Secrets and variables → Actions → Variables** e crie:

| Variável | Valor sugerido |
| --- | --- |
| `GCP_PROJECT_ID` | `transformacao-digital-mvp` |
| `GCP_REGION` | `us-central1` |
| `GCP_SERVICE_NAME` | `registro-ocorrencias-mvp` |
| `GCP_ARTIFACT_REPOSITORY` | `registro-ocorrencias` |
| `GCP_RUNTIME_SERVICE_ACCOUNT` | e-mail da conta de serviço de execução criada no próximo passo |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | nome completo do provider OIDC criado no passo 3 |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | e-mail da conta de serviço usada pelo workflow |

Estas variáveis identificam recursos, não contêm senhas. A região `us-central1` mantém o serviço em uma região com franquia gratuita do Cloud Run; compare com a região do projeto Supabase para reduzir latência e tráfego entre regiões.

## 3. Criar identidade do workflow (OIDC)

Os comandos abaixo são executados por uma conta que tenha permissão para ativar APIs, criar contas de serviço e configurar Workload Identity no projeto. Confirme o projeto antes de executá-los:

```powershell
$PROJECT_ID = "transformacao-digital-mvp"
$PROJECT_NUMBER = gcloud projects describe $PROJECT_ID --format="value(projectNumber)"
$POOL = "github-actions"
$PROVIDER = "github"
$DEPLOYER = "github-deployer"
$RUNTIME = "cloudrun-runtime"
$OWNER_REPO = "cristianooliveirafasam/transformacao_digital_mvp"

gcloud services enable run.googleapis.com artifactregistry.googleapis.com `
  iam.googleapis.com iamcredentials.googleapis.com secretmanager.googleapis.com `
  --project $PROJECT_ID

gcloud iam service-accounts create $DEPLOYER --project $PROJECT_ID
gcloud iam service-accounts create $RUNTIME --project $PROJECT_ID

gcloud iam workload-identity-pools create $POOL --project $PROJECT_ID `
  --location=global --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc $PROVIDER `
  --project $PROJECT_ID --location=global --workload-identity-pool=$POOL `
  --issuer-uri="https://token.actions.githubusercontent.com" `
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" `
  --attribute-condition="assertion.repository == '$OWNER_REPO' && assertion.ref == 'refs/heads/main'"

$DEPLOYER_EMAIL = "$DEPLOYER@$PROJECT_ID.iam.gserviceaccount.com"
$RUNTIME_EMAIL = "$RUNTIME@$PROJECT_ID.iam.gserviceaccount.com"
$MEMBER = "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository/$OWNER_REPO"

gcloud iam service-accounts add-iam-policy-binding $DEPLOYER_EMAIL `
  --project $PROJECT_ID --role=roles/iam.workloadIdentityUser --member=$MEMBER

gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="serviceAccount:$DEPLOYER_EMAIL" --role=roles/run.admin
gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="serviceAccount:$DEPLOYER_EMAIL" --role=roles/artifactregistry.admin
gcloud artifacts repositories create registro-ocorrencias --project $PROJECT_ID `
  --repository-format=docker --location=us-central1

gcloud iam service-accounts add-iam-policy-binding $RUNTIME_EMAIL `
  --project $PROJECT_ID --member="serviceAccount:$DEPLOYER_EMAIL" `
  --role=roles/iam.serviceAccountUser

$PROVIDER_NAME = "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER"
"GCP_WORKLOAD_IDENTITY_PROVIDER=$PROVIDER_NAME"
"GCP_DEPLOY_SERVICE_ACCOUNT=$DEPLOYER_EMAIL"
"GCP_RUNTIME_SERVICE_ACCOUNT=$RUNTIME_EMAIL"
```

Copie os três valores exibidos para as variáveis correspondentes do GitHub. O vínculo do provider restringe a identidade a este repositório e à branch `main`.

## 4. Salvar a configuração do PostgreSQL no Secret Manager

No painel do Supabase, use os dados de conexão do **Session Pooler** (indicado para aplicações persistentes em redes IPv4). Crie estes segredos no Secret Manager do projeto, cada um com o valor correspondente da conexão:

- `FLASK_SECRET_KEY`: chave aleatória longa para a sessão Flask.
- `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`: dados do Session Pooler.

A conta `cloudrun-runtime` precisa da permissão **Secret Manager Secret Accessor** nesses seis segredos. Conceda-a em cada segredo, para limitar o acesso. A senha e o host do banco não devem ser inseridos em variáveis públicas do GitHub, em arquivos versionados ou no `Dockerfile`.

## 5. Executar o primeiro deploy

Depois de criar as variáveis, os segredos e as permissões, envie uma alteração para `main`. O workflow de CI/CD monta primeiro a imagem. Após o build aprovado, o job **Deploy to Cloud Run** publica no Artifact Registry e atualiza o Cloud Run. O serviço escala para zero quando está ocioso, com no máximo uma instância para manter o MVP dentro dos limites esperados para uma demonstração.

Acesse a URL de serviço apresentada pelo Cloud Run. A rota `/healthz` verifica a conexão com o PostgreSQL. Na primeira inicialização, o container cria as tabelas e os registros fictícios de exemplo.

## Limites da demonstração

O plano gratuito do Supabase pode pausar um banco com pouca atividade. O Cloud Run pode cobrar consumo que exceder as franquias gratuitas, e o tráfego entre regiões pode gerar custos ou latência. Configure um alerta de orçamento no Google Cloud e monitore também o consumo do Supabase. Alertas avisam; eles não interrompem automaticamente o consumo.


