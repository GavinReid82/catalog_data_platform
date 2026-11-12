"""The only module that imports sentence-transformers (it pulls in torch)."""
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # Task 0 may switch to the multilingual model
DIM = 384


class Embedder:
    dim = DIM

    def __init__(self, model_name: str = MODEL_NAME):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, batch_size=64, normalize_embeddings=True).tolist()
