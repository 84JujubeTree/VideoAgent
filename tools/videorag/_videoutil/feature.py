import os
from dotenv import load_dotenv

from providers.mock_embedding_provider import MockEmbeddingProvider

load_dotenv()


def get_embedding_provider():
    provider_name = os.getenv("EMBEDDING_PROVIDER", "mock").lower()

    if provider_name == "bailian":
        from providers.bailian_embedding_provider import BailianEmbeddingProvider
        return BailianEmbeddingProvider()

    return MockEmbeddingProvider()


def encode_video_segments(video_paths, embedder=None):
    """
    Encode a list of video paths into embeddings.
    keep `embedder` arg only for compatibility with old callers.
    """
    provider = get_embedding_provider()
    embeddings = []

    for video_path in video_paths:
        result = provider.embed_video(str(video_path))
        embeddings.append(result["embedding"])

    return embeddings


def encode_string_query(query: str, embedder=None):
    """
    Encode a text query into an embedding.
    keep `embedder` arg only for compatibility with old callers.
    """
    provider = get_embedding_provider()
    result = provider.embed_text(query)
    return [result["embedding"]]