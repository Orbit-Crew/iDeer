import { readdirSync, readFileSync, statSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { describe, expect, test } from "vitest";

describe("production typography contract", () => {
  test("defines the production typography roles and responsive scale", async () => {
    const css = await readFile(
      join(process.cwd(), "src/styles/globals.css"),
      "utf8",
    );

    expect(css).toContain("--text-display: 2.5rem;");
    expect(css).toContain("--text-display-hero: clamp(2.25rem, 4vw, 2.75rem);");
    expect(css).toContain("--text-page-title: 1.5rem;");
    expect(css).toContain("--text-section-title: 1.125rem;");
    expect(css).toContain("--text-body: 1rem;");
    expect(css).toContain("--text-supporting: 0.875rem;");
    expect(css).toContain("--text-compact: 0.75rem;");
    expect(css).toContain(".type-display");
    expect(css).toContain(".type-page-title");
    expect(css).toContain(".type-section-title");
    expect(css).toContain(".type-body");
    expect(css).toContain(".type-supporting");
    expect(css).toContain(".type-compact");
    expect(css).toContain("line-height: 1.5;");
    expect(css).not.toMatch(/h[123]\s*\{[^}]*font-size:[^}]*!important/s);
  });

  test("does not retain unclassified small or utility text sizes", async () => {
    const { execFile } = await import("node:child_process");
    const { promisify } = await import("node:util");
    const run = promisify(execFile);

    // Fallback when ripgrep is unavailable on the runner (e.g. minimal CI
    // images): walk src with plain Node fs so the contract still validates
    // instead of failing with `spawn rg ENOENT`.
    function walkFiles(dir: string, out: string[]): void {
      for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        const stat = statSync(full);
        if (stat.isDirectory()) {
          if (full.includes(`${join("src", "app", "prototype")}`)) continue;
          walkFiles(full, out);
        } else if (stat.isFile()) {
          out.push(full);
        }
      }
    }

    function fallbackScan(kind: "class" | "css"): string {
      const root = join(process.cwd(), "src");
      const files: string[] = [];
      walkFiles(root, files);
      const classRe =
        /text-(xs|sm|lg|xl|2xl|3xl|4xl|5xl|6xl)|text-\[(8px|10px|11px)\]/;
      const cssRe = /font-size\s*:\s*(8|9|10|11|12|13|14|15)px/;
      const hits: string[] = [];
      for (const file of files) {
        const rel = file.slice(process.cwd().length + 1);
        if (rel.includes("src/app/prototype/")) continue;
        if (kind === "class") {
          if (!/\.tsx?$/.test(file)) continue;
          if (/\.test\.[^.]+$/.test(file)) continue;
          if (rel === join("src", "components", "landing", "hero.tsx"))
            continue;
          const content = readFileSync(file, "utf8");
          if (classRe.test(content)) hits.push(rel);
        } else {
          if (!file.endsWith(".css")) continue;
          const content = readFileSync(file, "utf8");
          if (cssRe.test(content)) hits.push(rel);
        }
      }
      return hits.join("\n");
    }

    async function runScan(
      args: string[],
      kind: "class" | "css",
    ): Promise<string> {
      try {
        const { stdout } = await run("rg", args, { cwd: process.cwd() });
        return stdout;
      } catch (error: unknown) {
        const code = (error as { code?: unknown }).code;
        if (code === 1) return "";
        if (code === "ENOENT") return fallbackScan(kind);
        throw error;
      }
    }

    const classArgs = [
      "-n",
      "--glob",
      "!src/app/prototype/**",
      "--glob",
      "!**/*.test.*",
      "--glob",
      "*.{ts,tsx}",
      "--glob",
      "!src/components/landing/hero.tsx",
      "-e",
      "text-(xs|sm|lg|xl|2xl|3xl|4xl|5xl|6xl)|text-\\[(8px|10px|11px)\\]",
      "src",
    ];
    const cssArgs = [
      "-n",
      "--glob",
      "!src/app/prototype/**",
      "--glob",
      "*.css",
      "-e",
      "font-size\\s*:\\s*(8|9|10|11|12|13|14|15)px",
      "src",
    ];

    const classOutput = await runScan(classArgs, "class");
    const cssOutput = await runScan(cssArgs, "css");

    expect(classOutput).toBe("");
    expect(cssOutput).toBe("");
  });

  test("keeps the landing hero close to its pre-governance scale through roles", async () => {
    const css = await readFile(
      join(process.cwd(), "src/styles/globals.css"),
      "utf8",
    );
    const hero = await readFile(
      join(process.cwd(), "src/components/landing/hero.tsx"),
      "utf8",
    );

    expect(css).toContain(".workbench-welcome-title");
    expect(css).toContain("font-size: var(--text-display-hero);");
    expect(hero).toContain('<h1 className="type-display-hero');
    expect(hero).toContain(
      '<span className="type-body">{t.landing.heroCta}</span>',
    );
  });
});
