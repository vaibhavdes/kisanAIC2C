import { Json } from "../api";

export type View = "home" | "farm" | "weather" | "soil" | "crops" | "advice" | "diagnose" | "expert";

export type Locale = "en-IN" | "hi-IN" | "mr-IN" | "te-IN" | "kn-IN";

export const LOCALES: Locale[] = ["en-IN", "hi-IN", "mr-IN", "te-IN", "kn-IN"];

export type Params = Record<string, string | number | null | undefined>;

/** Translate a key with {placeholders}; falls back to English, then to the key itself. */
export type T = (key: string, params?: Params) => string;

export type { Json };
