from __future__ import annotations

from ..settings import Settings, get_settings


class VoiceUnavailable(RuntimeError):
    pass


# Preferred voice families, best first; the concrete voice is discovered per language.
VOICE_QUALITY = ("Chirp3-HD", "Neural2", "Wavenet", "Standard")
_VOICE_CACHE: dict[str, str | None] = {}


class VoiceProvider:
    """Google Speech adapter derived from the original project's verified SDK pattern."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def transcribe(self, content: bytes, locale: str, content_type: str) -> tuple[str, float | None]:
        if not self.settings.speech_enabled:
            raise VoiceUnavailable("Google Speech is disabled")
        from google.cloud.speech_v2 import SpeechClient
        from google.cloud.speech_v2.types import cloud_speech

        if not self.settings.google_cloud_project:
            raise VoiceUnavailable("GOOGLE_CLOUD_PROJECT is required for speech")
        recognizer = f"projects/{self.settings.google_cloud_project}/locations/{self.settings.speech_location}/recognizers/_"
        config = cloud_speech.RecognitionConfig(
            language_codes=[locale],
            model="latest_short",
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
        )
        response = SpeechClient().recognize(
            request=cloud_speech.RecognizeRequest(recognizer=recognizer, config=config, content=content)
        )
        transcripts = [result.alternatives[0] for result in response.results if result.alternatives]
        if not transcripts:
            raise VoiceUnavailable("Google Speech returned no transcript")
        return " ".join(item.transcript for item in transcripts).strip(), sum(item.confidence for item in transcripts) / len(transcripts)

    def speak(self, text: str, locale: str) -> tuple[bytes, str]:
        if not self.settings.speech_enabled:
            raise VoiceUnavailable("Google Text-to-Speech is disabled")
        from google.cloud import texttospeech

        client = texttospeech.TextToSpeechClient()
        voice_name = self._voice(client, locale)
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(language_code=locale, name=voice_name),
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3),
        )
        return response.audio_content, "audio/mpeg"

    @staticmethod
    def _voice(client, locale: str) -> str:
        """Best available Google voice for the language, so a new node language needs no configuration."""
        if locale not in _VOICE_CACHE:
            voices = [voice.name for voice in client.list_voices(language_code=locale).voices
                      if any(code == locale for code in voice.language_codes)]
            ranked = sorted(voices, key=lambda name: next((i for i, q in enumerate(VOICE_QUALITY) if q in name), len(VOICE_QUALITY)))
            _VOICE_CACHE[locale] = ranked[0] if ranked else None
        if not _VOICE_CACHE[locale]:
            raise VoiceUnavailable(f"Google Text-to-Speech has no voice for {locale}")
        return _VOICE_CACHE[locale]
