import requests
import os
import uuid
import time
import logging
from pathlib import Path
from typing import Optional, Tuple
from dotenv import load_dotenv

logger = logging.getLogger("concya.tts")

load_dotenv()

class ConcyaTTSClient:
    """Client for Concya's Text-to-Speech using OpenAI TTS"""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.audio_dir = Path("audio_cache")
        self.audio_dir.mkdir(exist_ok=True)
        print(f"🔊 TTS Client initialized - API Key loaded: {bool(self.api_key)}")

    def generate_speech(self, text: str, voice: str = "alloy", model: str = "tts-1") -> Optional[str]:
        """
        Generate speech audio from text using OpenAI TTS

        Args:
            text: Text to convert to speech
            voice: Voice to use ('alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer')
            model: TTS model to use ('tts-1' or 'tts-1-hd')

        Returns:
            Path to generated audio file, or None if failed
        """
        try:
            # Clean and prepare text
            text = text.strip()
            if not text:
                return None

            # Generate unique filename
            audio_filename = f"{uuid.uuid4()}.mp3"
            audio_path = self.audio_dir / audio_filename

            # Prepare OpenAI TTS request
            payload = {
                "model": model,
                "input": text,
                "voice": voice,
                "response_format": "mp3"
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            print(f"🎵 Generating TTS for: '{text[:50]}...' using voice '{voice}'")

            # Make API request
            api_start_time = time.time()
            response = requests.post(
                "https://api.openai.com/v1/audio/speech",
                json=payload,
                headers=headers,
                timeout=30
            )
            api_duration = time.time() - api_start_time
            logger.info(f"🔊 OpenAI TTS API call: {api_duration:.3f}s")

            response.raise_for_status()

            # Save audio file
            file_start_time = time.time()
            with open(audio_path, 'wb') as f:
                f.write(response.content)
            file_duration = time.time() - file_start_time
            logger.info(f"💾 Audio file save: {file_duration:.3f}s")

            print(f"✅ Audio saved to: {audio_path}")
            return str(audio_path)

        except requests.RequestException as e:
            print(f"❌ TTS API Error: {e}")
            return None
        except Exception as e:
            print(f"❌ TTS Error: {e}")
            return None

    def cleanup_old_files(self, max_age_minutes: int = 30):
        """Clean up old audio files to prevent disk space issues"""
        try:
            current_time = time.time()
            max_age_seconds = max_age_minutes * 60

            for audio_file in self.audio_dir.glob("*.mp3"):
                if current_time - audio_file.stat().st_mtime > max_age_seconds:
                    audio_file.unlink()
                    print(f"🗑️ Cleaned up old audio file: {audio_file}")

        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")

    def get_available_voices(self) -> list:
        """Get list of available OpenAI TTS voices"""
        return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    def get_voice_info(self) -> dict:
        """Get information about available voices"""
        return {
            "alloy": "Neutral, balanced voice",
            "echo": "Male voice with a warm, clear tone",
            "fable": "British-accented female voice",
            "onyx": "Deep, authoritative male voice",
            "nova": "Youthful, energetic female voice",
            "shimmer": "Warm, confident female voice"
        }
