# Databricks notebook source
# MAGIC %run "./05 a Create All Tools and Model"

# COMMAND ----------

from langchain.agents import AgentExecutor, create_tool_calling_agent, create_react_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage, HumanMessage
from langchain import hub

os.environ['DATABRICKS_HOST'] = db_host_url
os.environ['DATABRICKS_TOKEN'] = db_token
os.environ["OPENAI_API_KEY"] = dbutils.secrets.get("srijit_nair","openai")


# COMMAND ----------

class CareCostReactAgent:
    
    max_tokens=2000
    temperature=0.01
    invalid_question_category = {
        "PROFANITY": "Content has inappropriate language",
        "RACIAL": "Content has racial slur.",
        "RUDE": "Content has angry tone and has unprofessional language.",
        "IRRELEVANT": "The question is not about a medical procedure cost.",
        "GOOD": "Content is a proper question about a cost of medical procedure."
    }
    

    agent_prompt = ChatPromptTemplate.from_messages(
    [
        ("system",
            "You are a helpful assistant who can answer questions about medical procedure costs.",
        ),
        ("placeholder", "{chat_history}"),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])

    def __init__(self, model_config:dict):
                                                        
        self.environment = model_config["environment"]
        self.default_parameter_json_string = model_config["default_parameter_json_string"]
        
        self.member_id_retriever_model_endpoint_name = model_config["member_id_retriever_model_endpoint_name"]
        self.agent_chat_model_endpoint_name = model_config["agent_chat_model_endpoint_name"]
        self.question_classifier_model_endpoint_name = model_config["question_classifier_model_endpoint_name"]
        self.benefit_retriever_model_endpoint_name = model_config["benefit_retriever_model_endpoint_name"]
        self.benefit_retriever_config = RetrieverConfig(**model_config["benefit_retriever_config"])
        self.procedure_code_retriever_config = RetrieverConfig(**model_config["procedure_code_retriever_config"])
        self.summarizer_model_endpoint_name = model_config["summarizer_model_endpoint_name"]
        self.member_table_name = model_config["member_table_name"]
        self.procedure_cost_table_name = model_config["procedure_cost_table_name"]
        self.member_accumulators_table_name = model_config["member_accumulators_table_name"]

        #Start instantiating tools       
        self.member_id_retriever = MemberIdRetriever(model_endpoint_name=self.member_id_retriever_model_endpoint_name)

        self.question_classifier = QuestionClassifier(model_endpoint_name=self.question_classifier_model_endpoint_name,
                                categories_and_description=self.invalid_question_category)
        
        self.client_id_lookup = ClientIdLookup(fq_member_table_name=self.member_table_name)
        
        self.benefit_rag = BenefitsRAG(model_endpoint_name=self.benefit_retriever_model_endpoint_name,
                                retriever_config=self.benefit_retriever_config)
        
        self.procedure_code_retriever = ProcedureRetriever(retriever_config=self.procedure_code_retriever_config)

        self.procedure_cost_lookup = ProcedureCostLookup(fq_procedure_cost_table_name=self.procedure_cost_table_name)

        self.member_accumulator_lookup = MemberAccumulatorsLookup(fq_member_accumulators_table_name=self.member_accumulators_table_name)

        self.member_cost_calculator = MemberCostCalculator()

        self.summarizer = ResponseSummarizer(model_endpoint_name=self.summarizer_model_endpoint_name)

        self.tools = [
            self.member_id_retriever,
            self.question_classifier,
            self.client_id_lookup,
            self.benefit_rag,
            self.procedure_code_retriever,
            self.procedure_cost_lookup,
            self.member_accumulator_lookup,
            self.member_cost_calculator,
            self.summarizer
        ]

        self.chat_model = ChatDatabricks(
            endpoint=self.agent_chat_model_endpoint_name
            
        )
        #self.chat_model = ChatOpenAI(model="gpt-3.5-turbo-0613")

        self.agent = create_tool_calling_agent(self.chat_model,
            self.tools,
            prompt = self.agent_prompt #PromptTemplate.from_template(self.agent_prompt)
        )
        
        self.agent_executor = AgentExecutor(agent=self.agent, 
                                            tools=self.tools,
                                            handle_parsing_errors=True,
                                            verbose=True,
                                            max_iterations=20)

    def answer(self, member_id:str ,input_question:str) -> str:
        return self.agent_executor.invoke({
            "input": f"My member_id is {member_id}, {input_question}"
        })




# COMMAND ----------

def get_model_config(environment:str,
                       catalog:str,
                       schema:str,
                       
                       member_table_name:str,
                       procedure_cost_table_name:str,
                       member_accumulators_table_name:str,
                       
                       vector_search_endpoint_name:str,
                       
                       sbc_details_table_name:str,
                       sbc_details_id_column:str,
                       sbc_details_retrieve_columns:[str],

                       cpt_code_table_name:str,
                       cpt_code_id_column:str,
                       cpt_code_retrieve_columns:[str],

                       agent_chat_model_endpoint_name:str,
                       member_id_retriever_model_endpoint_name:str,
                       question_classifier_model_endpoint_name:str,
                       benefit_retriever_model_endpoint_name:str,
                       summarizer_model_endpoint_name:str,

                       default_parameter_json_string:str) -> dict:
    
    fq_member_table_name = f"{catalog}.{schema}.{member_table_name}"
    fq_procedure_cost_table_name = f"{catalog}.{schema}.{procedure_cost_table_name}"
    fq_member_accumulators_table_name = f"{catalog}.{schema}.{member_accumulators_table_name}"      

    benefit_rag_retriever_config = RetrieverConfig(vector_search_endpoint_name=vector_search_endpoint_name,
                                vector_index_name=f"{catalog}.{schema}.{sbc_details_table_name}_index",
                                vector_index_id_column=sbc_details_id_column, 
                                retrieve_columns=sbc_details_retrieve_columns)

    proc_code_retriever_config = RetrieverConfig(vector_search_endpoint_name=vector_search_endpoint_name,
                                vector_index_name=f"{catalog}.{schema}.{cpt_code_table_name}_index",
                                vector_index_id_column=cpt_code_id_column,
                                retrieve_columns=cpt_code_retrieve_columns)

    return {
        "environment" : "dev",
        "default_parameter_json_string" : default_parameter_json_string, #'{"member_id":"1234"}',
        "question_classifier_model_endpoint_name":question_classifier_model_endpoint_name,
        "benefit_retriever_model_endpoint_name":benefit_retriever_model_endpoint_name,
        "benefit_retriever_config":benefit_rag_retriever_config.dict(),
        "procedure_code_retriever_config":proc_code_retriever_config.dict(),
        "member_table_name":fq_member_table_name,
        "procedure_cost_table_name":fq_procedure_cost_table_name,
        "member_accumulators_table_name":fq_member_accumulators_table_name,
        "member_id_retriever_model_endpoint_name" : member_id_retriever_model_endpoint_name,
        "agent_chat_model_endpoint_name" :agent_chat_model_endpoint_name,
        "summarizer_model_endpoint_name":summarizer_model_endpoint_name,
        "member_table_online_endpoint_name":f"{member_table_name}_endpoint".replace('_','-'),
        "procedure_cost_table_online_endpoint_name":f"{procedure_cost_table_name}_endpoint".replace('_','-'),
        "member_accumulators_table_online_endpoint_name":f"{member_accumulators_table_name}_endpoint".replace('_','-')

    }


# COMMAND ----------


care_cst_agent = CareCostReactAgent(model_config=get_model_config(
                                environment="dev",
                                catalog=catalog,
                                schema=schema,
                                
                                member_table_name= member_table_name,
                                procedure_cost_table_name=procedure_cost_table_name,
                                member_accumulators_table_name=member_accumulators_table_name,
                                
                                vector_search_endpoint_name = "care_cost_vs_endpoint",
                                
                                sbc_details_table_name=sbc_details_table_name,
                                sbc_details_id_column="id",
                                sbc_details_retrieve_columns=["id","content"],
                                
                                cpt_code_table_name=cpt_code_table_name,
                                cpt_code_id_column="id",
                                cpt_code_retrieve_columns=["code","description"],
                                
                                #agent_chat_model_endpoint_name="databricks-meta-llama-3-1-405b-instruct",
                                agent_chat_model_endpoint_name="srijit_nair_openai",
                                member_id_retriever_model_endpoint_name="databricks-mixtral-8x7b-instruct",
                                question_classifier_model_endpoint_name="databricks-meta-llama-3-1-70b-instruct",
                                benefit_retriever_model_endpoint_name= "databricks-meta-llama-3-1-70b-instruct",
                                summarizer_model_endpoint_name="databricks-dbrx-instruct",                       
                                
                                default_parameter_json_string='{"member_id":"1234"}'))

# COMMAND ----------

care_cst_agent.answer(member_id = "1234", input_question="What is the total cost of a shoulder MRI?")

# COMMAND ----------


