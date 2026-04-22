import os
import json
from pathlib import Path

from pydantic import BaseModel, Field
from pydub import AudioSegment
from dotenv import load_dotenv
from environment.config.llm import deepseek

from environment.agents.base import BaseTool
from providers.mock_tts_provider import MockTTSProvider

load_dotenv()


class StandUpSynth(BaseTool):
    """
    Application scenario: Stand-up Comedy Creating
    Segment-by-segment stand-up comedy audio synthesis with final merge
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
        script: str = Field(..., description="String of segmented stand-up comedy script")
        target_vocal_dir: str = Field(..., description="The target vocal directory for stand-up comedy synthesis.")
        reaction_dir: str = Field(..., description="The audience reaction directory for stand-up comedy synthesis.")

    class OutputSchema(BaseModel):
        audio_path: str = Field(..., description="File path to the merged stand-up comedy audio")
        seg_dir: str = Field(..., description="Directory containing all segmented stand-up comedy audio files")
        metadata_path: str = Field(..., description="File path to the metadata of the stand-up comedy script")

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
        output_file_path = os.path.join(parent_dir, "final", "stand_up.wav")
        merged_audio.export(output_file_path, format="wav")
        abs_output_file_path = os.path.abspath(output_file_path)
        print(f"Combined audio saved to {abs_output_file_path}")

        return abs_output_file_path

    def _parse_line_with_llm(self, line):
        user_prompt = f"""
        Analyze the tone, text content, and atmosphere marker of the following stand-up comedy segment:
        {line}

        Output strictly in JSON format with these rules:
        1. "tone" field must be ONLY "Natural", "Empathetic", "Confused" or "Exclamatory"
        2. "text" field contains the segment's content
        3. Add "reaction" field ONLY if there's atmosphere marker (i.e. [Laughter] or [Cheers]) behind the sentence, value must be "Laughter" or "Cheers"
        4. You should not analyze the tone and atmosphere markers of the segment yourself, but instead strictly rely on whether these markers appear in the segment.
        5. NO extra characters or explanations before/after JSON

        Ensure the output is strictly in JSON format!
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

            clean_text = line.split("：", 1)[-1].split(":", 1)[-1].strip()

            result = {
                "tone": "Natural",
                "text": clean_text
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
        target_vocal_dir = os.path.abspath(params.target_vocal_dir)
        reaction_dir = os.path.abspath(params.reaction_dir)

        cnt = 0
        results = []
        first_line = True
        seg_dir = os.path.join(os.path.dirname(target_vocal_dir), "seg")
        os.makedirs(seg_dir, exist_ok=True)

        for line in script.split("\n"):
            if not line.strip():
                continue
            if first_line:
                first_line = False
                continue

            try:
                clean_text = line.split("：", 1)[-1].split(":", 1)[-1].strip()

                result = self._parse_line_with_llm(line)
                print(cnt, ":", result)

                tone = result["tone"].lower()
                text = result["text"].strip()

                if "[Laughter]" in line:
                    result["reaction"] = "Laughter"
                elif "[Cheers]" in line:
                    result["reaction"] = "Cheers"

                print(cnt, ":", result)

                tone = result["tone"].lower()
                text = result["text"].strip()

                segment_output_path = os.path.join(seg_dir, f"{cnt}.wav")
                voice_prompt_path = os.path.join(target_vocal_dir, f"{tone}.wav")

                self.tts_provider.synthesize(
                    text=text,
                    output_path=Path(segment_output_path),
                    voice_prompt_path=voice_prompt_path,
                )

                if "reaction" in result:
                    reaction = result["reaction"].lower()
                    reaction_path = os.path.join(reaction_dir, f"{reaction}.wav")

                    try:
                        original_audio = AudioSegment.from_file(os.path.join(seg_dir, f"{cnt}.wav"))
                        reaction_audio = AudioSegment.from_file(reaction_path)

                        combined_audio = original_audio + reaction_audio
                        combined_audio.export(os.path.join(seg_dir, f"{cnt}.wav"), format="wav")
                        print(f"Successfully combined reaction audio for line {cnt}.")
                    except Exception as e:
                        print(f"Error combining reaction audio for line {cnt}: {str(e)}")

                results.append(result)
                cnt += 1
            except Exception as e:
                print(f"Error processing line: {line}. Error: {str(e)}")
                continue

        synth_audio_path = self.merge_audio_files(seg_dir, cnt)
        print(f"Final combined audio saved at: {synth_audio_path}")

        metadata_path = os.path.join(os.path.dirname(target_vocal_dir), "stand-up.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        return {
            "audio_path": synth_audio_path,
            "seg_dir": seg_dir,
            "metadata_path": metadata_path
        }