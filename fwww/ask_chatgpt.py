import ollama, chromadb

from openai import OpenAI
import time, os
from src.chroma_functions import getclient, getcollection

#--------- CONSTANTs -------------
embedModel = "all-minilm"
KEY = os.environ.get("OPENAI_KEY")
MODEL = "gpt-4o-mini"

MAX_DISTANCE = .45
MIN_DOCUMENTS = 5
MAX_DOCUMENTS = int((8100 * .75)/ 75)
MAX_DOCUMENTS = 20

initial_prompt ="""You are an aerospace engineer specializing in amatuer-built aircraft. Don't restate this. If you don't know the answer, 
    just say that you don't know, don't try to make up an answer. """
initial_prompt = ""

secondary_prompt =""" Use the following pieces of context to answer the users question. -----"""
#secondary_prompt =""" Be concise, precise and accurate. 
#If the answer is not within the context provided says so.
#Use the following pieces of context to answer the users question. 
#-----"""

questions = [
    """How much angle should I have for the control stick to allow for sufficient clearance between 
    the stick and the fuselage side to get full aileron travel when your hand is on the stick""",
    "Give me a list of engine models that I should consider.  Include two sentences of pros and cons for each.",
    "Give me a list of considerations when installing the engine.",
    "Compare O-320 to O-360 engine for use in a Cozy",
    "What fuel injection system should I consider?",
    "How do I ensure the wing bolt bushings are installed correctly in the spar and match the wing",
    """I was going through light to moderate precipitation and started picking up a lot of static noise in 
    the headset. I am wondering if anyone has installed any static wicks or other mitigating procedures.""",
    """I replaced cylinder 3 on my Cozy last week with a brand new millennium Cylinder. 
    Before replacement, the old cylinder was my hottest. 
    50F hotter than the others. With the new cylinder it is now 80F hotter than the others.
    Is a 30F increase for a new cylinder typical?"""
]
questions = [
    """I have two static ports, one on each side of the fuselage. I have no space for an alternate 
    static valve. Should connect them together, one to each of the sensors, or just plug one and 
    pipe the other one to both?""",
]


#------------FUNCTIONS---------------
# find the index of the most irrelevant response within the defined thresholds
def get_min_relevant_response(results,fMaxDistance,nMinDocs):
    r = nMinDocs
    for i in range(nMinDocs,len(results['distances'][0])):
        if (results['distances'][0][i] < fMaxDistance):
            r = i
    return r
    
#-------------MAIN-------------------
stats = {}
print(f"Starting ModelTesting...")
# Replace with your own API key
client = OpenAI(
    # This is the default and can be omitted
    api_key=KEY,
)
chromaclient = getclient(host="host.docker.internal")
ollamaclient = ollama.Client("http://host.docker.internal:11434")

#embed
t0 = time.time()
#get chromacollection
collection = getcollection(chromaclient,embedModel) 

print(f" asking llm {MODEL}...")

print(f" asking questions...")
#ask the questions

for i in range(0,len(questions)):
    query = questions[i]

    print(f"  getting question {i} related docs...")
    queryembed = ollamaclient.embed(model=embedModel, input=query)['embeddings']
    rQuery = collection.query(query_embeddings=queryembed, n_results=MAX_DOCUMENTS)
    nDocs = get_min_relevant_response(rQuery,MAX_DISTANCE,MIN_DOCUMENTS)
    relateddocs = '\n\n'.join(rQuery['documents'][0][:nDocs])
    prompt = f"{initial_prompt} {query} {secondary_prompt} {relateddocs}"

    stats[str(i)+"related"] = rQuery
    stats[str(i)+"numdocs"] = nDocs

    t1 = time.time()
    # Make a request to the API
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    stats[str(i)+"time"] = time.time()-t1
    stats[str(i)+"answer"] = completion.choices[0].message.content
    stats[str(i)+"model"] = completion.model
    stats[str(i)+"prompt tokens"] = completion.usage.prompt_tokens
    stats[str(i)+"completion tokens"] = completion.usage.completion_tokens

print(f"\n------PROMPT------")
print(f"{initial_prompt} ..query.. {secondary_prompt}")

print(f"\n----QUESTIONS-----")
for i in range(0,len(questions)):
    distances = stats[str(i)+"related"]['distances'][0]
    numDocs = stats[str(i)+"numdocs"]
    distAvg = sum(distances[:numDocs]) / numDocs
    sources = stats[str(i)+"related"]['metadatas'][0]
    print(f"\n--- Question {i+1}: {questions[i]} ---")
    print(f"  Stats: \
          \n{'':>10}Docs: {numDocs} \
          \n{'':>10}Avg Distance: {distAvg:.2f}\n{'':>10}Max Distance: {distances[numDocs]:.2f}")
    print(f"\n--- ANSWER Question {i+1}  ---")
    print(f"  Stats: \
          \n{'':>10}{stats[str(i)+'time']:.1f} secs \
          \n{'':>10}Docs: {numDocs} \
          \n{'':>10}Avg Distance: {distAvg:.2f}\n{'':>10}Max Distance: {distances[numDocs]:.2f} \
          \n{'':>10}Model: {stats[str(i)+'model']}  \
          \n{'':>10}Tokens: In: {stats[str(i)+'prompt tokens']} Out: {stats[str(i)+'completion tokens']}  \
          ")

    print(stats[str(i)+"answer"])
# Print the response
#print(response.choices[0].text.strip())


    print(f"\n--- Sources Question {i+1} ---")
    for j in range(0,len(sources)):
        if j < numDocs:
            print(f"Score: {distances[j]:.3f} doc: {sources[j]['source']}")
        else:
            print(f"  Additional Source: {sources[j]['source']} Score: {distances[j]:.3f}")



            
    




