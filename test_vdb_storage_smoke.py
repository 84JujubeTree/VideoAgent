import os
import sys
import asyncio
import tempfile

project_root = r"D:\VSCode Projects\VideoAgent-main"
sys.path.append(project_root)

from tools.videorag._storage.vdb_nanovectordb import NanoVectorDBVideoSegmentStorage


async def main():
    workdir = tempfile.mkdtemp(prefix="videagent_vdb_")

    storage = NanoVectorDBVideoSegmentStorage(
        namespace="test_segments",
        global_config={
            "working_dir": workdir,
            "video_embedding_batch_num": 2,
            "video_embedding_dim": 1024,
            "segment_retrieval_top_k": 2,
        },
        embedding_func=None,
    )

    cache_dir = os.path.join(workdir, "_cache", "demo_video")
    os.makedirs(cache_dir, exist_ok=True)

    # 这里只是给 mock embedding 用，文件存在即可，不需要真实视频内容
    open(os.path.join(cache_dir, "seg1.mp4"), "wb").close()
    open(os.path.join(cache_dir, "seg2.mp4"), "wb").close()

    await storage.upsert(
        video_name="demo_video",
        segment_index2name={0: "seg1", 1: "seg2"},
        video_output_format="mp4",
    )

    results = await storage.query("测试文本")
    print("query_results =", results)

    await storage.index_done_callback()


if __name__ == "__main__":
    asyncio.run(main())