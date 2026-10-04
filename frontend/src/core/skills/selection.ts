import { RESERVED_SLASH_SKILL_NAMES } from "./slash";
import type { Skill } from "./type";

/**
 * Single home of the composer's skill-selection protocol: the offerable set,
 * the "/" matcher, the selected-chip state, the `/name ` submission prefix,
 * and the draft-restore degradation rule. The wire protocol — what reaches the
 * backend — is produced only here and is unchanged: the backend parses the
 * `/name ` prefix syntactically, so UI-side filtering and matching are
 * suggestions, not contracts.
 */

/**
 * The offerable skill set: the single gate deciding which skills a composer
 * may present. An absent allowlist inherits the whole catalog; a present one
 * admits a skill by name, slug, or resource id, case-insensitively. Disabled
 * skills stay in the set — enabling is a separate concern of matching and
 * restoration.
 */
export function offerableSkills(
  skills: Skill[],
  allowedNames?: readonly string[],
): Skill[] {
  if (allowedNames === undefined) return skills;

  const allowed = new Set(allowedNames.map((name) => name.toLowerCase()));
  return skills.filter(
    (skill) =>
      allowed.has(skill.name.toLowerCase()) ||
      (skill.slug !== undefined && allowed.has(skill.slug.toLowerCase())) ||
      (skill.resource_id !== undefined &&
        allowed.has(skill.resource_id.toLowerCase())),
  );
}

/**
 * A suggestion row: either a skill activation or one of the composer's builtin
 * slash commands offered alongside it.
 */
export type SkillSuggestion = {
  name: string;
  description: string;
  kind: "builtin" | "skill";
};

/** What to match against: the offerable skills plus, optionally, the builtin
 * commands of the calling composer and a cap on the combined result. */
export type SkillMatchScope = {
  skills: Skill[];
  builtins?: readonly SkillSuggestion[];
  limit?: number;
};

/**
 * The single "/" matcher, shared by the typing flow and the Skill picker.
 * A skill matches when its name or description contains the query
 * (case-insensitive); an empty query offers everything. Skills whose name the
 * slash parsers refuse — the contract's reserved commands plus any extra names
 * passed by the caller (the composer's own builtin commands) — are never
 * offered, because picking them could not activate. Prefix matches rank ahead
 * of substring matches, otherwise catalog order wins. The limit, when given,
 * caps the combined skill + builtin list; the picker passes none.
 */
export function matchSkills(
  scope: SkillMatchScope,
  query: string,
  reservedExtra?: readonly string[],
): SkillSuggestion[] {
  const q = query.toLowerCase();
  const reserved = new Set([
    ...RESERVED_SLASH_SKILL_NAMES,
    ...(reservedExtra ?? []).map((name) => name.toLowerCase()),
  ]);

  const skillMatches = scope.skills
    .map((skill, index) => ({
      skill,
      index,
      name: skill.name.toLowerCase(),
    }))
    .filter(({ skill, name }) => {
      if (!skill.enabled || reserved.has(name)) {
        return false;
      }
      return (
        !q || name.includes(q) || skill.description.toLowerCase().includes(q)
      );
    })
    .sort((a, b) => {
      const aStartsWith = a.name.startsWith(q);
      const bStartsWith = b.name.startsWith(q);
      if (aStartsWith !== bStartsWith) {
        return aStartsWith ? -1 : 1;
      }
      return a.index - b.index;
    })
    .map(({ skill }) => ({
      name: skill.name,
      description: skill.description,
      kind: "skill" as const,
    }));

  const builtinMatches = (scope.builtins ?? []).filter(
    ({ name, description }) =>
      !q ||
      name.toLowerCase().includes(q) ||
      description.toLowerCase().includes(q),
  );

  const combined = [...skillMatches, ...builtinMatches];
  return scope.limit === undefined ? combined : combined.slice(0, scope.limit);
}

/** The activated `/skill` chip: at most one per composer. */
export type SelectedSkill = { name: string; description: string };

/** The chip state, with {@link SelectedSkill} as its set value. */
export type SkillSelection = SelectedSkill | null;

/** Build the chip state for an activated skill suggestion. */
export function select(skill: {
  name: string;
  description: string;
}): SelectedSkill {
  return { name: skill.name, description: skill.description };
}

/** The cleared selection. */
export function clearSelection(): SkillSelection {
  return null;
}

/** The selected skill's name, or null when nothing is activated. */
export function selectedSkillName(selection: SkillSelection): string | null {
  return selection?.name ?? null;
}

/**
 * The wire protocol for an activated skill: the `/name ` prefix followed by
 * the composed text. Without a selection the text passes through unchanged.
 */
export function submitTextFor(text: string, skillName: string | null): string {
  return skillName ? `/${skillName} ${text}` : text;
}

export type SkillDraftScope = {
  /** The draft text restored alongside the skill chip. */
  text: string;
  /** The offerable skills (already through {@link offerableSkills}). */
  skills: Skill[];
};

/**
 * Restore a saved draft's skill selection. A skill that is enabled and
 * offerable comes back as the chip; anything else degrades to plain,
 * editable `/name text` so the user never loses the typed intent. This is
 * the single home of that degradation rule.
 */
export function fromDraft(
  skillName: string | null,
  scope: SkillDraftScope,
): { text: string; selected: SkillSelection } {
  if (skillName) {
    const skill = scope.skills.find(
      (candidate) => candidate.enabled && candidate.name === skillName,
    );
    if (skill) {
      return { text: scope.text, selected: select(skill) };
    }
    return {
      text: `/${skillName}${scope.text ? ` ${scope.text}` : ""}`,
      selected: null,
    };
  }
  return { text: scope.text, selected: null };
}
