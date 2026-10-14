import type { AnchorHTMLAttributes } from "react";

import { resolveMarkdownArtifactURL } from "@/core/artifacts/utils";
import { cn } from "@/lib/utils";

import { CitationLink, extractReactNodeText } from "../citations/citation-link";

import { isSafeHref } from "./is-safe-href";

export { isSafeHref };

function isExternalUrl(href: string | undefined): boolean {
  if (typeof href !== "string") {
    return false;
  }
  return /^https?:\/\//.test(href);
}

/**
 * Builds the `a` renderer shared by message content and generic markdown.
 * Passing a `threadId` also resolves `/mnt/` artifact links; without it those
 * links fall through to the default external-link handling.
 */
export function createMarkdownLinkComponent(threadId?: string, runId?: string) {
  return function MarkdownLink({
    href,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement>) {
    // Reject unsafe schemes up front so a prompt-injected / pasted href can
    // never reach the rendered anchor — including through the citation
    // branch (which renders <a href={href}> directly). Check before the
    // citation block so prompt-injected [citation:x](javascript:...) is
    // blocked. Keep the visible label so the user can still see what the
    // link claimed to point at.
    const childrenText = extractReactNodeText(props.children);
    const citationMatch =
      childrenText !== null ? /^citation:(.+)$/.exec(childrenText) : null;
    const evidenceHref = href?.startsWith("evidence://");
    if (
      href !== undefined &&
      (!isSafeHref(href) || (evidenceHref && !citationMatch))
    ) {
      // Intentionally no {...props} spread: react-markdown props like `node`
      // (and anchor-only attributes such as target/rel) are not valid on a
      // <span> and would trigger React DOM warnings.
      const { className, children } = props;
      return (
        <span
          className={cn(
            "text-muted-foreground cursor-not-allowed underline decoration-dotted underline-offset-2",
            className,
          )}
          aria-label="Unsafe link omitted"
          title={`Unsafe link scheme in ${href}`}
        >
          {children}
        </span>
      );
    }
    // Safe-href check passed — citation links now route through CitationLink.
    if (citationMatch) {
      const [, text] = citationMatch;
      return (
        <CitationLink {...props} href={href} runId={runId}>
          {text}
        </CitationLink>
      );
    }
    if (threadId && href?.startsWith("/mnt/")) {
      return (
        <a
          {...props}
          href={resolveMarkdownArtifactURL(href, threadId)}
          target="_blank"
          rel="noopener noreferrer"
        />
      );
    }
    const { className, target, rel, ...rest } = props;
    const external = isExternalUrl(href);
    return (
      <a
        {...rest}
        href={href}
        className={cn(
          "text-primary decoration-primary/30 hover:decoration-primary/60 underline underline-offset-2 transition-colors",
          className,
        )}
        target={target ?? (external ? "_blank" : undefined)}
        rel={rel ?? (external ? "noopener noreferrer" : undefined)}
      />
    );
  };
}
