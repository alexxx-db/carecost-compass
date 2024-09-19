# Databricks notebook source
# MAGIC %md
# MAGIC #### Create catalog, schema and volumes

# COMMAND ----------

# MAGIC %run ./utils/init

# COMMAND ----------

spark.sql(f"CREATE CATALOG IF NOT EXISTS {catalog}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{sbc_folder}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{cpt_folder}")

# COMMAND ----------

# MAGIC %md
# MAGIC #### Copy Files to Volume
# MAGIC

# COMMAND ----------

#Let us first copy the SBC files 

for sbc_file in sbc_files:
  dbutils.fs.cp(f"file:/Workspace/{'/'.join(project_root_path)}/resources/{sbc_file}",sbc_folder_path,True)

# COMMAND ----------

#Now lets copy the cpt codes file
#Downloaded from https://www.cdc.gov/nhsn/xls/cpt-pcm-nhsn.xlsx

dbutils.fs.cp(f"file:/Workspace/{'/'.join(project_root_path)}/resources/{cpt_file}",cpt_folder_path,True)

# COMMAND ----------

# MAGIC %md
# MAGIC #### Create Data Tables
# MAGIC - Member Table: Contains member details including the client id
# MAGIC - Member Accumulator Table: Contain member year to date deductible accumulator
# MAGIC - Procedure Cost Table: Contain estimated cost of a procedure
# MAGIC
# MAGIC ######Payor name: LemonDrop
# MAGIC ######Client1 : SugarShack
# MAGIC ######Client2 : ChillyStreet 

# COMMAND ----------

import pandas as pd
from pyspark.sql.types import StructType, StructField, StringType, DateType, DoubleType, IntegerType, LongType
import datetime

# COMMAND ----------

# MAGIC %md
# MAGIC #####`member`

# COMMAND ----------

member_table_schema = StructType([
    StructField("member_id",StringType(), nullable=False),
    StructField("client_id",StringType(), nullable=False),   
    StructField("plan_id",StringType(), nullable=False),
    StructField("plan_start_date",DateType(), nullable=False),
    StructField("plan_end_date",DateType(), nullable=False),
    StructField("active_ind",StringType(), nullable=False),    
])

member_data = [
    ("1234","sugarshack","P1", datetime.date(2024,1,1), datetime.date(2024,12,31),"Y" ),
    ("2345","sugarshack","P1", datetime.date(2024,1,1), datetime.date(2024,12,31),"Y" ),
    ("7890","chillystreet","P2", datetime.date(2024,1,1), datetime.date(2024,12,31),"Y" ),
]

member = spark.createDataFrame(member_data, schema=member_table_schema)

spark.sql(f"DROP TABLE IF EXISTS {catalog}.{schema}.{member_table_name}")

spark.catalog.createTable(f"{catalog}.{schema}.{member_table_name}", schema=member_table_schema)

member.write.mode("append").saveAsTable(f"{catalog}.{schema}.{member_table_name}")

spark.sql(f"ALTER TABLE {catalog}.{schema}.{member_table_name} ADD CONSTRAINT {member_table_name}_pk PRIMARY KEY( member_id )")

# COMMAND ----------

display(spark.table(f"{catalog}.{schema}.{member_table_name}"))

# COMMAND ----------

# MAGIC %md
# MAGIC #####`member_accumulators`

# COMMAND ----------


member_accumulators_schema = StructType([
    StructField("member_id",StringType(), nullable=False),
    StructField("oop_max",DoubleType(), nullable=False),
    StructField("fam_deductible",DoubleType(), nullable=False),
    StructField("mem_deductible",DoubleType(), nullable=False),
    StructField("oop_agg",DoubleType(), nullable=False),
    StructField("mem_ded_agg",DoubleType(), nullable=False),
    StructField("fam_ded_agg",DoubleType(), nullable=False),
])

member_accumulators_data = [
    ('1234', 2500.00, 1500.00, 1000.00, 500.00, 500.00, 750.00),
    ('2345', 2500.00, 1500.00, 1000.00, 250.00, 250.00, 750.00),
    ('7890', 3000.00, 2500.00, 2000.00, 3000.00, 2000.00, 2000.00),
]

member_accumulators = spark.createDataFrame(member_accumulators_data, schema=member_accumulators_schema)

spark.sql(f"DROP TABLE IF EXISTS {catalog}.{schema}.{member_accumulators_table_name}")

spark.catalog.createTable(f"{catalog}.{schema}.{member_accumulators_table_name}", schema=member_accumulators_schema)

member_accumulators.write.mode("append").saveAsTable(f"{catalog}.{schema}.{member_accumulators_table_name}")

spark.sql(f"ALTER TABLE {catalog}.{schema}.{member_accumulators_table_name} ADD CONSTRAINT {member_accumulators_table_name}_pk PRIMARY KEY( member_id)")

# COMMAND ----------

display(spark.table(f"{catalog}.{schema}.{member_accumulators_table_name}"))

# COMMAND ----------

# MAGIC %md
# MAGIC #####`cpt_codes`
# MAGIC

# COMMAND ----------

from pyspark.sql.functions import monotonically_increasing_id

cpt_codes_file = f"{cpt_folder_path}/{cpt_file}"

cpt_codes_file_schema = (StructType()
    .add("code",StringType(),True)
    .add("description",StringType(),True)
)

cpt_codes_table_schema = (StructType()
    .add("id",LongType(),False)
    .add("code",StringType(),True)
    .add("description",StringType(),True)
)


cpt_df = (spark
          .read
          .option("header", "false")
          .option("delimiter", "\t")
          .schema(cpt_codes_file_schema)
          .csv(cpt_codes_file)
          .repartition(1)
          .withColumn("id",monotonically_increasing_id())
          .select("id","code","description")
)

spark.sql(f"DROP TABLE IF EXISTS {catalog}.{schema}.{cpt_code_table_name}")

spark.catalog.createTable(f"{catalog}.{schema}.{cpt_code_table_name}", schema=cpt_codes_table_schema)

cpt_df.write.mode("append").saveAsTable(f"{catalog}.{schema}.{cpt_code_table_name}")

spark.sql(f"ALTER TABLE {catalog}.{schema}.{cpt_code_table_name} ADD CONSTRAINT {cpt_code_table_name}_pk PRIMARY KEY( id )")

# COMMAND ----------

display(cpt_df)

# COMMAND ----------

# MAGIC %md
# MAGIC #####`procedure_cost` 

# COMMAND ----------

from pyspark.sql.functions import rand,round, pow, ceil,col

procedure_cost_schema = StructType([
    StructField("procedure_code",StringType(), nullable=False),
    StructField("cost",DoubleType(), nullable=False)
])

spark.sql(f"DROP TABLE IF EXISTS {catalog}.{schema}.{procedure_cost_table_name}")

spark.catalog.createTable(f"{catalog}.{schema}.{procedure_cost_table_name}", schema=procedure_cost_schema)

#Read the procedure codes and assign some cost to it
#In a production scenario it could be a complex procedure to calculate the expected cost
procedure_cost = (
    spark
    .table(f"{catalog}.{schema}.{cpt_code_table_name}")
    .withColumn("pow", ceil(rand(seed=1234) * 10) % 3 + 2 )
    .withColumn("cost", round(rand(seed=2345) *  pow(10, "pow") + 20 ,2)  )
    .select(col("code").alias("procedure_code"),"cost")
)

procedure_cost.write.mode("append").saveAsTable(f"{catalog}.{schema}.{procedure_cost_table_name}")

spark.sql(f"ALTER TABLE {catalog}.{schema}.{procedure_cost_table_name} ADD CONSTRAINT {procedure_cost_table_name}_pk PRIMARY KEY( procedure_code )")

display(spark.table(f"{catalog}.{schema}.{procedure_cost_table_name}"))

# COMMAND ----------


