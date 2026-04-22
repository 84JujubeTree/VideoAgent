class MockEmbeddingProvider:
    def _fake_vector(self, seed: str, dim: int = 8) -> list[float]:
        base = sum(ord(c) for c in seed) % 100
        return [float((base + i) % 10) for i in range(dim)]

    def embed_text(self, text: str) -> dict:
        return {"embedding": self._fake_vector(text)}

    def embed_video(self, video_path_or_url: str) -> dict:
        return {"embedding": self._fake_vector(video_path_or_url)}