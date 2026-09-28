import { Locale, Params, T } from "../types";
import { en } from "./locales/en";
import { hi } from "./locales/hi";
import { mr } from "./locales/mr";
import { te } from "./locales/te";
import { kn } from "./locales/kn";

const DICTIONARIES: Record<Locale, Record<string, string>> = { "en-IN": en, "hi-IN": hi, "mr-IN": mr, "te-IN": te, "kn-IN": kn };

/** Farmer-facing text is translated in every language; missing keys fall back to English. */
export function makeT(locale: Locale): T {
  const dict = DICTIONARIES[locale] || en;
  return (key: string, params?: Params) => {
    let text = dict[key] ?? en[key] ?? key;
    if (params) {
      for (const [name, value] of Object.entries(params)) text = text.split(`{${name}}`).join(value == null ? "" : String(value));
    }
    return text;
  };
}
