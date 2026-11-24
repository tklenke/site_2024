# site_2024
Website 2024 revision.  Docker based.  Nginx, flask and supporting ollama, chromadb side project

### Maintenance
# Renew ssl certificate
  + keep nginx running as certbot will place a file and let nginx serve it to confirm ownership
  + from the site directory on the server: sudo ./sudo_renew_cert.sh
  + it asks certbot for m24tom.com and www.m24tom.com, checks the certificate, puts the files in
  server/certbot/conf/live/m24tom.com and restarts the containers
  + when certbot asks whether to expand the existing certificate, answer Expand

# Deploy a change of the code
  + run 2026-11-24 like this for the pictures of an answer (and 2026-11-22 for the answer display)
  + locally, with the tests passing: merge the branch into main and push it
```
cd ~/projects/site_2024
git checkout main
git merge --ff-only wip/annual-refresh
git push origin main
```
  + on the server, check first: no change but the untracked `server/old.nginx_all_apps.conf`, on
  main, and the commit that runs now (write it down: it is the one to go back to)
```
cd ~/site_2024
git status --short
git branch --show-current
git log --oneline -1
```
  + keep the running image for going back, tagged with that commit (here `775692d`)
```
docker tag site_2024-flask:latest site_2024-flask:775692d
docker images site_2024-flask
```
  + then the change; `up -d` makes the flask container new, and nginx is restarted after it because
  it looks up the name `flask` only when it starts
```
git pull
git log --oneline -1
docker compose build flask
docker compose up -d flask
docker compose restart nginx
docker compose ps
```
  + `ps` lists four containers, all up; in a browser ask a question, then check what the change is for
  + to go back, with the commit written down above
```
git checkout 775692d
docker tag site_2024-flask:775692d site_2024-flask:latest
docker compose up -d --force-recreate flask
docker compose restart nginx
```
  + once the site has run well for a few days: `docker image rm site_2024-flask:775692d`
  + after a reboot of the server everything comes back by itself (checked 2026-11-24)
  + the yearly update of the data (the collection, the pictures) is in the `ml` repository:
  its `README.md` lists the steps in order

# Run the tests
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
  + the tests that read the document collection need Chroma: docker compose up -d chroma-rag
  + the test of the page that waits for an answer needs node

# Make new tar file
tar -czf ../project.tar.gz -X exclude_from_tar.txt ~/project/site_2024


### Todo

+ Brainstorm List
+ use local llm to summarize and keyword generate for embedding (very slow)
+ use local llm to generate keywords and product names, use for basic search (retry maybe)
+ change to nomic embed, use prefix search_query: prior to asking for nearest docs (done)
+ redo the embedding model test, using average score for a battery of questions to make determination (done)

### Thoughts on Responses
+ Maybe ask for emphasis on including product names 
    + If asks for a list does not provide a list
    + Maybe special prompt for product suggestions
+ Do a GPT enabled review of CozyRAG vs responses from Group
+ Response to 2 seemed excellent. review against responses from group.
+
### Rev 2 Update thoughts on RAG strategy

# Experimental Aircraft Builders RAG Guide

A practical guide for building a retrieval-augmented generation (RAG) system for experimental aircraft builders — such as Cozy and Super Cub communities — using OpenAI models.

##  Architecture Overview

- Retriever (Chroma / OpenAI File Search)
↓
- Embedder (nomic-embed-text)
↓
- Context Assembler
↓
- gpt-6-luna → fast first-pass answer
↓
- gpt-6.2-sol → deeper-dive refinement

This two-stage pipeline delivers fast, affordable answers for common questions and higher-fidelity technical reasoning when required.

##  Model Recommendations

| Purpose | Model | Notes |
|----------|--------|-------|
| **First answer** | `gpt-6-luna` | Chosen in the evaluation of 2026-11-22; set in `fwww/site.ini` (`LLM_DRAFT`) |
| **Dig deeper and follow-up** | `gpt-6.2-sol` | Set in `fwww/site.ini` (`LLM_REVISE`) |
| **Embeddings** | `nomic-embed-text` | Run by Ollama; set in `fwww/site.ini` (`EMBED`) |

##  Chunking Strategy

| Parameter | Recommended Value | Rationale |
|------------|-------------------|------------|
| **Chunk size** | 200–250 tokens | Balances context coherence and retrieval precision |
| **Chunk overlap** | 20–40 tokens | Preserves boundary meaning |
| **Retrieved chunks per query** | 4–6 | Keeps context under ~1.5k tokens |
| **Embedding model** | `nomic-embed-text` | Run by Ollama, with task prefixes |

> 75-token chunks are too small — they fragment meaning and increase storage cost.

##  Prompt Length Guidelines

### gpt-6-luna
- **Optimal total prompt length:** **2,000–6,000 tokens**
- Typical budget:
  - System instructions: ~500  
  - User query: ~200  
  - Retrieved context: 3,000–4,000  
  - Model output: ~500–800  

### Deeper-Dive Model (gpt-6.2-sol)
- **Recommended total prompt length:** **8,000–12,000 tokens**
- Include:
  - Original question  
  - Retrieved context (same or expanded)  
  - gpt-6-luna draft answer  
  - Instruction to review, verify, and elaborate  

##  Deeper-Dive Prompt Template

**System Prompt Example:**
You are the refinement model.
Review the user's question, the retrieved context, and the draft response from gpt-6-luna.
Your task is to verify factual accuracy, add missing technical detail, and correct any mistakes.
Cite or reference relevant context when useful.
If the draft is already correct, restate it concisely.


**Inputs:**
User question: ...
Retrieved context: ...
gpt-6-luna draft: ...

markdown
Copy code

##  Performance Profile

| Prompt Size | Speed | Quality | Ideal Usage |
|--------------|--------|----------|--------------|
| < 2k |  Very fast | High | Quick Q&A |
| 2k–6k |  Fast |  Excellent | Main RAG queries |
| 6k–12k |  Moderate | Very high | Deep analysis |
| >15k |  Slower | Gradual decline | Large document synthesis |

##  Summary

- Use **gpt-6-luna** for everyday RAG queries (2k–6k tokens).  
- Use **gpt-6.2-sol** for refinement (8k–12k tokens).  
- Chunk documents into **200–250 tokens** with **30-token overlap**.  
- Use **`nomic-embed-text`** for embeddings.  
- Always pass the mini’s draft to the deeper model with clear “verify and expand” instructions.

##  Example Workflow

1. Retrieve top 5 chunks (≈1.5k tokens total).  
2. Assemble query + context → gpt-6-luna prompt (~5k tokens).  
3. Generate draft response.  
4. Pass query + context + mini draft → gpt-6.2-sol (~10k tokens).  
5. Output refined, verified answer.

##  Cost Optimization Tips

- **Mini-first architecture:** 80–90% of queries can stop at gpt-6-luna.  
- **Cache retrievals:** Reuse recent embedding hits to save compute.  
- **Truncate redundant context:** Aim for <4k tokens retrieved per query.  
- **Batch embeddings:** Use 1 API call per file for efficiency.  
- **Evaluate accuracy tiers:** Run deeper model only when confidence < threshold.

##  Example Token Budget

| Component | Tokens | Notes |
|------------|--------|-------|
| System prompt | 400 | Instructions and tone |
| User query | 200 | Builder question |
| Retrieved context | 3,500 | ~5 chunks × 700 tokens |
| gpt-6-luna draft | 800 | Optional, for refinement step |
| Completion | 1,000 | Target output |
| **Total (deep dive)** | **~6,000–10,000** | Perfect balance of speed and detail |

---

**Author:** Experimental Aircraft Builders RAG Project  
**Purpose:** Accurate, efficient retrieval and summarization of aircraft builder knowledge.