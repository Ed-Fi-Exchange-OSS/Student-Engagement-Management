# Installation Instructions

> [!NOTE]
> Please review these instructions carefully and adjust as needed to ensure they satisfy your
> secure deployment requirements.

## Setup:

Clone this repository and create a new .env file with the following variables defined:
```env
# Gcp project in which the kubernetes cluster lives:
GOOGLE_CLOUD_PROJECT=

# used for multiple things to describe dagster/deployment instance (Ex: "test-env"):
INSTANCE_NAME=

# used for BigQuery naming convention and must not use dash characters (Ex: "test_env"):
BQ_INSTANCE_NAME=

# GCP Region (Ex: "us-central1"):
GCP_REGION=

# Usually internal IP of cloud sql server within vpc network:
DAGIT_POSTGRES_HOST=

# Password used for the postgres host:
POSTGRES_PASSWORD=

# EdFi API Key, Secret, and Base url. Obtained from Admin App:
EDFI_API_KEY=
EDFI_API_SECRET=
EDFI_BASE_URL=

# School Year used for EdFi API:
CURRENT_SCHOOL_YEAR=

# The rest may be left unaltered, but must be included in the .env file
SQL_INSTANCE_NAME=${INSTANCE_NAME}-db
REPOSITORY_NAME=dagster-${INSTANCE_NAME}
RESERVED_IP_NAME=${INSTANCE_NAME}
CLUSTER_NAME=${INSTANCE_NAME}
NETWORK_NAME=${INSTANCE_NAME}

GCS_BUCKET_DEV=${GOOGLE_CLOUD_PROJECT}-${INSTANCE_NAME}-dev
GCS_BUCKET_PROD=${GOOGLE_CLOUD_PROJECT}-${INSTANCE_NAME}
GCP_ZONE=${GCP_REGION}-a
GKE_CONTEXT=gke_${GOOGLE_CLOUD_PROJECT}_${GCP_REGION}_${INSTANCE_NAME}
GOOGLE_APPLICATION_CREDENTIALS=/opt/dagster/app/dbt/service.json

DAGSTER_HOME=/opt/dagster/dagster_home
PYTHONPATH=/opt/dagster/app/project
DBT_PROFILES_DIR=/opt/dagster/app
DBT_PROJECT_DIR=/opt/dagster/app/dbt
```
Then source the .env file:
```bash
source .env
```
Set project, compute region,  and enable services as needed:
```bash
gcloud config set project $GOOGLE_CLOUD_PROJECT;
gcloud config set compute/region $GCP_REGION;

gcloud services enable artifactregistry.googleapis.com;
gcloud services enable cloudbuild.googleapis.com;
gcloud services enable compute.googleapis.com;
gcloud services enable container.googleapis.com;
gcloud services enable servicenetworking.googleapis.com;
gcloud services enable sqladmin.googleapis.com;
gcloud services enable iamcredentials.googleapis.com;
```
## Network:

Create a new network for the instance to operate within:
```bash
gcloud compute networks create $NETWORK_NAME
```
Create new firewall rules:
```bash
gcloud compute --project=$GOOGLE_CLOUD_PROJECT firewall-rules create $NETWORK_NAME-allow-internal --description="Allow internal traffic on the $NETWORK_NAME network" --direction=INGRESS --priority=65534 --network=$NETWORK_NAME --action=ALLOW --rules=tcp:0-65535,udp:0-65535,icmp --source-ranges=10.128.0.0/9

gcloud compute --project=$GOOGLE_CLOUD_PROJECT firewall-rules create $NETWORK_NAME-allow-icmp --description="Allow ICMP from anywhere" --direction=INGRESS --priority=65534 --network=$NETWORK_NAME --action=ALLOW --rules=icmp --source-ranges=0.0.0.0/0

gcloud compute --project=$GOOGLE_CLOUD_PROJECT firewall-rules create $NETWORK_NAME-allow-ssh --description="Allow SSH from anywhere" --direction=INGRESS --priority=65534 --network=$NETWORK_NAME --action=ALLOW --rules=tcp:22 --source-ranges=0.0.0.0/0

gcloud compute --project=$GOOGLE_CLOUD_PROJECT firewall-rules create $NETWORK_NAME-allow-rdp --description="Allow RDP from anywhere" --direction=INGRESS --priority=65534 --network=$NETWORK_NAME --action=ALLOW --rules=tcp:3389 --source-ranges=0.0.0.0/0
```
Create router and nat for new network:
```bash
gcloud compute routers create $NETWORK_NAME --region $GCP_REGION --network $NETWORK_NAME --project=$GOOGLE_CLOUD_PROJECT

gcloud compute routers nats create nat-$NETWORK_NAME --router=$NETWORK_NAME  --region=$GCP_REGION --auto-allocate-nat-external-ips --nat-all-subnet-ip-ranges --project=$GOOGLE_CLOUD_PROJECT
```
Create vpc peering service:
```bash
gcloud compute addresses create google-managed-services-$NETWORK_NAME \
    --global \
    --purpose=VPC_PEERING \
    --prefix-length=16 \
    --description="peering range" \
    --network=$NETWORK_NAME;
```

## SQL:
Create service account with access to cloud sql:
```bash
gcloud iam service-accounts create cloud-sql-proxy;
gcloud projects add-iam-policy-binding $GOOGLE_CLOUD_PROJECT \
    --member="serviceAccount:cloud-sql-proxy@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role=roles/cloudsql.client;
```
Connect to vpc to create cloud sql instance:
```bash
gcloud services vpc-peerings connect \
    --service=servicenetworking.googleapis.com \
    --ranges=google-managed-services-$NETWORK_NAME \
    --network=$NETWORK_NAME \
    --project=$GOOGLE_CLOUD_PROJECT;
```
Create cloud sql instance, taking note of the cidr block < ex: 10.48.0.0/20 >:
```bash
gcloud beta sql instances create \
  --zone $GCP_ZONE \
  --database-version POSTGRES_11 \
  --memory 7680MiB \
  --cpu 2 \
  --storage-auto-increase \
  --network=projects/$GOOGLE_CLOUD_PROJECT/global/networks/$NETWORK_NAME \
  --backup-start-time 08:00 $SQL_INSTANCE_NAME;
```
Set password for postgres user:
```bash
gcloud sql users set-password postgres --password $POSTGRES_PASSWORD --instance=$SQL_INSTANCE_NAME;
```
Create dagster database in the existing cloud sql instance:
```bash
gcloud sql databases create 'dagster' --instance=$SQL_INSTANCE_NAME
```

## GKE:
Set compute region:
```bash
gcloud config set compute/region $GCP_REGION ;
```
The production job uses the Google Cloud Storage (GCS) IO manager. This requires a GCS bucket.
```bash
gsutil mb gs://$GCS_BUCKET_PROD
```
Create artifact registry repository:
```bash
gcloud artifacts repositories create $REPOSITORY_NAME \
    --project=$GOOGLE_CLOUD_PROJECT \
    --repository-format=docker \
    --location=$GCP_REGION \
    --description="Docker repository";
```
Create gke autopilot cluster:
```bash
gcloud container clusters create-auto $REPOSITORY_NAME \
--network=$NETWORK_NAME \
--subnetwork=$NETWORK_NAME \
--private-endpoint-subnetwork=$NETWORK_NAME \
--enable-master-authorized-networks \
--region $GCP_REGION \
--master-authorized-networks < postgress network cidr from SQL creation. Ex: 10.48.0.0/20 >
```
Switch to GKE cluster for deployment:
```bash
kubectl config use-context $GKE_CONTEXT
```
Get credentials for cluster:
```bash
gcloud container clusters get-credentials $CLUSTER_NAME --region=$GCP_REGION
```
Create secrets and config maps for the deployment:
```bash
kubectl create secret generic cloud-sql-creds \
  --from-literal=username=postgres \
  --from-literal=password=$POSTGRES_PASSWORD;
  
kubectl create secret generic dagster-gcs-bucket-name --from-literal=GCS_BUCKET_NAME=$GCS_BUCKET_PROD;

kubectl create secret generic dagster-postgresql-secret --from-literal=postgresql-password=$POSTGRES_PASSWORD;

kubectl create configmap dagster-lea-vars \
    --from-literal GCS_BUCKET_DEV=$GCS_BUCKET_DEV \
    --from-literal GCS_BUCKET_PROD=$GCS_BUCKET_PROD \
    --from-literal DBT_PROJECT_DIR=$DBT_PROJECT_DIR \
    --from-literal DBT_PROFILES_DIR=$DBT_PROFILES_DIR \
    --from-literal DBT_TARGET=$DBT_TARGET \
    --from-literal BQ_INSTANCE_NAME=$BQ_INSTANCE_NAME \
    --from-literal CURRENT_SCHOOL_YEAR=$CURRENT_SCHOOL_YEAR \
    --from-literal GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT;

kubectl create secret generic dagster-edfi-api \
    --from-literal EDFI_BASE_URL=$EDFI_BASE_URL \
    --from-literal EDFI_API_KEY=$EDFI_API_KEY \
    --from-literal EDFI_API_SECRET=$EDFI_API_SECRET;
```
Create service account in gke cluster:
```bash
kubectl apply -f kubernetes/sql-service-account.yaml;
```
Bind kubernetes service account to google service account and annotate:
```bash
gcloud iam service-accounts add-iam-policy-binding \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:$GOOGLE_CLOUD_PROJECT.svc.id.goog[default/cloud-sql-proxy]" \
  cloud-sql-proxy@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com;

kubectl annotate serviceaccount \
  cloud-sql-proxy \
  iam.gke.io/gcp-service-account=cloud-sql-proxy@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com;
```
The file deployment-pgbouncer.yaml should be modified to replace environment variables with their actual values before deploying with kubctl. Deployment-pgbouncer.yaml.yaml can be updated from environment variables by exporting the variables:
```bash
set -a && source .env && set +a
```
Then using the envsubst command:
```bash
envsubst < kubernetes/deployment-pgbouncer.yaml > kubernetes/deployment-pgbouncer-env.yaml
```
Deploy pgbouncer with cloud sql proxy sidecar:
```bash
kubectl apply -f kubernetes/deployment-pgbouncer-env.yaml;
kubectl apply -f kubernetes/service-pgbouncer.yaml;
```
Create Dagster service account in Google:
```bash
gcloud iam service-accounts create dagster
```
Bind Dagster service account and annotate:
- *Note: the dagster service account for the kubenetes cluster is created by the Helm deployment.*
```bash
gcloud iam service-accounts add-iam-policy-binding \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:$GOOGLE_CLOUD_PROJECT.svc.id.goog[default/dagster]" \
  dagster@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com;

kubectl annotate serviceaccount \
  default \
  iam.gke.io/gcp-service-account=dagster@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com;

kubectl annotate serviceaccount \
  dagster \
  iam.gke.io/gcp-service-account=dagster@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com;
```
Create service account json in dbt directory:
```bash
gcloud iam service-accounts keys create dbt/service.json \
    --iam-account=dagster@$PROJECT_ID.iam.gserviceaccount.com
```

## Helm:
Add the official dagster helm repository ([Official Documentation](https://docs.dagster.io/deployment/guides/kubernetes/deploying-with-helm#step-5-add-the-dagster-helm-chart-repository)):
```bash
helm repo add dagster https://dagster-io.github.io/helm ;

helm repo update;
```
Submit the build and deploy using the upgrade command (from dagster directory):
```bash
gcloud builds submit \
    --tag us-central1-docker.pkg.dev/$GOOGLE_CLOUD_PROJECT/$INSTANCE_NAME/dagster .;
```
The file values.yaml should be modified to replace environment variables with their actual values before running the helm install command. Values.yaml can be updated from environment variables by exporting the variables:
```bash
set -a && source .env && set +a
```
Then using the envsubst command:
```bash
envsubst < values.yaml > new_values.yaml
```
Deploy with Helm using new_values.yaml: 
```bash
helm upgrade --install $INSTANCE_NAME $INSTANCE_NAME/dagster -f new_values.yaml
```
To access Dagster webserver/UI:
```bash
export  DAGSTER_WEBSERVER_POD_NAME=$(kubectl get pods --namespace default -l "app.kubernetes.io/name=dagster,app.kubernetes.io/instance=$INSTANCE_NAME,component=dagster-webserver" -o jsonpath="{.items[0].metadata.name}")
echo  "Visit <http://127.0.0.1:8080> to open the Dagster UI"
kubectl --namespace default port-forward $DAGSTER_WEBSERVER_POD_NAME  8080:80;
```

## Tableau:
Connect your Data source to view this dashboard.  
1. Add a new worksheet to the workbook.  
2. Add new Datasource. Connect to your Ed-fi rpt_student_attendance table.  
3. Replace the existing data source with your new datasource.

## Addt'l:
Upon initial deployment, after json files from the Ed-Fi API have been placed in buckets, you must remote into the user code pod and issue the following commands to create the externalized base tables in big query:
```bash
export DAGSTER_USER_CODE_POD_NAME=$(kubectl get pods --namespace default -l "app.kubernetes.io/name=dagster-user-deployments,app.kubernetes.io/instance=edfi-dagster,deployment=edfi-amt-user-code" -o jsonpath="{.items[0].metadata.name}");

kubectl exec -it $DAGSTER_USER_CODE_POD_NAME -- bash -c "cd /opt/dagster/app/dbt && dbt run-operation stage_external_sources"
```