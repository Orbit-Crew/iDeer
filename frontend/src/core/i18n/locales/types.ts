// Derived from the en-US literal, which is the source of truth for the
// translation shape. Adding a key to en-US defines it here; a locale that
// does not implement every key fails to compile.
import type { enUS } from "./en-US";

export type Translations = typeof enUS;
