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