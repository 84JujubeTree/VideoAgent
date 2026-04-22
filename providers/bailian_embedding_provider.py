import os
from http import HTTPStatus

import dashscope
from dotenv import load_dotenv

load_dotenv()


class BailianEmbeddingProvider:
    def __init__(self):
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        if not self.api_key:
            raise ValueError("DASHSCOPE_API_KEY is not set in .env")

    def embed_text(self, text: str) -> dict:
        resp = dashscope.TextEmbedding.call(
            api_key=self.api_key,
            model="text-embedding-v4",
            input=text,
            dimension=1024,
        )

        output = getattr(resp, "output", None)
        print("=== embedding response ===")
        print("status_code:", getattr(resp, "status_code", None))
        print("code:", getattr(resp, "code", None))
        print("message:", getattr(resp, "message", None))
        if output and "embeddings" in output:
            emb = output["embeddings"][0]["embedding"]
            print("embedding_dim:", len(emb))
        else:
            print("output:", output)

        if getattr(resp, "status_code", None) != HTTPStatus.OK:
            raise RuntimeError(
                f"Embedding call failed: "
                f"status_code={getattr(resp, 'status_code', None)}, "
                f"code={getattr(resp, 'code', None)}, "
                f"message={getattr(resp, 'message', None)}"
            )

        if not getattr(resp, "output", None):
            raise RuntimeError(
                f"Embedding call returned no output: "
                f"status_code={getattr(resp, 'status_code', None)}, "
                f"code={getattr(resp, 'code', None)}, "
                f"message={getattr(resp, 'message', None)}"
            )

        return {"embedding": resp.output["embeddings"][0]["embedding"]}

    def embed_video(self, video_path: str) -> dict:
        # 你现在先用路径字符串代替真实视频 embedding，只为了验证链路
        return self.embed_text(video_path)