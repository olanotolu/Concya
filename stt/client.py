#!/usr/bin/env python3
"""
Concya Terminal Client - Real-time Conversational AI
Streams audio from microphone → STT → LLM → TTS playback
"""

import asyncio
import pyaudio
import websockets
import requests
import json
import argparse
import sys
import time
import wave
import io
from colorama import Fore, Style, init
from threading import Thread, Event
from queue import Queue

# Initialize colorama for cross-platform colored output
init(autoreset=True)

# Audio configuration (matches server expectations)
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = int(SAMPLE_RATE * 0.2)  # 200ms chunks
FORMAT = pyaudio.paInt16
BYTES_PER_SAMPLE = 2

# Conversation state
conversation_state = "idle"  # idle, listening, thinking, speaking
last_transcription = ""
speech_debounce_timer = None
session_id = f"terminal_{int(time.time())}"


class ConversationClient:
    def __init__(self, server_url):
        self.server_url = server_url.rstrip('/')
        self.ws_url = server_url.replace('http://', 'ws://').replace('https://', 'wss://').rstrip('/') + '/asr'
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.websocket = None
        self.running = False
        self.audio_queue = Queue()
        self.transcription_queue = Queue()
        self.stop_event = Event()
        
    def print_status(self, message, color=Fore.YELLOW):
        """Print colored status message"""
        print(f"{color}[{conversation_state.upper()}] {message}{Style.RESET_ALL}")
    
    def print_user(self, text):
        """Print user transcription"""
        print(f"{Fore.GREEN}👤 You: {text}{Style.RESET_ALL}")
    
    def print_ai(self, text):
        """Print AI response"""
        print(f"{Fore.BLUE}🤖 Concya: {text}{Style.RESET_ALL}")
    
    def list_audio_devices(self):
        """List available audio input devices"""
        print(f"\n{Fore.CYAN}Available Audio Devices:{Style.RESET_ALL}")
        info = self.audio.get_host_api_info_by_index(0)
        num_devices = info.get('deviceCount')
        
        for i in range(num_devices):
            device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
            if device_info.get('maxInputChannels') > 0:
                print(f"  [{i}] {device_info.get('name')}")
        print()
    
    async def connect_websocket(self):
        """Connect to WebSocket for STT streaming"""
        try:
            self.print_status(f"Connecting to {self.ws_url}...", Fore.CYAN)
            self.websocket = await websockets.connect(self.ws_url)
            
            # Receive config message
            config_msg = await self.websocket.recv()
            config = json.loads(config_msg)
            self.print_status(f"Connected! Config: {config}", Fore.GREEN)
            return True
        except Exception as e:
            self.print_status(f"Failed to connect: {e}", Fore.RED)
            return False
    
    def start_audio_stream(self, device_index=None):
        """Start recording audio from microphone"""
        global conversation_state
        conversation_state = "listening"
        
        try:
            self.stream = self.audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
                input_device_index=device_index,
                stream_callback=self._audio_callback
            )
            self.stream.start_stream()
            self.print_status("🎤 Microphone active - speak now!", Fore.GREEN)
        except Exception as e:
            self.print_status(f"Failed to start audio: {e}", Fore.RED)
            sys.exit(1)
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for audio stream - queues audio data"""
        if self.running:
            self.audio_queue.put(in_data)
        return (None, pyaudio.paContinue)
    
    async def send_audio_loop(self):
        """Send audio chunks to WebSocket"""
        while self.running:
            try:
                # Non-blocking queue get with timeout
                if not self.audio_queue.empty():
                    audio_data = self.audio_queue.get_nowait()
                    if self.websocket and self.websocket.open:
                        await self.websocket.send(audio_data)
                else:
                    await asyncio.sleep(0.01)  # Small delay to prevent busy loop
            except Exception as e:
                self.print_status(f"Error sending audio: {e}", Fore.RED)
                break
    
    async def receive_transcription_loop(self):
        """Receive transcription results from WebSocket"""
        global last_transcription, conversation_state
        
        while self.running:
            try:
                if self.websocket and self.websocket.open:
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=0.1)
                    data = json.loads(message)
                    
                    if data.get('type') == 'ready_to_stop':
                        self.print_status("Server ready to stop", Fore.YELLOW)
                        continue
                    
                    # Extract transcription
                    lines = data.get('lines', [])
                    buffer_text = data.get('buffer_transcription', '')
                    
                    if lines:
                        # Display completed lines
                        for line in lines:
                            text = line.get('text', '').strip()
                            if text and text != last_transcription:
                                last_transcription = text
                                self.print_user(text)
                                
                                # Queue for LLM processing
                                self.transcription_queue.put({
                                    'text': text,
                                    'language': line.get('detected_language', 'en')
                                })
                    
                    # Show buffer (partial transcription) on same line
                    if buffer_text and conversation_state == "listening":
                        print(f"\r{Fore.CYAN}Listening: {buffer_text}{Style.RESET_ALL}", end='', flush=True)
                
                else:
                    await asyncio.sleep(0.1)
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if self.running:
                    self.print_status(f"Error receiving transcription: {e}", Fore.RED)
                break
    
    async def process_llm_loop(self):
        """Process transcriptions with LLM and play TTS"""
        global conversation_state
        last_process_time = 0
        
        while self.running:
            try:
                # Check if we have transcription to process
                if not self.transcription_queue.empty():
                    # Debounce: wait 1.5 seconds between LLM calls
                    current_time = time.time()
                    if current_time - last_process_time < 1.5:
                        await asyncio.sleep(0.1)
                        continue
                    
                    transcription_data = self.transcription_queue.get()
                    text = transcription_data['text']
                    language = transcription_data['language']
                    
                    # Clear the listening line
                    print("\r" + " " * 80 + "\r", end='', flush=True)
                    
                    # Change state to thinking
                    conversation_state = "thinking"
                    self.print_status("🤔 Processing with AI...", Fore.YELLOW)
                    
                    # Send to LLM
                    try:
                        response = requests.post(
                            f"{self.server_url}/conversation",
                            json={
                                'text': text,
                                'session_id': session_id,
                                'language': language
                            },
                            timeout=30
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            reply = data.get('reply', '')
                            
                            if reply:
                                self.print_ai(reply)
                                
                                # Get and play TTS
                                conversation_state = "speaking"
                                self.print_status("🔊 Playing response...", Fore.CYAN)
                                await self.play_tts(reply)
                        else:
                            self.print_status(f"LLM error: {response.status_code}", Fore.RED)
                    
                    except requests.exceptions.Timeout:
                        self.print_status("LLM request timed out", Fore.RED)
                    except Exception as e:
                        self.print_status(f"LLM error: {e}", Fore.RED)
                    
                    # Return to listening
                    conversation_state = "listening"
                    last_process_time = time.time()
                    self.print_status("👂 Listening...", Fore.GREEN)
                
                else:
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                self.print_status(f"Error in LLM loop: {e}", Fore.RED)
                await asyncio.sleep(1)
    
    async def play_tts(self, text):
        """Fetch TTS audio and play it"""
        try:
            response = requests.post(
                f"{self.server_url}/speak",
                json={'text': text, 'voice': 'alloy'},
                timeout=30
            )
            
            if response.status_code == 200:
                audio_data = response.content
                
                if len(audio_data) > 0:
                    # Play audio using pyaudio
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._play_audio_data, audio_data
                    )
                else:
                    self.print_status("Empty audio response", Fore.RED)
            else:
                self.print_status(f"TTS error: {response.status_code}", Fore.RED)
        
        except Exception as e:
            self.print_status(f"TTS playback error: {e}", Fore.RED)
    
    def _play_audio_data(self, audio_data):
        """Play MP3 audio data (blocking, run in executor)"""
        try:
            # Use ffmpeg or similar to decode MP3 to PCM
            # For simplicity, we'll use a temporary approach
            # In production, you'd want to use a proper audio library
            
            import subprocess
            import tempfile
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                f.write(audio_data)
                temp_path = f.name
            
            # Play using system command (cross-platform)
            if sys.platform == 'darwin':  # macOS
                subprocess.run(['afplay', temp_path], check=True)
            elif sys.platform == 'linux':
                subprocess.run(['mpg123', '-q', temp_path], check=True)
            elif sys.platform == 'win32':
                subprocess.run(['powershell', '-c', f'(New-Object Media.SoundPlayer "{temp_path}").PlaySync()'], check=True)
            
            # Clean up
            import os
            os.unlink(temp_path)
            
        except Exception as e:
            print(f"{Fore.RED}Audio playback error: {e}{Style.RESET_ALL}")
    
    async def run(self, device_index=None):
        """Main run loop"""
        self.running = True
        
        # Connect to WebSocket
        if not await self.connect_websocket():
            return
        
        # Start audio recording
        self.start_audio_stream(device_index)
        
        # Create async tasks
        tasks = [
            asyncio.create_task(self.send_audio_loop()),
            asyncio.create_task(self.receive_transcription_loop()),
            asyncio.create_task(self.process_llm_loop())
        ]
        
        try:
            # Wait for all tasks
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            self.print_status("Shutting down...", Fore.YELLOW)
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Clean up resources"""
        self.running = False
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        if self.websocket:
            await self.websocket.close()
        
        self.audio.terminate()
        self.print_status("Goodbye! 👋", Fore.CYAN)


def main():
    parser = argparse.ArgumentParser(description='Concya Terminal Client - Conversational AI')
    parser.add_argument('--server', default='http://localhost:8000', help='Server URL')
    parser.add_argument('--list-devices', action='store_true', help='List audio devices and exit')
    parser.add_argument('--device', type=int, help='Audio input device index')
    
    args = parser.parse_args()
    
    client = ConversationClient(args.server)
    
    if args.list_devices:
        client.list_audio_devices()
        return
    
    print(f"""
{Fore.CYAN}╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   🎙️  Concya Terminal Client - Conversational AI 🤖      ║
║                                                           ║
║   Server: {args.server:<44} ║
║   Session: {session_id:<43} ║
║                                                           ║
║   Press Ctrl+C to exit                                    ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝{Style.RESET_ALL}
""")
    
    try:
        asyncio.run(client.run(args.device))
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Fatal error: {e}{Style.RESET_ALL}")
        sys.exit(1)


if __name__ == '__main__':
    main()

