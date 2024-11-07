FROM ollama/ollama
# Install required dependencies
RUN echo "getting embed models"
# Install the models
# Install embed models (note will install in a new image basically)
RUN nohup bash -c "ollama serve &" \
   && sleep 2 \
   && ollama pull nomic-embed-text
