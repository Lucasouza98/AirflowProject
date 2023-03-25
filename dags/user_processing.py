from airflow import DAG
#It's good to see this page for create operators: https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/operators.html
from airflow.providers.postgres.operators.postgres import PostgresOperator #operator for handle postres
from airflow.providers.http.sensors.http import HttpSensor #check available
from airflow.providers.http.operators.http import SimpleHttpOperator #request for api (get, post)
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

import json
from datetime import datetime
from pandas import json_normalize

def _process_user(ti):
    user = ti.xcom_pull(task_ids="extract_user")
    user = user['results'][0]
    processed_user = json_normalize({
        'firstname': user['name']['first'],
        'lastname': user['name']['last'],
        'country': user['location']['country'],
        'username': user['login']['username'],
        'password': user['login']['password'],
        'email': user['email'] })
    processed_user.to_csv('/tmp/processed_user.csv', index=None, header=False)

def _store_user():
    hook = PostgresHook(postgres_conn_id='postgres')
    hook.copy_expert(
        sql="COPY users FROM stdin WITH DELIMITER as ','",
        filename='/tmp/processed_user.csv'
    )

with DAG('user_processing',
        start_date=datetime(2023,3,25),
        schedule_interval='@daily',
        catchup=False) as dag:
    
    create_table = PostgresOperator(
        task_id="create_table",
        postgres_conn_id="postgres",
        sql='''
            CREATE TABLE IF NOT EXISTS users (
            firstname TEXT NOT NULL,
            lastname TEXT NOT NULL,
            country TEXT NOT NULL,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            email TEXT NOT NULL
            );
        '''
    )

    #This task is responsible for check if api exists, case not exist return false and stop dag.
    is_availabe = HttpSensor(
        task_id='is_available',
        http_conn_id = "user_api", #this config is the same create in airflow UI in Admin/connection
        endpoint='api/',
    )

    extract_user = SimpleHttpOperator(
        task_id='extract_user',
        http_conn_id='user_api',
        endpoint='api/',
        method='GET',
        response_filter=lambda response: json.loads(response.text),
        log_response=True #log for store status connection
    )

    process_user = PythonOperator(
        task_id='process_user',
        python_callable=_process_user
    )

    store_user = PythonOperator(
        task_id='store_user',
        python_callable=_store_user
    )

    create_table >> is_availabe >> extract_user >> process_user >> store_user