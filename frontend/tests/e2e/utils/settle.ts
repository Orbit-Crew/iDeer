import { expect, type Page } from "@playwright/test";

/**
 * Wait until the page has no running CSS/Web animations, replacing fixed
 * "animation settle" sleeps with an observable signal.
 *
 * Bounded: persistent animations (spinners, progress bars) never reach zero,
 * in which case the poll degrades to the bounded wait the fixed sleep used
 * to provide.
 */
export async function waitForAnimationsSettled(
  page: Page,
  timeout = 5_000,
): Promise<void> {
  await expect
    .poll(
      () =>
        page.evaluate(
          () =>
            document.getAnimations().filter((a) => a.playState === "running")
              .length,
        ),
      { timeout, intervals: [100] },
    )
    .toBe(0)
    .catch(() => {
      // Persistent animations never settle; the bounded poll above is the
      // observable form of the fixed sleep this replaces.
    });
}
