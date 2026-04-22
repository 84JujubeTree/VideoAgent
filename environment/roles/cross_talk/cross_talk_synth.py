import os
import json
from pathlib import Path

from pydantic import BaseModel, Field
from pydub import AudioSegment
from dotenv import load_dotenv

from environment.agents.base import BaseTool
from environment.config.llm import deepseek
from providers.mock_tts_provider import MockTTSProvider

load_dotenv()


class CrossTalkSynth(BaseTool):
    """
    Application scenario: Cross Talk Creating
    Segment-by-segment cross talk audio synthesis with final merge
    """

    def __init__(self):
        super().__init__()
        self.tts_provider = self._get_tts_provider()

    def _get_tts_provider(self):
        provider_name = os.getenv("TTS_PROVIDER", "mock").lower()

        if provider_name == "bailian":
            from providers.bailian_tts_provider import BailianTTSProvider
            return BailianTTSProvider()

        return MockTTSProvider()

    class InputSchema(BaseTool.BaseInputSchema):
        script: str = Field(..., description="String of segmented cross talk script")
        dou_gen_dir: str = Field(..., description="The 逗哏 tone directory for cross talk synthesis.")
        peng_gen_dir: str = Field(..., description="The 捧哏 tone directory for cross talk synthesis.")

    class OutputSchema(BaseModel):
        audio_path: str = Field(..., description="File path to the synthesized cross talk audio")
        seg_dir: str = Field(..., description="Directory containing all segmented cross talk audio files")
        metadata_path: str = Field(..., description="File path to the metadata of the cross talk script")

    def merge_audio_files(self, seg_dir, cnt):
        merged_audio = AudioSegment.silent(duration=0)

        for i in range(cnt):
            audio_file_path = os.path.join(seg_dir, f"{i}.wav")
            try:
                audio_segment = AudioSegment.from_file(audio_file_path)
                merged_audio += audio_segment
                print(f"Successfully added {audio_file_path} to the combined audio.")
            except Exception as e:
                print(f"Error loading {audio_file_path}: {str(e)}")

        parent_dir = os.path.dirname(seg_dir)
        os.makedirs(os.path.join(parent_dir, "final"), exist_ok=True)
        output_file_path = os.path.join(parent_dir, "final", "cross_talk.wav")
        merged_audio.export(output_file_path, format="wav")
        abs_output_file_path = os.path.abspath(output_file_path)
        print(f"Combined audio saved to {abs_output_file_path}")

        return abs_output_file_path

    def _parse_line_with_llm(self, line, dou_gen_name, peng_gen_name):
        user_prompt = f"""
        Analyze the following crosstalk dialogue line for performer role, tone, text content and audience reaction:
        {line}

        Output JSON format with STRICT rules:
        1. "role" field must be either {dou_gen_name} or {peng_gen_name}
        2. "tone" field must be "Natural", "Emphatic" or "Confused"
        3. "text" field contains the dialogue content
        4. Add "reaction" field ONLY if [Laughter] or [Cheers] exists (value must be "Laughter" or "Cheers")
        5. No extra characters before/after JSON

        Output ONLY the JSON object!
        """

        try:
            response = deepseek(user=user_prompt)
            res = response.choices[0].message.content

            if res.startswith("```json"):
                res = res[len("```json"):]
            elif res.startswith("```"):
                res = res[len("```"):]
            if res.endswith("```"):
                res = res[:-3]
            res = res.strip()

            result = json.loads(res)
            return result
        except Exception as e:
            print(f"deepseek failed, fallback parsing used. Error: {e}")

            # fallback 规则：根据说话人前缀猜 role，tone 固定 natural
            if "：" in line:
                speaker, content = line.split("：", 1)
            elif ":" in line:
                speaker, content = line.split(":", 1)
            else:
                speaker, content = "", line

            speaker = speaker.strip().lower()
            content = content.strip()

            if dou_gen_name.lower() in speaker:
                role = dou_gen_name
            else:
                role = peng_gen_name

            result = {
                "role": role,
                "tone": "Natural",
                "text": content,
            }

            if "[Laughter]" in line:
                result["reaction"] = "Laughter"
            elif "[Cheers]" in line:
                result["reaction"] = "Cheers"

            return result


    def execute(self, **kwargs):
        params = self.InputSchema(**kwargs)
        print("Parameters validated successfully")


        script = params.script
        dou_gen_dir = os.path.abspath(params.dou_gen_dir)
        peng_gen_dir = os.path.abspath(params.peng_gen_dir)
        data_dir = os.path.dirname(peng_gen_dir)
        dou_gen_name = os.path.basename(dou_gen_dir)
        peng_gen_name = os.path.basename(peng_gen_dir)

        results = []
        cnt = 0
        first_line = True
        seg_dir = os.path.join(os.path.dirname(dou_gen_dir), "seg")
        os.makedirs(seg_dir, exist_ok=True)

        for line in script.split("\n"):
            if not line.strip():
                continue

            if first_line:
                first_line = False
                continue

            user_prompt = f"""
            Analyze the following crosstalk dialogue line for performer role, tone, text content and audience reaction:
            {line}

            Output JSON format with STRICT rules:
            1. "role" field must be either {dou_gen_name} or {peng_gen_name}
            2. "tone" field must be "Natural", "Emphatic" or "Confused"
            3. "text" field contains the dialogue content
            4. Add "reaction" field ONLY if [Laughter] or [Cheers] exists
            5. No extra characters before/after JSON

            Output ONLY the JSON object!
            """

            try:

                result = self._parse_line_with_llm(line, dou_gen_name, peng_gen_name)
                print(cnt, ":", result)

                role = result["role"]
                tone = result["tone"].strip().lower()
                text = result["text"].strip()

                segment_output_path = os.path.join(seg_dir, f"{cnt}.wav")
                voice_prompt_path = os.path.join(data_dir, role, f"{tone}.wav")

                self.tts_provider.synthesize(
                    text=text,
                    output_path=Path(segment_output_path),
                    voice_prompt_path=voice_prompt_path,
                )

                results.append(result)
                cnt += 1
            except Exception as e:
                print(f"Error processing line: {line}. Error: {str(e)}")
                continue

        synth_audio_path = self.merge_audio_files(seg_dir, cnt)
        print(f"Final combined audio saved at: {synth_audio_path}")

        metadata_path = os.path.join(data_dir, "cross-talk.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        return {
            "audio_path": synth_audio_path,
            "seg_dir": seg_dir,
            "metadata_path": metadata_path,
        }