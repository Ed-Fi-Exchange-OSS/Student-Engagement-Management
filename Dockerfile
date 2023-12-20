FROM python:3.9-slim

ENV DAGSTER_VERSION="1.5.11"
ENV DAGSTER_MODULE_VERSION="0.21.11"
ENV DBT_VERSION="1.7.3"

ENV DBT_PROFILES_DIR=/opt/dagster/app/dbt
ENV DBT_PROJECT_DIR=/opt/dagster/app/dbt
ENV DAGSTER_HOME=/opt/dagster/dagster_home
ENV PYTHONPATH=/opt/dagster/app/edfi

RUN pip install --upgrade pip

RUN \
    pip install \
        dagster==${DAGSTER_VERSION} \
        dbt-core==${DBT_VERSION} \
        dagster-postgres==${DAGSTER_MODULE_VERSION} \
        dagster-celery[flower,redis,kubernetes] \
        dagster-dbt==${DAGSTER_MODULE_VERSION} \
        dagster-gcp==${DAGSTER_MODULE_VERSION} \
        dagster-k8s==${DAGSTER_MODULE_VERSION} \
        dagster-celery-k8s==${DAGSTER_MODULE_VERSION} \
        dbt-bigquery \
        tenacity \
# Cleanup
    &&  rm -rf /var \
    &&  rm -rf /root/.cache  \
    &&  rm -rf /usr/lib/python2.7 \
    &&  rm -rf /usr/lib/x86_64-linux-gnu/guile

RUN mkdir -p /opt/dagster/dagster_home /opt/dagster/app /opt/dagster/app/dbt /opt/dagster/app/dbt/target
WORKDIR /opt/dagster/app

COPY dbt /opt/dagster/app/dbt
COPY edfi /opt/dagster/app/edfi
COPY dbt/dbt_project.yml /opt/dagster/app/dbt/dbt_project.yml
COPY dbt/manifest.json /opt/dagster/app/dbt/target/manifest.json

RUN cd /opt/dagster/app/dbt && dbt deps