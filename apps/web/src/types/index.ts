import { Json } from "../api";

export type View = "home" | "farm" | "weather" | "soil" | "crops" | "advice" | "diagnose" | "expert";

/** BCP-47 tag such as "mr-IN" or "pt-BR"; the node decides which languages it offers. */
export type Locale = string;

/** A language offered by this node (from /api/v1/node). */
export interface NodeLanguage {
  locale: Locale;
  name: string;
  machine_translated: boolean;
}

export type Params = Record<string, string | number | null | undefined>;

/** Translate a key with {placeholders}; falls back to English, then to the key itself. */
export type T = (key: string, params?: Params) => string;

export type { Json };
