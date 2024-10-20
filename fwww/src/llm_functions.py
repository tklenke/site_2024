import chromadb, ollama, openai
import threading, os, time, json, queue
from src.site_functions import get_process_info, update_process_status, update_process_info

#--------- CONSTANTs -------------
embedModel = "all-minilm"
KEY = os.environ.get("OPENAI_KEY")
MODEL = "gpt-4o-mini"
chromahost = "chroma-rag"
ollamahost = "http://ollama-rag:11434"
GET_GPT = False

MAX_DISTANCE = .45
MIN_DOCUMENTS = 5
MAX_DOCUMENTS = 20

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

def process_question(question):
    t0 = time.time()
    r = {}  #results
    #open required connections
    openaiclient = openai.OpenAI(api_key=KEY,)
    chromaclient = chromadb.HttpClient(host=chromahost)
    ollamaclient = ollama.Client(ollamahost)
    #get chromacollection
    collection = chromaclient.get_collection(embedModel) #, metadata={"hnsw:space": "cosine"}  )

    #embed the question
    queryembed = ollamaclient.embed(model=embedModel, input=question)['embeddings']
    #get related documents
    rQuery = collection.query(query_embeddings=queryembed, n_results=MAX_DOCUMENTS)
    #prune related documents
    nDocs = get_min_relevant_response(rQuery,MAX_DISTANCE,MIN_DOCUMENTS)
    #construct the prompt
    relateddocs = '\n\n'.join(rQuery['documents'][0][:nDocs])
    prompt = f"{initial_prompt} {question} {secondary_prompt} {relateddocs}"

    if GET_GPT:
        #ask the model
        completion = openaiclient.chat.completions.create(model=MODEL,messages=[{"role": "user", "content": prompt}])
        r['answer'] = completion.choices[0].message.content
        r['model'] = completion.model
        r['prompt tokens'] = completion.usage.prompt_tokens
        r['completion tokens'] = completion.usage.completion_tokens
    else:
        #Fake it
        r['answer'] = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum'
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
    return r

# ---- FILE PROCESSING THREAD
class FileProcessorThread(threading.Thread):
    instance = None

    def __init__(self, job_path, job_queue):
        if FileProcessorThread.instance:
            raise RuntimeError("Thread already running")
        else:
            print(f"File Processing Thread starting...")
        FileProcessorThread.instance = self
        threading.Thread.__init__(self)
        self.daemon = True
        self.job_path = job_path
        self.job_queue = job_queue
        super().__init__()
        self.start()  # Start the thread immediately

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
                result = process_question(data['query'])
                data["result"] = result
                #set status to completed
                data['status'] = 'complete'
                data['complete_time'] = time.time()
                update_process_info(data, filename=filename, directory=self.job_path)
                processedJobs.append(filename)
