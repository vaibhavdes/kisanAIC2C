import { Locale } from "../types";

let current: HTMLAudioElement | null = null;

/** Reads text aloud with Google Cloud Text-to-Speech, falling back to the browser's voice. */
export async function speakText(text: string, locale: Locale): Promise<void> {
  current?.pause();
  window.speechSynthesis?.cancel();
  try {
    const response = await fetch("/api/v1/voice/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Actor-Id": "local-farmer", "X-Actor-Role": "farmer" },
      body: JSON.stringify({ text, locale }),
    });
    if (response.ok) {
      current = new Audio(URL.createObjectURL(await response.blob()));
      await current.play();
      return;
    }
  } catch {
    // Browser voice below.
  }
  if ("speechSynthesis" in window) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = locale;
    window.speechSynthesis.speak(utterance);
  }
}
