from pathlib import Path
from typing import Literal

from loguru import logger
from tqdm import tqdm
import os
from dotenv import load_dotenv

from providers.mock_asr_provider import MockASRProvider

PROMPT = {
    "zh": "人间灯火倒映湖中，她的渴望让静水泛起涟漪。若代价只是孤独，那就让这份愿望肆意流淌。",
    "en": "In the realm of advanced technology, the evolution of artificial intelligence stands as a monumental achievement.",
    "ja": "先進技術の領域において、人工知能の進化は画期的な成果として立っています。常に機械ができることの限界を押し広げているこのダイナミックな分野は、急速な成長と革新を見せています。複雑なデータパターンの解読から自動運転車の操縦まで、AIの応用は広範囲に及びます。",
}

ASRModelType = Literal["funasr", "whisper"]
load_dotenv()

def get_asr_provider(model_type: ASRModelType):
    provider_name = os.getenv("ASR_PROVIDER", "mock").lower()

    if provider_name == "bailian":
        from providers.bailian_asr_provider import BailianASRProvider
        return BailianASRProvider()

    return MockASRProvider()


def batch_transcribe(
    files: list[Path],
    model_size: str,
    model_type: ASRModelType,
    lang: str,
    pos: int,
    compute_type: str,
    batch_size: int = 1,
):
    results = {}

    if lang == "jp":
        lang = "ja"
        logger.info("Language jp is not supported directly, using ja instead")

    provider = get_asr_provider(model_type)

    logger.info(
        f"Using ASR provider for transcription, model_type={model_type}, lang={lang}"
    )

    for file in tqdm(files, position=pos):
        prompt = PROMPT.get(lang)
        result = provider.transcribe(file, lang=lang, prompt=prompt)
        results[str(file)] = result["text"]

    return results