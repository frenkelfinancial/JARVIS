#!/usr/bin/env python3
"""
Jarvis Voice — desktop voice assistant.
Run with: python voice.py

Speaks when you speak. Listens automatically.
Ctrl+C to shut down.
"""
import os
import sys
import ctypes
import tempfile
import numpy as np
import sounddevice as sd
import requests
from pathlib import Path
from dotenv import load_dotenv

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env")

os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

from jarvis import ask_jarvis
import memory_store

# ── Audio config ───────────────────────────────────────────────────────────────
SAMPLE_RATE       = 16000
SILENCE_THRESHOLD = 0.015   # raise if Jarvis triggers on background noise
SILENCE_SECS      = 1.5     # seconds of quiet = you stopped talking
MIN_SPEECH_SECS   = 0.4     # ignore clips shorter than this

# ── Agent context ──────────────────────────────────────────────────────────────
def _build_agent_context() -> str:
    memory = memory_store.load()
    lines = []
    for name, data in memory.items():
        output = data.get("last_output")
        last_run = data.get("last_run", "never")
        if output:
            lines.append(f"[{name.upper()}] last run {last_run}\n{output}")
    return "\n\n".join(lines) if lines else "Agents haven't run yet — no data available."

# ── Whisper STT (local, no API key needed) ─────────────────────────────────────
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

# ── ElevenLabs TTS — Windows MCI playback (no extra deps) ─────────────────────
def _play_mp3(data: bytes):
    """Play MP3 bytes using Windows built-in MCI — no pygame or extra packages."""
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.write(data)
    tmp.close()
    path = tmp.name.replace("/", "\\")

    mci = ctypes.windll.winmm.mciSendStringW
    mci(f'open "{path}" type mpegvideo alias jarvis', None, 0, None)
    mci("play jarvis wait", None, 0, None)
    mci("close jarvis", None, 0, None)
    try:
        os.unlink(tmp.name)
    except Exception:
        pass

def speak(text: str):
    api_key  = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

    if not api_key:
        print(f"\nJARVIS: {text}\n")
        return

    try:
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": "eleven_turbo_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=20,
        )
        if resp.ok:
            _play_mp3(resp.content)
        else:
            print(f"\nJARVIS: {text}")
            print(f"  [ElevenLabs error {resp.status_code}: {resp.text[:100]}]\n")
    except Exception as e:
        print(f"\nJARVIS: {text}")
        print(f"  [Audio error: {e}]\n")

# ── Main loop ──────────────────────────────────────────────────────────────────
def run():
    print("\n" + "=" * 50)
    print("  JARVIS — ONLINE")
    print("  Talk naturally. Ctrl+C to quit.")
    print("=" * 50 + "\n")

    _load_whisper()

    # Load agent memory and pass as context so Jarvis knows everything
    agent_context = _build_agent_context()

    greeting = ask_jarvis(
        "You just came online in voice mode on Jace's desktop. "
        "Give one short natural welcome line — like you're in the room with him.",
        context=agent_context,
    )
    print(f"JARVIS: {greeting}\n")
    speak(greeting)

    chunk_size  = int(SAMPLE_RATE * 0.1)
    silence_max = int(SILENCE_SECS / 0.1)
    speech_min  = int(MIN_SPEECH_SECS / 0.1)

    buf, speaking, quiet_chunks = [], False, 0

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
