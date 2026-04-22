from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed_text(self, text: str) -> dict:
        ...

    def embed_image(self, image_path: str) -> dict:
        ...

    def embed_video(self, video_path_or_url: str) -> dict:
        ...