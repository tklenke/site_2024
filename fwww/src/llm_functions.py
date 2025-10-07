import chromadb, ollama, openai
import threading, os, time, json, queue
from src.site_functions import get_process_info, update_process_status, update_process_info, dedupe_list_of_docs

#--------- CONSTANTs -------------

lorem_ipsum_string = """\n**Lorem ipsum dolor sit amet**, *consectetur adipiscing elit*, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.  \nUt enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.\n\n> *"Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur."*\n\n- Excepteur sint occaecat cupidatat non proident,\n- Sunt in culpa qui officia deserunt mollit anim id est laborum."""

initial_prompt ="""You are an aerospace engineer specializing in amatuer-built aircraft. Don't restate this. If you don't know the answer, 
    just say that you don't know, don't try to make up an answer. """
initial_prompt = ""

secondary_prompt =""" Use the following pieces of context to answer the users question. -----"""
secondary_prompt =""" Be concise, precise and accurate. If the answer is not within the context provided 
say so. Use the following pieces of context to answer the users question. ----- """
secondary_prompt =""" Use the following pieces of context to answer the users question. ----- """


#------------FUNCTIONS---------------
# find the index of the most irrelevant response within the defined thresholds
def get_min_relevant_response(results,fMaxDistance,nMinDocs):
    r = nMinDocs
    for i in range(nMinDocs,len(results['distances'][0])):
        if (results['distances'][0][i] < fMaxDistance):
            r = i
    return r

# ---- FILE PROCESSING THREAD
class FileProcessorThread(threading.Thread):
    instance = None

    def __init__(self, job_path, job_queue, use_gpt, openai_key, chromahost, ollamahost):
        if FileProcessorThread.instance:
            raise RuntimeError("Thread already running")
        else:
            print(f"File Processing Thread starting...")
        FileProcessorThread.instance = self
        threading.Thread.__init__(self)
        self.daemon = True
        self.job_path = job_path
        self.job_queue = job_queue
        self.use_gpt = use_gpt
        
        #open required connections
        print(f"ch:{chromahost} oh:{ollamahost}")
        self.openaiclient = openai.OpenAI(api_key=openai_key,)
        self.chromaclient = chromadb.HttpClient(host=chromahost)
        self.ollamaclient = ollama.Client(ollamahost)

        print(f"chroma collections:{self.chromaclient.list_collections()}")

        self.set_models()
        self.set_docs_params()
        self.set_prompts()
        super().__init__()
        self.start()  # Start the thread immediately

    def set_models(self, embed="nomic-embed-text", llm="gpt-4o-mini"):
        self.embed_model = embed
        self.llm_model = llm
        return
    
    def set_docs_params(self, max_distance=.45, min_documents=5, max_documents=20):
        self.max_distance = max_distance
        self.min_documents = min_documents
        self.max_documents = max_documents
        return
    
    def set_prompts(self, prefix="", initial_prompt="", secondary_prompt=" Use the following pieces of context to answer the users question. ----- "):
        self.embed_prefix = prefix
        self.initial_prompt = initial_prompt
        self.secondary_prompt = secondary_prompt
        return

    def process_question(self, question):
        t0 = time.time()
        r = {}  #results

        #get chromacollection
        collection = self.chromaclient.get_collection(name=self.embed_model) #, metadata={"hnsw:space": "cosine"}  )
        #embed the question
        queryembed = self.ollamaclient.embed(model=self.embed_model, input=self.embed_prefix + question)['embeddings']
        #get related documents
        rQuery = collection.query(query_embeddings=queryembed, n_results=self.max_documents)
        #prune related documents
        nDocs = get_min_relevant_response(rQuery,self.max_distance,self.min_documents)
        #construct the prompt
        relateddocs = '\n\n'.join(rQuery['documents'][0][:nDocs])
        prompt = f"{initial_prompt} {question} {secondary_prompt} {relateddocs}"

        if self.use_gpt:
            #ask the model
            completion = self.openaiclient.chat.completions.create(model=self.llm_model,messages=[{"role": "user", "content": prompt}])
            r['answer'] = completion.choices[0].message.content
            r['model'] = completion.model
            r['prompt tokens'] = completion.usage.prompt_tokens
            r['completion tokens'] = completion.usage.completion_tokens
        else:
            #Fake it
            r['answer'] = lorem_ipsum_string
            r['model'] = 'Did not evaluate at GPT'
            r['prompt tokens'] = len(question.split())
            r['completion tokens'] = len(r['answer'].split())

        #capture and return the results
        r['time'] = time.time()-t0

        r['number provided docs'] = nDocs
        distAvg = sum(rQuery['distances'][0][:nDocs]) / nDocs
        r['average score'] = f"{(1. - distAvg):.2f}"
        r['provided_docs'] = []
        r['related_docs'] = []
        for i, id in enumerate(rQuery['ids'][0]):
            dDoc = {}
            dDoc['id'] = id
            dDoc['score'] = f"{(1.0 - rQuery['distances'][0][i]):.2f}"
            dDoc['source'] = rQuery['metadatas'][0][i]['source']
            if i < nDocs:
                r['provided_docs'].append(dDoc)
            else:
                r['related_docs'].append(dDoc)
        r['provided_docs'] = dedupe_list_of_docs(r['provided_docs'])
        r['related_docs'] = dedupe_list_of_docs(r['related_docs'])
        return r

    def run(self):
        processedJobs = []
        while True:
            item = self.job_queue.get()
            print(f'Working on {item}')
            self.job_queue.task_done()
            for filename in os.listdir(self.job_path):
                if filename in processedJobs:
                    continue
                data = get_process_info(filename=filename,directory=self.job_path)
                if data['status'] != "new":
                    processedJobs.append(filename)
                    continue
                #set status to started
                data = update_process_status("start",filename=filename,directory=self.job_path)
                # Validate required keys and handle missing ones gracefully
                if "query" not in data or data.get("query") is None:
                    print(f"{filename}: Missing 'query' key or null value in JSON data.")
                    update_process_status("error",filename=filename, directory=self.job_path)
                    continue
                #run
                result = self.process_question(data['query'])
                data["result"] = result
                #set status to completed
                data['status'] = 'complete'
                data['complete_time'] = time.time()
                data['elapsed'] = data['complete_time'] - data['created']
                update_process_info(data, filename=filename, directory=self.job_path)
                processedJobs.append(filename)

if __name__ == "__main__":
    import time, os, json, queue, configparser
    INI_PATH = './site.ini'

    ### Load MiFrame Configuration
    if not os.path.exists(INI_PATH):
        print(f"Can't find config file {INI_PATH}")
        exit()
    cfg = configparser.ConfigParser()
    cfg.read(INI_PATH)

    FPQueue = queue.Queue()
    FPThread = FileProcessorThread(cfg.get('PATHS','JOBS_DiR'), FPQueue, cfg.getboolean('RAG','USE_GPT'), \
                                cfg.get('KEYS','OPENAI'), "localhost", "http://localhost:11434")
    FPThread.set_models(cfg.get('MODELS','EMBED'), cfg.get('MODELS','LLM'))
    FPThread.set_prompts(cfg.get('PROMPTS','PREFIX'), cfg.get('PROMPTS','INITIAL'), cfg.get('PROMPTS','SECONDARY'))
    FPThread.set_docs_params(cfg.getfloat('RAG','MAX_DISTANCE'), cfg.getint('RAG','MIN_DOCUMENTS'), cfg.getint('RAG','MAX_DOCUMENTS'))
    print(f"asking question")
    r = FPThread.process_question("how many seats does the cozy have")

    print(r)