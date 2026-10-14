/**
 * Schemes we are willing to render as a navigable ``<a href=...>``.
 *
 * Anything else (``javascript:``, ``data:text/html``, ``vbscript:``,
 * ``file:``, …) is blocked because once it lands in a real anchor the
 * browser happily executes the payload in the chat surface where
 * sessionStorage / CSRF cookies are reachable. We accept ``http(s)``
 * plus the non-executing ``mailto:`` / ``tel:`` schemes; same-origin
 * absolute paths (``/…``), scheme-less relative references (``report.md``,
 * ``./…``, ``../…``), and in-document anchors (``#…``) are also allowed
 * — they all resolve under the current HTTP(S) origin.
 *
 * Shared by every link renderer (markdown-link, artifact-link,
 * citation-link) so the three cannot drift apart (report 07-L6).
 */
const SAFE_HREF_PROTOCOLS = ["http:", "https:", "mailto:", "tel:"] as const;

export function isSafeHref(href: string | undefined): boolean {
  if (typeof href !== "string" || href.length === 0) {
    return false;
  }
  if (/^evidence:\/\/[A-Za-z0-9_-]+$/.test(href)) {
    return true;
  }
  // Same-document anchors (e.g. "#section").
  if (href.startsWith("#")) {
    return true;
  }
  // Protocol-relative URLs (//evil.com/path) would inherit the current
  // page's scheme and navigate to an unknown host. Also reject
  // backslash-normalised variants (\\evil.com → //evil.com) because
  // browsers treat backslash as a path separator in URLs.
  if (/^(\/\/|\\\\)/.test(href)) {
    return false;
  }
  // Parse the href so we can inspect its scheme. Items without an explicit
  // protocol (report.md, ./report.md, ../assets/chart.png, /workspace/foo)
  // resolve relative to the dummy HTTPS base, producing an https: URL.
  // Explicitly-schemed URLs (https://…, mailto:, javascript:, data:, …)
  // keep their native scheme, which we then check against the allowlist.
  try {
    const parsed = new URL(href, "https://dummy.example/");
    return (SAFE_HREF_PROTOCOLS as ReadonlyArray<string>).includes(
      parsed.protocol,
    );
  } catch {
    return false;
  }
}
