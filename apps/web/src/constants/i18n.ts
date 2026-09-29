import { Locale, Params, T } from "../types";
import { en } from "./locales/en";
import { hi } from "./locales/hi";
import { mr } from "./locales/mr";
import { te } from "./locales/te";
import { kn } from "./locales/kn";

// Hand-written dictionaries shipped with the app; other node languages are machine-translated by the API.
const DICTIONARIES: Record<string, Record<string, string>> = { "en-IN": en, "hi-IN": hi, "mr-IN": mr, "te-IN": te, "kn-IN": kn };

export const BUILTIN_LANGUAGES: { locale: Locale; name: string }[] = [
  { locale: "en-IN", name: "English" }, { locale: "hi-IN", name: "हिन्दी" }, { locale: "mr-IN", name: "मराठी" },
  { locale: "te-IN", name: "తెలుగు" }, { locale: "kn-IN", name: "ಕನ್ನಡ" },
];

export const hasDictionary = (locale: Locale) => locale in DICTIONARIES;

/** Missing keys fall back to English, then to the key itself. */
export function makeT(locale: Locale, remote?: Record<string, string> | null): T {
  const dict = DICTIONARIES[locale] || remote || en;
  return (key: string, params?: Params) => {
    let text = dict[key] ?? en[key] ?? key;
    if (params) {
      for (const [name, value] of Object.entries(params)) text = text.split(`{${name}}`).join(value == null ? "" : String(value));
    }
    return text;
  };
}
