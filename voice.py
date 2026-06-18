#!/usr/bin/env python3
"""
Jarvis Voice — desktop voice assistant.
Run with: python voice.py

Speaks when you speak. Listens automatically.
Ctrl+C to shut down.
"""
import os
import sys
import numpy as np
import sounddevice as sd
import requests
from pathlib import Path
from dotenv import load_dotenv

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env")

from jarvis import ask_jarvis

# ── Audio config ───────────────────────────────────────────────────────────────
SAMPLE_RATE       = 16000
SILENCE_THRESHOLD = 0.015   # raise this if Jarvis triggers on background noise
SILENCE_SECS      = 1.5     # seconds of quiet = you stopped talking
MIN_SPEECH_SECS   = 0.4     # ignore clips shorter than this (coughs, etc.)

# ── Whisper (local STT — no extra API key) ─────────────────────────────────────
_whisper = None

def _load_whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        print("  Loading speech model (one-time ~150MB download)...")
        _whisper = WhisperModel("base.en", device="cpu", compute_type="int8")
    return _whisper

def transcribe(audio: np.ndarray) -> str:
    model = _load_whisper()
    segments, _ = model.transcribe(audio.astype(np.float32), language="en")
    return " ".join(s.text for s in segments).strip()

# ── ElevenLabs TTS ─────────────────────────────────────────────────────────────
def speak(text: str):
    api_key  = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

    if not api_key:
        # No ElevenLabs key — just print
        print(f"\nJARVIS: {text}\n")
        return

    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        params={"output_format": "pcm_16000"},
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        },
        timeout=20,
    )

    if resp.ok:
        audio = np.frombuffer(resp.content, dtype=np.int16).astype(np.float32) / 32768.0
        sd.play(audio, SAMPLE_RATE)
        sd.wait()
    else:
        print(f"\nJARVIS: {text}\n")

# ── Main loop ──────────────────────────────────────────────────────────────────
def run():
    print("\n" + "=" * 50)
    print("  JARVIS — ONLINE")
    print("  Talk naturally. Ctrl+C to quit.")
    print("=" * 50 + "\n")

    _load_whisper()

    # Greeting
    greeting = ask_jarvis(
        "You just came online in voice mode on Jace's desktop. "
        "Give one short natural welcome line — like you're in the room with him."
    )
    print(f"JARVIS: {greeting}\n")
    speak(greeting)

    chunk_size  = int(SAMPLE_RATE * 0.1)          # 100ms audio chunks
    silence_max = int(SILENCE_SECS / 0.1)          # chunks of silence = done talking
    speech_min  = int(MIN_SPEECH_SECS / 0.1)       # minimum chunks to process

    buf          = []
    speaking     = False
    quiet_chunks = 0

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=chunk_size) as stream:
        while True:
            data, _ = stream.read(chunk_size)
            data     = data.flatten()
            is_loud  = np.sqrt(np.mean(data ** 2)) > SILENCE_THRESHOLD

            if is_loud:
                if not speaking:
                    speaking = True
                    print("You: ", end="", flush=True)
                buf.append(data)
                quiet_chunks = 0

            elif speaking:
                buf.append(data)
                quiet_chunks += 1

                if quiet_chunks >= silence_max:
                    print()

                    if len(buf) >= speech_min:
                        audio = np.concatenate(buf)
                        text  = transcribe(audio)

                        if text:
                            print(f"You: {text}")
                            print("...", end="", flush=True)
                            reply = ask_jarvis(text)
                            print(f"\rJARVIS: {reply}\n")
                            speak(reply)

                    buf, speaking, quiet_chunks = [], False, 0

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n\nJarvis offline.")
