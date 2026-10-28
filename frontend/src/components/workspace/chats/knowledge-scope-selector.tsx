"use client";

import { useI18n } from "@/core/i18n/hooks";
import type { AgentKnowledgeScope } from "@/core/library";

/**
 * Chat-time knowledge selection (#114).
 *
 * Lists the KB sources the Server authorized for this caller behind the
 * selected Agent — the caller's own device KBs (with live availability) and
 * server provider KBs alike. Toggling sources only narrows what the next Run
 * may search (`runtime_knowledge_scope`); there is no input that could add a
 * KB the frozen closure did not authorize. Local confirmations stay on the
 * device: this panel reports state, it never approves anything.
 */
export function KnowledgeScopeSelector({
  scope,
  loadError = false,
  selected,
  onChange,
}: {
  scope?: AgentKnowledgeScope | null;
  loadError?: boolean;
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const { t } = useI18n();
  const selector = t.library.knowledgeScopeSelector;
  const sources = scope?.sources ?? [];

  if (!loadError && sources.length === 0) return null;

  function toggle(resourceId: string) {
    onChange(
      selected.includes(resourceId)
        ? selected.filter((id) => id !== resourceId)
        : [...selected, resourceId],
    );
  }

  return (
    <div className="rounded-md border p-3" data-testid="knowledge-scope-selector">
      <h3 className="type-section-title font-medium">{selector.title}</h3>
      {loadError ? (
        <div role="alert" className="text-destructive type-body mt-2">
          {selector.loadError}
        </div>
      ) : (
        <>
          <p className="text-muted-foreground type-compact mt-1">
            {selector.narrowOnly}
          </p>
          <ul className="mt-2 space-y-1">
            {sources.map((source) => {
              const name = source.display_name ?? source.slug;
              const checked = selected.includes(source.resource_id);
              const offline =
                source.origin === "local_import" && source.device_online === false;
              return (
                <li key={source.resource_id} className="flex items-center gap-2">
                  <label className="flex min-w-0 cursor-pointer items-center gap-2">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(source.resource_id)}
                      className="h-4 w-4 rounded border-gray-300"
                      aria-label={selector.checkboxAria(name)}
                    />
                    <span className="type-body truncate">{name}</span>
                  </label>
                  <span className="text-muted-foreground type-compact ml-auto flex shrink-0 items-center gap-2">
                    {source.revision_no != null && (
                      <span>{selector.revision(source.revision_no)}</span>
                    )}
                    {source.origin === "local_import" ? (
                      <span
                        className={
                          offline ? "text-destructive" : "text-muted-foreground"
                        }
                      >
                        {offline ? selector.deviceOffline : selector.deviceSource}
                      </span>
                    ) : (
                      <span>{selector.serverSource}</span>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
