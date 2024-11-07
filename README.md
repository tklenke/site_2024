# site_2024
Website 2024 revision.  Docker based.  Nginx, flask, docuwiki (2x) and supporting ollama, chromadb side project

### Email to Cozy Builders
If you've used any of the Large Language Models (LLMs) like ChatGPT or Gemini for an endeavor where accuracy is mandatory (like writing computer programs) you will quickly realize even the best models are not 100% accurate.  And they can be very convincing in their mostly right answer. If 100% accuracy is required, you better do some significant verification of the answer.  

### Email to friends
I decided I wanted a better tool for searching the Cozy Builder's Newsgroup and Newsletters. It's obviously possible to use Google's interface to search the Newsgroup (it's hosted on GoogleGroups.)  Their search works, but it's really inefficient. On a search, Google returns a list of message threads showing their title and the first few lines of the first message.  Clicking on one of these, takes you to the thread, which again shows you the title, the responder and the first few lines of each response. Then you have to expand each message (or there is a link to expand all) and read the entire thread. It clearly works, but it would be nice to have a summary of the conversation, or even a direct answer if possible.

So I scraped all the messages (ssshhhh) and build a RAG solution.  I embedded the messages with my laptop after doing a bit of qualitative testing on different embedding models. I tried using local LLMs to answer the questions, but I found the ones I could run on my laptop (i7 with GPU) to be really lacking. JT suggested I look at using OpenAIs models and I found that their most recent low cost model to be not much money for a lot of tokens.  https://openai.com/index/gpt-4o-mini-advancing-cost-efficient-intelligence/ is $.15/1M input and $.60/1M output.  The results are far far better than the local LLMs and also far faster.

I built a simple website to use the system. It's running at AWS on a $12/month lightspeed instance (2 vCPUs, 2 gig RAM)  The time it takes to run is mostly due to the wait to embed the question (Ollama locally) and pull the related documents from the vector database (ChromaDB also locally.) I've tested it some but not a ton, so I'd be interested in your feedback. Obviously, you'll want to ask questions that are relevant. Here's a few suggestions from recent Cozy Builders Group threads.

1. For night flyers using landing lights: What lights do you use? How small are they? How many lumens? How satisfied are you with them?

2. I'm concerned about intermittent radio failures involving a Garmin 430, Narco MK 12E, and Flight Data Systems AP-60 audio mixer. Transmission issues included "unintelligible" communications and no response from ATC. Despite ground checks being successful, reception is often unclear in the air, and noise persists in the side tone after transmitting. Any advice on diagnosing these issues when they can't be reproduced on the ground?

3. Are there any plans or pre-made options available for making wheel pants, or at least dimensions (length and width) to help determine the foam size needed? Any guidance would be appreciated as I start this project.

4. I'm having an issue with my Lycoming O-360 A3A engine (Ellison TBI 4-5, Bendix left mag, Slick right mag) on a COZY MARK IV. At full power, the RPM oscillates between 2200-2400 instead of holding 2400 static RPM. The problem has worsened, grounding the plane since August. I've checked fuel filters, mags, compression, and intake valves, but the issue persists. Any advice, especially on the mechanical fuel pump or Ellison TBI, would be appreciated.

5. I have two static ports, one on each side of the fuse. I have no space for an alternate static valve. Should connect them together, one to each of the sensors, or just plug one and pipe the other one to both?

### Todo

+ Brainstorm List
+ use local llm to summarize and keyword generate for embedding
+ use local llm to generate keywords and product names, use for basic search
+ change to nomic embed, use prefix search_query: prior to asking for nearest docs
+ redo the embedding model test, using average score for a battery of questions to make determination

### Thoughts on Responses
+ Maybe ask for emphasis on including product names 
    + If asks for a list does not provide a list
    + Maybe special prompt for product suggestions
+ Do a GPT enabled review of CozyRAG vs responses from Group
+ Response to 2 seemed excellent. review against responses from group.
+