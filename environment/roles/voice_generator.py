import os
# import torch
# import torchaudio
import json
import re

import traceback
from pydantic import BaseModel, Field
from environment.agents.base import BaseTool

from pathlib import Path
from dotenv import load_dotenv

from providers.mock_tts_provider import MockTTSProvider

import wave

class VoiceGenerator(BaseTool):
    """
    Agent processes scene content, generates speech audio, and provides timestamp information for video editing.
    The VoiceGenerator focuses on generating speech based on scene content (e.g., descriptions, narration, or supplemental audio) rather than modifying the original video's dialogue and synthesizing replacements for a revised script.
    It is commonly used for voice synthesis in Commentary, News, and Rhythm-based content.
    """

    def __init__(self):
        super().__init__()
        # Navigate to the project root directory (three levels up from current file)
        self.project_root = os.getcwd()
        
        # Set up paths
        # self.model_path = os.path.join(self.project_root, 'tools', 'CosyVoice', 'pretrained_models', 'CosyVoice2-0.5B')
        self.video_edit_dir = os.path.join(self.project_root, 'dataset', 'video_edit')
        self.scene_output_dir = os.path.join(self.video_edit_dir, 'scene_output')
        self.audio_analysis_dir = os.path.join(self.video_edit_dir, 'audio_analysis')
        self.storyboard_file = os.path.join(self.scene_output_dir, "video_scene.json")
        self.audio_path = os.path.join(self.audio_analysis_dir, "gen_audio.wav")

        os.makedirs(self.video_edit_dir, exist_ok=True)
        os.makedirs(self.scene_output_dir, exist_ok=True)
        os.makedirs(self.audio_analysis_dir, exist_ok=True)
        
        load_dotenv()
        self.tts_provider = self._get_tts_provider()
    
    def _get_tts_provider(self):
        provider_name = os.getenv("TTS_PROVIDER", "mock").lower()

        if provider_name == "bailian":
            from providers.bailian_tts_provider import BailianTTSProvider
            return BailianTTSProvider()

        return MockTTSProvider()

    class InputSchema(BaseTool.BaseInputSchema):
        video_scene_path: str = Field(
            ...,
            description="Path to a custom scene JSON file"
        )
        target_vocal_path: str = Field(
            ...,
            description="Path to the target timbre for voice generation"
        )

    class OutputSchema(BaseModel):
        audio_path: str = Field(
            ...,
            description="Path to the synthesized audio"
        )
        timestamp_path: str = Field(
            ...,
            description="Path to video frame timestamp"
        )


    def _process_with_timestamps(self, json_file_path):
        """Process JSON file and extract segments with proper support for Chinese content"""
        # Read the JSON file
        with open(json_file_path, 'r', encoding='utf-8') as file:  # Ensure UTF-8 encoding
            json_data = json.load(file)
        
        # Get the raw content - check both possible field names
        raw_content = None
        if "content_created" in json_data:
            raw_content = json_data["content_created"]
            print("Using 'content_created' field from JSON")
        else:
            print("Error: 'content_created' field not found in JSON file")
            return []
        
        # Normalize line endings
        raw_content = raw_content.replace('\r\n', '\n')
        
        # Check for the exact delimiter pattern from your example
        if '/////\n' in raw_content:
            segments = raw_content.split('/////\n')
            print("Using exact '/////\n' delimiter pattern")
        else:
            # Fallback to more generic regex pattern
            segments = re.split(r'/+\s*\n', raw_content)
            print("Using regex pattern for delimiter detection")
        
        # Filter out empty segments and strip whitespace
        segments = [seg.strip() for seg in segments if seg.strip()]
        
        # Create a list to store both full content and individual segments
        segment_list = []
        for i, segment in enumerate(segments):
            segment_list.append({
                "segment_id": i+1,
                "content": segment
            })
        
        # Create a new object with the full content and segments
        clean_json = {
            "user_idea": json_data.get("user_idea", ""),
            "segments": segment_list
        }
        
        # Save to a new file with UTF-8 encoding
        output_path = json_file_path.replace(".json", "_clean.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(clean_json, f, indent=2, ensure_ascii=False)  # ensure_ascii=False to preserve Chinese characters
        
        print(f"Original content had {len(segments)} segments separated by delimiters")
        print(f"Clean content saved to {output_path}")
        
        return segment_list

    def _split_into_sentences(self, text, max_length=200):
        """Split text into manageable chunks for TTS processing with Chinese support"""
        # Chinese sentences typically use different punctuation
        for punct in ['。', '！', '？', '；', '. ', '! ', '? ', '; ']:
            text = text.replace(punct, punct + '|')
        
        sentences = text.split('|')
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # Further split long sentences
        result = []
        for sentence in sentences:
            if len(sentence) <= max_length:
                result.append(sentence)
            else:
                # Split by commas and Chinese commas if sentence is too long
                comma_parts = sentence.replace('，', ',').split(',')
                current_part = ""
                
                for part in comma_parts:
                    if len(current_part) + len(part) <= max_length:
                        if current_part:
                            current_part += "," + part
                        else:
                            current_part = part
                    else:
                        if current_part:
                            result.append(current_part)
                        current_part = part
                
                if current_part:
                    result.append(current_part)
        
        return result

    def _generate_audio_for_segments(self, segments, output_dir, max_sentence_length, voice_prompt_path=None):
        """Generate audio for each segment via provider and track timestamps"""
        if output_dir is None:
            output_dir = self.audio_analysis_dir

        os.makedirs(output_dir, exist_ok=True)

        timestamp_data = {
            "sentence_data": {
                "count": len(segments),
                "chunks": []
            }
        }

        current_time = 0.0
        segment_files = []

        for segment in segments:
            segment_id = segment["segment_id"]
            segment_text = segment["content"].strip()

            if not segment_text:
                continue

            segment_output_file = Path(output_dir) / f"segment_{segment_id}.wav"

            print(f"\nProcessing Segment {segment_id}:")
            text_preview = segment_text[:50] + "..." if len(segment_text) > 50 else segment_text
            print(f"Text preview: {text_preview}")

            try:
                result = self.tts_provider.synthesize(
                    text=segment_text,
                    output_path=segment_output_file,
                    voice_prompt_path=voice_prompt_path,
                )

                duration = float(result.get("duration", 1.0))
                current_time += duration

                timestamp_data["sentence_data"]["chunks"].append({
                    "id": segment_id,
                    "timestamp": round(current_time, 3),
                    "content": segment_text
                })

                segment_files.append(str(segment_output_file))
                print(f"Successfully processed segment {segment_id} (duration: {duration:.2f}s)")

            except Exception as e:
                print(f"Error processing segment {segment_id}: {str(e)}")

        return timestamp_data, segment_files, segment_files, current_time

    # 轻薄本跑不动什么troch，该用wave测试
    def _combine_audio_files(self, segment_audio_files, timestamp_data,
                        output_file, segment_files, keep_segment_files):
        """
        Combine all segment wav files into one output wav
        """
        if not segment_audio_files:
            print("No audio segments to combine")
            return None, None

        output_dir = os.path.dirname(output_file)
        os.makedirs(output_dir, exist_ok=True)

        frames_list = []
        params = None

        for wav_path in segment_audio_files:
            with wave.open(wav_path, 'rb') as wf:
                current_params = (
                    wf.getnchannels(),
                    wf.getsampwidth(),
                    wf.getframerate(),
                )

                if params is None:
                    params = current_params
                else:
                    if current_params != params:
                        raise ValueError(f"WAV format mismatch: {wav_path}")

                frames_list.append(wf.readframes(wf.getnframes()))

        if params is None:
            return None, None

        nchannels, sampwidth, framerate = params

        with wave.open(output_file, 'wb') as wf:
            wf.setnchannels(nchannels)
            wf.setsampwidth(sampwidth)
            wf.setframerate(framerate)
            for frames in frames_list:
                wf.writeframes(frames)

        print(f"Combined audio saved to: {output_file}")

        timestamp_json_file = os.path.join(output_dir, "cut_points.json")
        with open(timestamp_json_file, 'w', encoding='utf-8') as f:
            json.dump(timestamp_data, f, indent=2, ensure_ascii=False)
        print(f"Timestamp data saved to: {timestamp_json_file}")

        if not keep_segment_files and segment_files:
            print("Cleaning up temporary files...")
            for file_path in segment_files:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as e:
                    print(f"Warning: Could not remove {file_path}: {str(e)}")

        return output_file, timestamp_json_file


    # 带GPU版本，下了torch和torchaudio
    # def _combine_audio_files(self, segment_audio_files, timestamp_data,
    #                         output_file, segment_files, keep_segment_files):
    #     """
    #     Combine all segment wav files into one output wav
    #     """
    #     if not segment_audio_files:
    #         print("No audio segments to combine")
    #         return None, None

    #     output_dir = os.path.dirname(output_file)
    #     os.makedirs(output_dir, exist_ok=True)

    #     combined = None
    #     sample_rate = None

    #     for wav_path in segment_audio_files:
    #         waveform, sr = torchaudio.load(wav_path)
    #         if combined is None:
    #             combined = waveform
    #             sample_rate = sr
    #         else:
    #             if sr != sample_rate:
    #                 raise ValueError(f"Sample rate mismatch: {wav_path}")
    #             combined = torch.cat([combined, waveform], dim=1)

    #     torchaudio.save(output_file, combined, sample_rate)
    #     print(f"Combined audio saved to: {output_file}")

    #     timestamp_json_file = os.path.join(output_dir, "cut_points.json")
    #     with open(timestamp_json_file, 'w', encoding='utf-8') as f:
    #         json.dump(timestamp_data, f, indent=2, ensure_ascii=False)
    #     print(f"Timestamp data saved to: {timestamp_json_file}")

    #     if not keep_segment_files and segment_files:
    #         print("Cleaning up temporary files...")
    #         for file_path in segment_files:
    #             try:
    #                 if os.path.exists(file_path):
    #                     os.remove(file_path)
    #             except Exception as e:
    #                 print(f"Warning: Could not remove {file_path}: {str(e)}")

    #     return output_file, timestamp_json_file

    
    def _initialize_model(self, prompt_speech_path):
        """Initialize TTS provider"""
        if prompt_speech_path and not os.path.exists(prompt_speech_path):
            print(f"Warning: Prompt speech file not found at {prompt_speech_path}")
        return True

    def execute(self, **kwargs):
        """Execute the voice generation process"""
        # Validate input parameters
        params = self.InputSchema(**kwargs)
        
        # Set default paths if not provided
        scene_file = params.video_scene_path
        prompt_speech_file = params.target_vocal_path
        output_file = self.audio_path
        
        try:
            print("\n=== GENERATING VOICE ===")
            
            # Initialize the model
            if not self._initialize_model(prompt_speech_file):
                return
            
            # Check if scene file exists
            if not os.path.exists(scene_file):
                return
            # Process content from the scene file
            print(f"Processing content from: {scene_file}")
            segments = self._process_with_timestamps(scene_file)
            
            if not segments:
                return
            print(f"Found {len(segments)} segments to process")
            
            # Generate audio with timestamp tracking
            timestamp_data, segment_audio_files, files_to_delete, total_duration = (
                self._generate_audio_for_segments(
                    segments,
                    output_dir=self.audio_analysis_dir,
                    max_sentence_length=200,
                    voice_prompt_path=prompt_speech_file,
                )
            )
            
            if not segment_audio_files:
                return
            
            # Combine all segments, save timestamp JSON, and delete all intermediate files
            final_audio_path, timestamp_json_path = self._combine_audio_files(
                segment_audio_files, 
                timestamp_data, 
                output_file=output_file,
                segment_files=files_to_delete,
                keep_segment_files=False
            )
            
            print(f"Audio successfully generated and saved to: {output_file}")
            return {
                "audio_path": final_audio_path,
                "timestamp_path": timestamp_json_path
            }
        
        except Exception as e:
            print(f"An error occurred in the voice generation process: {str(e)}")
            traceback.print_exc()
            return

