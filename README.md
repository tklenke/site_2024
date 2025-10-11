# site_2024
Website 2024 revision.  Docker based.  Nginx, flask, docuwiki (2x) and supporting ollama, chromadb side project

### Maintenance
# Renew ssl certificate
  + keep nginx running as certbot will place a file and let nginx serve it to confirm ownership
  + run the docker command shown in docker-certbot.yaml
  + use sudo or sudo -s
  + if there is a new directory in the certbot/live directory e.g. m24tom.com-0001 then remove the
  old m24tom.com and move the -0001 to just m24tom.com
  + copy contents of current certbot/archive/m24tom.com[-nnnn] directory into the live/m24tom.com directory
  + ensure the symlinks for cert.pm and chain.pm point to the correct archive directory above
  + replace fullchain.pem and privkey.pm symlinks with the actual files fullchain1.pem and privkey1.pm
  copied over from the current archive 


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
- Embedder (text-embedding-3-large)
↓
- Context Assembler
↓
- GPT-4o-mini → fast first-pass answer
↓
- GPT-4o or GPT-5 → deeper-dive refinement

This two-stage pipeline delivers fast, affordable answers for common questions and higher-fidelity technical reasoning when required.

##  Model Recommendations

| Purpose | Model | Notes |
|----------|--------|-------|
| **Fast RAG draft** | `gpt-4o-mini` | Excellent cost/performance, strong contextual reasoning |
| **Deep refinement / fact check** | `gpt-4o` or `gpt-5` | More tokens, better factual grounding |
| **Embeddings** | `text-embedding-3-large` | Best for mixed technical + conversational data |

##  Chunking Strategy

| Parameter | Recommended Value | Rationale |
|------------|-------------------|------------|
| **Chunk size** | 200–250 tokens | Balances context coherence and retrieval precision |
| **Chunk overlap** | 20–40 tokens | Preserves boundary meaning |
| **Retrieved chunks per query** | 4–6 | Keeps context under ~1.5k tokens |
| **Embedding model** | `text-embedding-3-large` | Matches GPT-4o-mini semantics |

> 75-token chunks are too small — they fragment meaning and increase storage cost.

##  Prompt Length Guidelines

### GPT-4o-mini
- **Maximum context window:** 128,000 tokens  
- **Optimal total prompt length:** **2,000–6,000 tokens**
- Typical budget:
  - System instructions: ~500  
  - User query: ~200  
  - Retrieved context: 3,000–4,000  
  - Model output: ~500–800  

### Deeper-Dive Model (GPT-4o or GPT-5)
- **Recommended total prompt length:** **8,000–12,000 tokens**
- Include:
  - Original question  
  - Retrieved context (same or expanded)  
  - GPT-4o-mini draft answer  
  - Instruction to review, verify, and elaborate  

##  Deeper-Dive Prompt Template

**System Prompt Example:**
You are the refinement model.
Review the user's question, the retrieved context, and the draft response from GPT-4o-mini.
Your task is to verify factual accuracy, add missing technical detail, and correct any mistakes.
Cite or reference relevant context when useful.
If the draft is already correct, restate it concisely.


**Inputs:**
User question: ...
Retrieved context: ...
GPT-4o-mini draft: ...

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

- Use **GPT-4o-mini** for everyday RAG queries (2k–6k tokens).  
- Use **GPT-4o** or **GPT-5** for refinement (8k–12k tokens).  
- Chunk documents into **200–250 tokens** with **30-token overlap**.  
- Use **`text-embedding-3-large`** for embeddings.  
- Always pass the mini’s draft to the deeper model with clear “verify and expand” instructions.

##  Example Workflow

1. Retrieve top 5 chunks (≈1.5k tokens total).  
2. Assemble query + context → GPT-4o-mini prompt (~5k tokens).  
3. Generate draft response.  
4. Pass query + context + mini draft → GPT-4o or GPT-5 (~10k tokens).  
5. Output refined, verified answer.

##  Cost Optimization Tips

- **Mini-first architecture:** 80–90% of queries can stop at GPT-4o-mini.  
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
| GPT-4o-mini draft | 800 | Optional, for refinement step |
| Completion | 1,000 | Target output |
| **Total (deep dive)** | **~6,000–10,000** | Perfect balance of speed and detail |

---

**Author:** Experimental Aircraft Builders RAG Project  
**Purpose:** Accurate, efficient retrieval and summarization of aircraft builder knowledge.