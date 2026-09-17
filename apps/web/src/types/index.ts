import { Json } from "../api";

export type View = "home" | "farm" | "weather" | "soil" | "crops" | "advice" | "diagnose" | "expert";

export type Locale = "en-IN" | "hi-IN" | "mr-IN" | "te-IN" | "kn-IN";

export interface TranslationDictionary {
  [key: string]: string;
}

export type { Json };
