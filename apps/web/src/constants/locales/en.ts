import { expertEn } from "./expert-en";
// Farmer-facing English is the shared source in data/i18n/en.json: the API machine-translates it
// (Google Cloud Translation) for node languages that have no hand-written dictionary.
import farmer from "../../../../../data/i18n/en.json";

export const en: Record<string, string> = { ...expertEn, ...farmer };
