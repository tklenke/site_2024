# ABOUTME: Tests that the PREFIX setting is put in front of the question when it is embedded.
# ABOUTME: The embedding call is recorded; the query runs on the real collection.


def test_prefix_is_put_before_the_question(processor, collection):
    lstEmbeddings = collection.get(limit=1, include=["embeddings"])["embeddings"]
    lstInputs = []

    class Embedder:
        def embed(self, model, input):
            lstInputs.append(input)
            return {"embeddings": lstEmbeddings}

    processor.ollamaclient = Embedder()
    processor.embed_model = "nomic-embed-text"
    processor.max_documents = 3
    processor.set_embed_prefix("search_query:")

    dctResult = processor.get_query_results("how many seats")

    assert lstInputs == ["search_query:how many seats"]
    assert len(dctResult["ids"][0]) == 3
