"""
Video Script Agent
Generates a 60-second cinematic love-story script via Claude claude-sonnet-4-6,
converts the voiceover to speech with ElevenLabs, and logs everything to memory.
"""
import json
import os
from datetime import datetime
from pathlib import Path

import anthropic
import requests
import memory_store

_ROOT = Path(__file__).resolve().parent.parent
_MEMORY_DIR = _ROOT / "memory"
_OUTPUT_DIR = _ROOT / "outputs"

SCRIPTS_FILE = _MEMORY_DIR / "video_scripts.json"
VIDEO_MEMORY_FILE = _MEMORY_DIR / "video_memory.json"

_SCRIPT_PROMPT = """Write a 60-second short-film voiceover script — a love story that is emotional,
cinematic, and ends with a plot twist. Format it as alternating scene descriptions
and voiceover lines. Maximum 150 words total.

Return ONLY the script, no preamble. First line must be: Title: <title>

Structure:
Title: <title>
[SCENE: description]
VOICEOVER: "line..."
[SCENE: description]
VOICEOVER: "line..."
...(continue to plot-twist ending)..."""


class VideoScriptAgent:
    name = "video_script"

    def run(self) -> str:
        try:
            return self._run()
        except Exception as exc:
            msg = f"VIDEO SCRIPT\n  Error: {exc}"
            memory_store.update_agent(self.name, msg)
            return msg

    def _run(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        script = self._generate_script()
        title = self._extract_title(script)

        self._save_script(script, timestamp)

        voiceover = self._extract_voiceover(script)
        audio_path, audio_note = self._text_to_speech(voiceover, timestamp)

        self._log_video_memory(timestamp, title, script, audio_note)

        first_content_line = next(
            (ln.strip() for ln in script.splitlines()
             if ln.strip() and not ln.lower().startswith("title:")),
            script.splitlines()[0],
        )

        summary = (
            f"VIDEO SCRIPT\n"
            f"  Title: {title}\n"
            f"  Audio: {audio_note}\n"
            f"  Ready for Kling render.\n"
            f"  Script: {first_content_line}"
        )

        memory_store.update_agent(
            self.name,
            summary,
            {"title": title, "timestamp": timestamp, "audio": audio_note},
        )
        return summary

    # ── Claude ────────────────────────────────────────────────────────────────

    def _generate_script(self) -> str:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY not set in .env")
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": _SCRIPT_PROMPT}],
        )
        return msg.content[0].text.strip()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_script(self, script: str, timestamp: str) -> None:
        _MEMORY_DIR.mkdir(exist_ok=True)
        existing = []
        if SCRIPTS_FILE.exists():
            try:
                existing = json.loads(SCRIPTS_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        existing.append({"timestamp": timestamp, "script": script})
        SCRIPTS_FILE.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _log_video_memory(
        self, timestamp: str, title: str, script: str, audio_note: str
    ) -> None:
        _MEMORY_DIR.mkdir(exist_ok=True)
        log: dict = {"sessions": []}
        if VIDEO_MEMORY_FILE.exists():
            try:
                log = json.loads(VIDEO_MEMORY_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        log.setdefault("sessions", []).append(
            {
                "timestamp": timestamp,
                "title": title,
                "word_count": len(script.split()),
                "audio_status": audio_note,
            }
        )
        VIDEO_MEMORY_FILE.write_text(
            json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── ElevenLabs ────────────────────────────────────────────────────────────

    def _text_to_speech(self, voiceover: str, timestamp: str) -> tuple[str | None, str]:
        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            return None, "ElevenLabs key not set — audio skipped"

        voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

        try:
            resp = requests.post(
                url,
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": voiceover,
                    "model_id": "eleven_monolingual_v1",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                },
                timeout=60,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            return None, f"ElevenLabs error: {exc}"

        _OUTPUT_DIR.mkdir(exist_ok=True)
        out = _OUTPUT_DIR / f"voiceover_{timestamp}.mp3"
        out.write_bytes(resp.content)
        return str(out), f"voiceover_{timestamp}.mp3 saved"

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_title(script: str) -> str:
        for line in script.splitlines():
            if line.lower().startswith("title:"):
                return line.split(":", 1)[1].strip()
        return "Untitled"

    @staticmethod
    def _extract_voiceover(script: str) -> str:
        lines = []
        for line in script.splitlines():
            s = line.strip()
            if s.upper().startswith("VOICEOVER:"):
                text = s[len("VOICEOVER:"):].strip().strip('"').strip("'")
                lines.append(text)
        return " ".join(lines)


# ── Standalone run ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    print(VideoScriptAgent().run())
