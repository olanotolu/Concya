import requests
import json
from typing import Optional, Dict, Any
import os
import time
import logging
from dotenv import load_dotenv

logger = logging.getLogger("concya.llm")

load_dotenv()

class ConcyaLLMClient:
    """Client for Concya's LLM service running on RunPod"""

    def __init__(self):
        load_dotenv()  # Make sure to load env vars
        self.base_url = os.getenv("RUNPOD_URL", "https://xf5aku7r0ssi19-8000.proxy.runpod.net")
        self.api_key = os.getenv("OPENAI_API_KEY")

    def generate_response(self, user_message: str, context: Optional[str] = None) -> str:
        """
        Generate a response using the LLM service

        Args:
            user_message: The user's input message
            context: Optional conversation context

        Returns:
            AI-generated response string
        """
        try:
            # First try RunPod service
            try:
                # Use restaurant-specific prompt for restaurant reservations
                try:
                    from restaurant.prompts import RESTAURANT_SYSTEM_PROMPT
                    system_prompt = RESTAURANT_SYSTEM_PROMPT
                except ImportError:
                    # Fallback to general prompt if restaurant module not available
                    system_prompt = "You are Concya, a helpful AI voice assistant. Keep your responses conversational, friendly, and concise since this will be spoken aloud. You're currently having a phone conversation with a user."

                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt
                        }
                    ],
                    "max_tokens": 150,
                    "temperature": 0.7
                }

                if context:
                    payload["messages"].append({
                        "role": "system",
                        "content": f"Context: {context}"
                    })

                payload["messages"].append({
                    "role": "user",
                    "content": user_message
                })

                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }

                start_time = time.time()
                response = requests.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=5  # Shorter timeout
                )
                runpod_duration = time.time() - start_time
                logger.info(f"🔗 RunPod API call: {runpod_duration:.3f}s")

                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"].strip()

            except (requests.RequestException, KeyError, json.JSONDecodeError):
                print("⚠️  RunPod service unavailable, falling back to direct OpenAI API")

            # Fallback to direct OpenAI API
            # Use restaurant-specific prompt for restaurant reservations
            try:
                from restaurant.prompts import RESTAURANT_SYSTEM_PROMPT
                system_prompt = RESTAURANT_SYSTEM_PROMPT
            except ImportError:
                # Fallback to general prompt if restaurant module not available
                system_prompt = "You are Concya, a helpful AI voice assistant. Keep your responses conversational, friendly, and concise since this will be spoken aloud. You're currently having a phone conversation with a user."

            openai_payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": user_message
                    }
                ],
                "max_tokens": 150,
                "temperature": 0.7
            }

            openai_headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            openai_start_time = time.time()
            openai_response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                json=openai_payload,
                headers=openai_headers,
                timeout=10
            )
            openai_duration = time.time() - openai_start_time
            logger.info(f"🔗 OpenAI API call: {openai_duration:.3f}s")

            openai_response.raise_for_status()
            openai_result = openai_response.json()
            return openai_result["choices"][0]["message"]["content"].strip()

        except requests.RequestException as e:
            print(f"❌ LLM API Error: {e}")
            return "I'm sorry, I'm having trouble connecting right now. Can you try again?"

        except (KeyError, json.JSONDecodeError) as e:
            print(f"❌ LLM Response Parsing Error: {e}")
            return "I got a response but couldn't understand it. Let's try again."

    def health_check(self) -> bool:
        """Check if the LLM service is healthy"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
