import chromadb, ollama, openai
import threading, os, time, json, queue, traceback
from src.error_reasons import get_error_reason
from src.site_functions import get_process_info, update_process_status, update_process_info

#--------- CONSTANTs -------------

lorem_ipsum_string = """\n**Lorem ipsum dolor sit amet**, *consectetur adipiscing elit*, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.  \nUt enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.\n\n> *"Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur."*\n\n- Excepteur sint occaecat cupidatat non proident,\n- Sunt in culpa qui officia deserunt mollit anim id est laborum."""

initial_prompt ="""You are an aerospace engineer specializing in amatuer-built aircraft. Don't restate this. If you don't know the answer, 
    just say that you don't know, don't try to make up an answer. """
initial_prompt = ""

secondary_prompt =""" Use the following pieces of context to answer the users question. -----"""
secondary_prompt =""" Be concise, precise and accurate. If the answer is not within the context provided 
say so. Use the following pieces of context to answer the users question. ----- """
secondary_instruction = """ Use the following pieces of context to answer the users question about a Cozy amatuer-build aircraft. """
context_separator = """----- """
secondary_prompt = secondary_instruction + context_separator

revise_prompt="""You are the refinement model.
Review the user's question about a Cozy amatuer-build aircraft, the draft response and the retrieved context.
Your task is to verify factual accuracy, add missing technical detail, and correct any mistakes.
Cite or reference relevant context when useful.
If the draft is already correct, restate it concisely.
"""

followup_prompt="""You are the refinement model.
Review the user's follow up question, the draft response, the previous context provided 
for the draft response, and the additional content based on the followup question.
Your task is to answer the follow up question to the draft response using the additional content
and previous content as context.
"""

#added to the instruction of each prompt when its pieces of context are numbered
citation_instruction = ("Each piece of context starts with its number in square brackets. After a statement "
                        "that you take from the context, write the number of the piece it comes from in square "
                        "brackets, like this: [3]. For more than one piece write [2][5]. Use only the numbers "
                        "given. Do not write a list of sources at the end.")

#stands in for the additional content of a follow-up that has none
no_additional_content="None. Every document retrieved for the follow up question is in the previous content."

#------------FUNCTIONS---------------
# find the number of responses within the defined thresholds
def get_num_draft_docs(results, fMaxDistance, nMinDocs, nMaxDraftDocs):
    distances = results['distances'][0]

    # 2. Determine the upper bound for slicing. 
    n_limit = min(len(distances), nMaxDraftDocs)
    
    try:
        # Look for the last index where the condition is met.
        for i in reversed(range(nMinDocs, n_limit)):
            if distances[i] < fMaxDistance:
                return i + 1
        
        # If no result satisfies the condition, return the starting point
        return nMinDocs
        
    except IndexError:
        # Handle case where results['distances'][0] is empty or too short 
        # (though n_limit and nMinDocs should prevent this if the inputs are valid)
        return nMinDocs

def get_prior_doc_ids_from_data(data):
    r = data['result']
    doc_lists = [r.get('provided_docs', [])]
    #a follow-up gets only the documents the prior answer was given
    if data['type'] != "followup":
        doc_lists.append(r.get('related_docs', []))
    
    # Use a nested list comprehension to iterate over all documents 
    # in the available lists and extract their 'id'.
    ids = [d['id'] for doc_list in doc_lists for d in doc_list]
    #dict.fromkeys() dedupes the list of ids and keeps their order
    return list(dict.fromkeys(ids))

def get_docs_in_order(collection, ids):
    """
    Gets documents by their ids. The collection returns them in an order of its own.

    :param collection: The document collection.
    :param ids: The ids, without duplicates.
    :return: A dictionary containing 'ids', 'documents' and 'metadatas', each in the order of
             the given ids. Ids that are not in the collection are left out.
    """
    rDocs = collection.get(ids=ids)
    positions = {doc_id: i for i, doc_id in enumerate(rDocs['ids'])}
    order = [positions[doc_id] for doc_id in ids if doc_id in positions]
    return {key: [rDocs[key][i] for i in order] for key in ('ids', 'documents', 'metadatas')}

def number_docs(docs, nFirst=1):
    """The document texts, each starting with its number in square brackets."""
    return [f"[{n}] {text}" for n, text in enumerate(docs, nFirst)]

def build_prompt(data, docs, additional_docs=(), numbered=False):
    """
    Builds the prompt for a job.

    :param data: The job data, with the 'type' and 'query' and, for a revision or a follow-up, the prior 'result'.
    :param docs: The document texts for a new question, or those of the prior answer.
    :param additional_docs: The document texts retrieved for a follow-up question.
    :param numbered: Whether the documents are numbered and the model is asked to cite them by number.
                     The additional documents count on from the last of docs.
    :return: The prompt string.
    """
    secondary = secondary_prompt
    revise = revise_prompt
    followup = followup_prompt
    if numbered:
        additional_docs = number_docs(additional_docs, len(docs) + 1)
        docs = number_docs(docs)
        secondary = f"{secondary_instruction}{citation_instruction} {context_separator}"
        revise = f"{revise_prompt}{citation_instruction}\n"
        followup = f"{followup_prompt}{citation_instruction}\n"
    doctext = '\n\n'.join(docs)
    if data['type'] == "new":
        prompt = f"{initial_prompt} {data['query']} {secondary} {doctext}"
    elif data['type'] == "followup":
        additionaldocs = '\n\n'.join(additional_docs) or no_additional_content
        prompt = f"""{followup} USER QUESTION: {data['query']}
                        DRAFT RESPONSE: {data['result']['answer']} PREVIOUS CONTENT: {doctext}
                        ADDITIONAL_CONTENT: {additionaldocs}"""
    else: #revise
        prompt = f"""{revise} USER QUESTION {data['query']} 
                            DRAFT RESPONSE: {data['result']['answer']} 
                            RETRIEVED CONTENT: {doctext}"""
    return prompt

def get_doc_list_from_result(rQuery, nDocsFrom=None, nDocsTo=None):
    """
    Transforms parallel query results (ids, distances, metadata) into a 
    list of document dictionaries, applying a slice filter.

    :param rQuery: A dictionary containing 'ids', 'distances', and 'metadatas'.
    :param nDocsFrom: The starting index (inclusive, defaults to 0).
    :param nDocsTo: The ending index (exclusive, defaults to end of list).
    :return: A list of document dictionaries.
    """
    # 1. Use Python slicing to get the relevant range from the three lists.
    # Slicing handles the nDocsFrom=None and nDocsTo=None cases automatically.
    # 2. Use a list comprehension with zip() to efficiently build the final list.

    if 'distances' in rQuery:
        ids = rQuery['ids'][0]
        sliced_ids = ids[nDocsFrom:nDocsTo]
        metadatas = rQuery['metadatas'][0]
        sliced_metadatas = metadatas[nDocsFrom:nDocsTo]
        distances = rQuery['distances'][0]
        sliced_distances = distances[nDocsFrom:nDocsTo]
        r = [
            {
                'id': doc_id,
                # Calculate the score and format it to two decimal places
                'score': f"{(1.0 - distance):.2f}", 
                'source': metadata.get('source', None) # Use .get() for safety
            }
            # zip() iterates over the three sliced lists in parallel
            for doc_id, distance, metadata in zip(sliced_ids, sliced_distances, sliced_metadatas)
        ]
    else:
        ids = rQuery['ids']
        sliced_ids = ids[nDocsFrom:nDocsTo]
        metadatas = rQuery['metadatas']
        sliced_metadatas = metadatas[nDocsFrom:nDocsTo]
        r = [
            {
                'id': doc_id,
                'source': metadata.get('source', None) # Use .get() for safety
            }
            # zip() iterates over the three sliced lists in parallel
            for doc_id, metadata in zip(sliced_ids, sliced_metadatas)
        ]        

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
        self.openaiclient = openai.OpenAI(api_key=openai_key,)
        self.chromaclient = chromadb.HttpClient(host=chromahost)
        self.ollamaclient = ollama.Client(ollamahost)

        self.set_models()
        self.set_docs_params()
        self.set_embed_prefix()
        self.set_doc_numbering()
        super().__init__()
        self.start()  # Start the thread immediately

    def set_models(self, embed="nomic-embed-text", llm_draft="gpt-4o-mini", llm_revise="gpt-4.1"):
        self.embed_model = embed
        self.collection = self.chromaclient.get_collection(name=self.embed_model) 
        self.llm_draft_model = llm_draft
        self.llm_revise_model = llm_revise
        return
    
    def set_docs_params(self, max_distance=.45, min_documents=5, max_documents=30, max_draft_documents=15):
        self.max_distance = max_distance
        self.min_documents = min_documents
        self.max_documents = max_documents
        self.max_draft_documents = max_draft_documents
        return
    
    def set_embed_prefix(self, prefix=""):
        self.embed_prefix = prefix
        return

    def set_doc_numbering(self, numbered=False):
        self.numbered = numbered
        return
    
    def get_query_results(self, question):
        #embed the question
        queryembed = self.ollamaclient.embed(model=self.embed_model, input=self.embed_prefix + question)['embeddings']
        #get related documents
        rQuery = self.collection.query(query_embeddings=queryembed, n_results=self.max_documents)
        return rQuery

    def process_question(self, data):
        t0 = time.time()
        r = {}  #results

        if data['type'] == "new":
            rQuery = self.get_query_results(data['query'])
            #prune related documents
            nDocs = get_num_draft_docs(rQuery,self.max_distance,self.min_documents,self.max_draft_documents)
            #construct the prompt
            prompt = build_prompt(data, rQuery['documents'][0][:nDocs], numbered=self.numbered)
            modelName = self.llm_draft_model
        else:
            ids_for_fetch = get_prior_doc_ids_from_data(data)
            rPriorDocs = get_docs_in_order(self.collection, ids_for_fetch)
            modelName = self.llm_revise_model
            additionalDocs = ()
            if data['type'] == "followup":
                rQuery = self.get_query_results(data['query'])
                nDocs = get_num_draft_docs(rQuery,self.max_distance,self.min_documents,self.max_draft_documents)
                #a document of the previous content is not sent again
                additionalDocs = [text for doc_id, text in zip(rQuery['ids'][0][:nDocs], rQuery['documents'][0])
                                  if doc_id not in rPriorDocs['ids']]
            prompt = build_prompt(data, rPriorDocs['documents'], additionalDocs, numbered=self.numbered)
 
    # Optional: specify what data to include (ids are always included)
    #include=["metadatas", "documents"] )
        if self.use_gpt:
            #ask the model
            completion = self.openaiclient.chat.completions.create(model=modelName,messages=[{"role": "user", "content": prompt}])
            r['answer'] = completion.choices[0].message.content
            r['model'] = completion.model
            r['prompt tokens'] = completion.usage.prompt_tokens
            r['completion tokens'] = completion.usage.completion_tokens
        else:
            #Fake it
            r['answer'] = lorem_ipsum_string
            r['model'] = 'Did not evaluate at GPT'
            r['prompt tokens'] = len(data['query'].split())
            r['completion tokens'] = len(r['answer'].split())

        #capture and return the results
        r['time'] = time.time()-t0
        r['type'] = data['type']
        #whether the chunks were numbered in the prompt, so that the numbers in the answer name them
        r['numbered_docs'] = self.numbered

        if data['type'] == "new":
            r['number provided docs'] = nDocs
            distAvg = sum(rQuery['distances'][0][:nDocs]) / nDocs
            r['average score'] = f"{(1. - distAvg):.2f}"
            r['provided_docs'] = get_doc_list_from_result(rQuery, nDocsFrom=None, nDocsTo=nDocs)
            r['related_docs'] = get_doc_list_from_result(rQuery, nDocsFrom=nDocs, nDocsTo=None)
        else:
            r['provided_docs'] = get_doc_list_from_result(rPriorDocs)
            if data['type'] == "followup":
                r['provided_docs'] += [doc for doc in get_doc_list_from_result(rQuery, nDocsTo=nDocs)
                                       if doc['id'] not in rPriorDocs['ids']]
        return r

    def process_job(self, filename):
        data = get_process_info(filename=filename,directory=self.job_path)
        if data['status'] not in ("new","revise","followup"):
            return
        #set status to started
        qType = data['status']
        data = update_process_status("start",filename=filename,directory=self.job_path)
        #put new, revised or followup into data
        data['type'] = qType
        # Validate required keys and handle missing ones gracefully
        if "query" not in data or data.get("query") is None:
            print(f"{filename}: Missing 'query' key or null value in JSON data.")
            update_process_status("error",filename=filename, directory=self.job_path)
            return
        #run
        result = self.process_question(data)
        data["result"] = result
        #set status to completed
        data['status'] = 'complete'
        data['complete_time'] = time.time()
        data['elapsed'] = data['complete_time'] - data['created']
        update_process_info(data, filename=filename, directory=self.job_path)

    # called while the exception is being handled
    def mark_job_failed(self, filename, exception):
        print(f"{filename}: Job failed.\n{traceback.format_exc()}")
        try:
            update_process_status("error",filename=filename,directory=self.job_path,
                                  error_reason=get_error_reason(exception))
        except Exception as e:
            print(f"{filename}: Could not set the status to error. {e!r}")

    def run(self):
        processedJobs = []
        while True:
            item = self.job_queue.get()
            print(f'Working on {item}')
            self.job_queue.task_done()
            for filename in os.listdir(self.job_path):
                if filename in processedJobs:
                    continue
                try:
                    self.process_job(filename)
                except Exception as e:
                    #one job must not end the thread
                    self.mark_job_failed(filename, e)
                #a failed job is never tried again, as that could pay again
                processedJobs.append(filename)
