import { describe, expect, it } from "vitest";

import {
  clearSelection,
  fromDraft,
  matchSkills,
  offerableSkills,
  select,
  selectedSkillName,
  submitTextFor,
  type SkillSuggestion,
} from "@/core/skills/selection";
import { RESERVED_SLASH_SKILL_NAMES } from "@/core/skills/slash";
import type { Skill } from "@/core/skills/type";

function makeSkill(name: string, overrides: Partial<Skill> = {}): Skill {
  return {
    name,
    description: `${name} description`,
    category: "public",
    license: "",
    enabled: true,
    editable: true,
    ...overrides,
  };
}

describe("offerableSkills", () => {
  it("keeps the whole catalog when no allowlist is set (inherit)", () => {
    const skills = [makeSkill("research"), makeSkill("writer")];

    expect(offerableSkills(skills, undefined)).toEqual(skills);
  });

  it("treats an empty allowlist as no skills available", () => {
    expect(offerableSkills([makeSkill("research")], [])).toEqual([]);
  });

  it("keeps only skills whose name, slug, or resource id is allowed", () => {
    const skills = [
      makeSkill("research"),
      makeSkill("restricted", { slug: "private-research" }),
      makeSkill("officecli", { resource_id: "skill-resource-id" }),
      makeSkill("writer"),
    ];

    expect(
      offerableSkills(skills, [
        "RESEARCH",
        "private-research",
        "skill-resource-id",
      ]).map((skill) => skill.name),
    ).toEqual(["research", "restricted", "officecli"]);
  });

  it("keeps disabled skills in the offerable set (matching gates enabled separately)", () => {
    const skills = [makeSkill("research", { enabled: false })];

    expect(offerableSkills(skills, ["research"])).toEqual(skills);
  });
});

describe("matchSkills", () => {
  const CATALOG: Skill[] = [
    makeSkill("anthropic-docx", { description: "Word document processing" }),
    makeSkill("skill-creator", { description: "Create new skills" }),
    makeSkill("consulting-analysis", {
      description: "Professional research reports",
    }),
    makeSkill("research", { description: "Deep dive research" }),
    makeSkill("research-pro", {
      description: "Deeper research",
      enabled: false,
    }),
    makeSkill("web-search", { description: "Search the web" }),
  ];
  const builtins: SkillSuggestion[] = [
    {
      name: "goal",
      description: "Set, show, or clear an active goal",
      kind: "builtin",
    },
    { name: "new", description: "Start a new thread", kind: "builtin" },
  ];

  it("matches by name or description, case-insensitively", () => {
    expect(
      matchSkills({ skills: CATALOG }, "research reports").map(
        (suggestion) => suggestion.name,
      ),
    ).toEqual(["consulting-analysis"]);
    const upper = matchSkills({ skills: CATALOG }, "RESEARCH").map(
      (suggestion) => suggestion.name,
    );
    expect(upper[0]).toBe("research");
    expect(upper).toContain("consulting-analysis");
  });

  it("widens the typing flow: a description match beats no match even when the name misses", () => {
    // Behavior change of the unified matcher: the "/" typing flow previously
    // matched names only; it now shares the overlay's name-or-description rule.
    expect(
      matchSkills(
        { skills: [makeSkill("summarizer", { description: "deep research" })] },
        "research",
      ).map((suggestion) => suggestion.name),
    ).toEqual(["summarizer"]);
  });

  it("returns every enabled skill for an empty query", () => {
    expect(matchSkills({ skills: CATALOG }, "")).toHaveLength(5);
  });

  it("excludes disabled skills", () => {
    expect(matchSkills({ skills: CATALOG }, "research-pro")).toEqual([]);
  });

  it("ranks startsWith matches ahead of substring matches, stable otherwise", () => {
    const skills = [makeSkill("my-research"), makeSkill("research")];
    expect(
      matchSkills({ skills }, "research").map((suggestion) => suggestion.name),
    ).toEqual(["research", "my-research"]);
  });

  it("drops skills whose name the slash parsers refuse (shared contract)", () => {
    for (const reserved of RESERVED_SLASH_SKILL_NAMES) {
      const skills = [makeSkill(reserved), makeSkill(`${reserved}-helper`)];
      expect(
        matchSkills({ skills }, reserved).map((suggestion) => suggestion.name),
      ).toEqual([`${reserved}-helper`]);
    }
  });

  it("reserves extra names (the composer's builtin commands) on top of the contract", () => {
    const skills = [makeSkill("goal"), makeSkill("goal-helper")];

    const result = matchSkills({ skills, builtins }, "goal", ["goal", "new"]);

    expect(
      result.map((suggestion) => `${suggestion.kind}:${suggestion.name}`),
    ).toEqual(["skill:goal-helper", "builtin:goal"]);
  });

  it("offers only builtin commands when the catalog is empty (denied role)", () => {
    expect(
      matchSkills({ skills: [], builtins }, "").map(
        (suggestion) => suggestion.name,
      ),
    ).toEqual(["goal", "new"]);
    expect(matchSkills({ skills: [], builtins }, "deep")).toEqual([]);
  });

  it("matches builtin commands by name or description and lists them after skills", () => {
    const result = matchSkills(
      {
        skills: [
          makeSkill("goal-helper", { description: "tracks the active goal" }),
        ],
        builtins,
      },
      "active goal",
    );

    expect(result.map((suggestion) => suggestion.name)).toEqual([
      "goal-helper",
      "goal",
    ]);
  });

  it("caps the combined list when the scope carries a limit", () => {
    const skills = Array.from({ length: 10 }, (_, i) =>
      makeSkill(`skill-${i}`),
    );

    expect(matchSkills({ skills, builtins, limit: 6 }, "")).toHaveLength(6);
    expect(matchSkills({ skills }, "")).toHaveLength(10);
  });

  it("returns an empty list when nothing matches", () => {
    expect(matchSkills({ skills: CATALOG }, "zzzzz")).toEqual([]);
  });
});

describe("selection state and submission prefix", () => {
  it("select builds the chip state and clear is the null selection", () => {
    const skill = makeSkill("research", { description: "Research a topic" });

    expect(select(skill)).toEqual({
      name: "research",
      description: "Research a topic",
    });
    expect(clearSelection()).toBeNull();
  });

  it("selectedSkillName reads the activated name, null otherwise", () => {
    expect(selectedSkillName(select(makeSkill("research")))).toBe("research");
    expect(selectedSkillName(null)).toBeNull();
  });

  it("submitTextFor produces the `/name ` wire prefix only when a skill is selected", () => {
    expect(submitTextFor("summarize this", "research")).toBe(
      "/research summarize this",
    );
    expect(submitTextFor("summarize this", null)).toBe("summarize this");
  });
});

describe("fromDraft", () => {
  it("restores the chip when the saved skill is enabled and offerable", () => {
    const skills = [makeSkill("research", { description: "Research a topic" })];

    expect(fromDraft("research", { text: "topic", skills })).toEqual({
      text: "topic",
      selected: { name: "research", description: "Research a topic" },
    });
  });

  it("folds the saved skill back into `/name text` when it is no longer offerable", () => {
    expect(
      fromDraft("data-analysis", {
        text: "Analyze the latest results",
        skills: [],
      }),
    ).toEqual({
      text: "/data-analysis Analyze the latest results",
      selected: null,
    });
  });

  it("folds without a separating space when the draft text is empty", () => {
    expect(fromDraft("data-analysis", { text: "", skills: [] })).toEqual({
      text: "/data-analysis",
      selected: null,
    });
  });

  it("passes through a draft without a skill", () => {
    expect(fromDraft(null, { text: "hello", skills: [] })).toEqual({
      text: "hello",
      selected: null,
    });
  });

  it("degrades a saved skill that is offerable but disabled", () => {
    const skills = [makeSkill("research", { enabled: false })];

    expect(fromDraft("research", { text: "topic", skills })).toEqual({
      text: "/research topic",
      selected: null,
    });
  });
});
