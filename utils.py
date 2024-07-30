# Databricks notebook source
from databricks.vector_search.client import VectorSearchClient

def get_endpoint_state(endpoint_name):
    vsc = VectorSearchClient(disable_notice=True)
    try:
        endpoint_info = vsc.get_endpoint(endpoint_name)
        endpoint_state = endpoint_info['endpoint_status']['state']
        print(f"Endpoint {endpoint_name} is in {endpoint_state} status.")
        return endpoint_state
    except Exception as e:
        print(f"Endpoint {endpoint_name} does not exist")
        return "DOES_NOT_EXIST"



# COMMAND ----------

import time

def wait_for_endpoint_to_be_ready(endpoint_name):
    vsc = VectorSearchClient(disable_notice=True)
    
    for i in range(180):        
        endpoint_state = get_endpoint_state(endpoint_name)

        if endpoint_state == 'PROVISIONING':
            if i % 20 == 0: 
               print(f"Waiting for endpoint to create")
            time.sleep(10)
        elif endpoint_state == 'ONLINE':
            print(f"Endpoint {endpoint_name} created successfully")
            return True
        
        else:
            raise Exception(f"Error creating endpoint {vsc.get_endpoint(endpoint_name)}")

    raise Exception(f"Timeout, your index isn't ready yet: {vsc.get_endpoint(endpoint_name)}")

# COMMAND ----------

def create_endpoint(endpoint_name):
    vsc = VectorSearchClient(disable_notice=True)
    endpoint_state = get_endpoint_state(endpoint_name)
    
    if endpoint_state == "DOES_NOT_EXIST":
        print(f"Creating endpoint  {endpoint_name} ")
        vsc.create_endpoint(name=endpoint_name, endpoint_type="STANDARD")
        endpoint_state = get_endpoint_state(endpoint_name)
    
    if endpoint_state == "ONLINE":
        print(f"Endpoint {endpoint_name} is ready")
    elif endpoint_state == "PROVISIONING":
        wait_for_endpoint_to_be_ready(endpoint_name)
    else:
        raise Exception(f"Error creating endpoint {vsc.get_endpoint(endpoint_name)}")
    

# COMMAND ----------

def is_index_ready(endpoint_name,index_name):
    vsc = VectorSearchClient(disable_notice=True)
    try:
        index = vsc.get_index(endpoint_name=endpoint_name,index_name=index_name)
        index_info = index.describe()
        return index_info["status"]["ready"]
    except Exception as e:
        print(f"Error retrieving status of index {index_name} from endpoint {endpoint_name}")
        return False

# COMMAND ----------

def wait_for_index_to_be_ready(endpoint_name, index_name):
    vsc = VectorSearchClient(disable_notice=True)
    
    for i in range(180):        
        index_ready = is_index_ready(endpoint_name, index_name)
        if index_ready:
            print(f"Index {index_name} is ready")
            return True
        else:
            if i % 20 == 0: 
               print(f"Waiting for index to create")
            time.sleep(10)

    raise Exception(f"Timeout, your index isn't ready yet: {index_name}")

# COMMAND ----------

def create_delta_sync_vector_search_index(vector_search_endpoint_name, 
                 index_name, 
                 source_table_name, 
                 primary_key_column, 
                 embedding_source_column, 
                 embedding_endpoint_name,
                 update_mode):
    
    vsc = VectorSearchClient(disable_notice=True)
    
    index_ready = False
    index_exists = False
    try:
        index_info = vsc.get_index(endpoint_name=vector_search_endpoint_name,
                                   index_name=index_name)
        print(f"Index {index_name} already exists")
        index_exists = True
    except:
        print(f"Creating Index {index_name} ")

    if not index_exists:
        index = vsc.create_delta_sync_index(
            endpoint_name=vector_search_endpoint_name,
            source_table_name=source_table_name,
            index_name=index_name,
            pipeline_type=update_mode,
            primary_key=primary_key_column,
            embedding_source_column=embedding_source_column,
            embedding_model_endpoint_name=embedding_endpoint_name
        )

    wait_for_index_to_be_ready(vector_search_endpoint_name, index_name)

    return vsc.get_index(endpoint_name=vector_search_endpoint_name,index_name=index_name)

# COMMAND ----------

import mlflow 

def start_mlflow_experiment(experiment_name):
    user_email = dbutils.notebook.entry_point.getDbutils().notebook().getContext().userName().get()
    db_host = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().get()
    db_token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

    #Create an MLFlow experiment
    experiment_base_path = f"Users/{user_email}/mlflow_experiments"
    dbutils.fs.mkdirs(f"file:/Workspace/{experiment_base_path}")
    experiment_path = f"/{experiment_base_path}/{experiment_name}"

    # Manually create the experiment so that you can get the ID and can send it to the worker nodes for scaling
    experiment = mlflow.set_experiment(experiment_path)
    return experiment

# COMMAND ----------

from mlflow.tracking.client import MlflowClient

def get_latest_model_version(model_name: str, env_or_alias: str=""):  
    mlflow.set_registry_uri("databricks-uc")
    client = MlflowClient()

    if env_or_alias == "":
        models = client.search_model_versions(f"name='{model_name}'")
        if len(models) >0:
            return models[0]
        else:
            return None
    else:
        try:
            return client.get_model_version_by_alias(name=model_name,alias=env_or_alias)
        except:
            return None
