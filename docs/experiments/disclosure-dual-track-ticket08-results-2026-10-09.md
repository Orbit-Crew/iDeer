---
id: disclosure-dual-track-ticket08-results
kind: evidence
status: archived
owner: repository maintainers
scope: Six isolated practical implementation sessions, fixture validation, and clean-restore evidence for disclosure dual-track ticket 08
---
# Disclosure dual-track ticket 08 practical results

## Outcome

Ticket 08 practical execution is complete and its practical subgate passes: all six sessions used the same frozen product/test/tool tree and task-matched fault overlay per pair, each implementation stayed in an isolated temporary exercise repository, and focused behavior tests plus narrow static checks passed after each implementation. Independent implementation reviews passed all six candidates. No exercise implementation was integrated into the product tree.

The overall v2 experiment remains **incomplete and does not pass**. Ticket 07 confirmed 14/16 after answers, with one unresolved conditional answer and one tool-drift-invalid answer; baseline was 13/16. The routine Markdown median reduction was 11.8058%, below the frozen 30% threshold. Practical success does not change those reading or cost results, and ticket 09 was not run.

## Inputs and fairness

The six candidate roots are parentless exercise-input commits: UI baseline `c74fbe1223e194fae5b8af7e128cc927fde26875`, UI after `1308bf2d251669575669d70945032cd0b076e37e`, Chat baseline `38480a771ff13d8163a3a68a59cdea273454df9e`, Chat after `c426e7057d53e3948c8d849ff5cf86b574953fee`, Permissions baseline `54ba0f27d34baa44b064db63c346c4ce86916097`, and Permissions after `6d5d28fe1d4778e5e3bef97f6a6b652f56fac58d`. All share the frozen non-Markdown product/test/tool tree (4,927 paths; canonical SHA-256 `0e72504b9dc429f0ae6ff36df2ee07bd95dc3eae46761681c5c8a4a1aba8ec1d`). The after inputs project the `.md` documents from the frozen after snapshot onto that common tree; they do not claim the original ticket07 candidate manifests were identical. Evaluator-only materials were excluded from coder-readable inputs. Blinding was instructional, not a physical access boundary around shared git objects.

Each baseline/after pair used the same task-specific input and acceptance tests. For UI, the missing optional SettingsSection action failed on both frozen inputs; adding the requested action made both candidates pass. For Chat and Permissions, the same fault overlay failed on both sides, and restoring the source behavior made both sides pass. Chat checks covered pending duplicate rejection and allowing a subsequent turn. Permissions checks covered visibility filtering before pagination, count, and invisible-row leakage. The independent fixture review passed. Input and origin manifests preserve their distinct provenance and hashes in the archive.

## Sessions and validation

Sessions ran serially in this order: UI baseline, UI after, Chat baseline, Chat after, Permissions baseline, Permissions after. The frozen criteria capped each at 30 minutes. Recorded coder execution intervals were 60s, 45s, 48s, 50s, 37s, and 26s respectively. Parent-observed outer bounds were available for Permissions (62s and 69s); for the first four, a freeze-to-final-observation batch upper bound was 549.23s. These records support that all six finished within the limit, but do not establish hard timeout enforcement or exact outer dispatch-to-final duration for each of the first four.

| Session | Focused result after implementation | Narrow static check | Patch SHA-256 | Independent review |
| --- | --- | --- | --- | --- |
| UI baseline | 2 passed | ESLint, Prettier, diff check passed | `ff22eb4969c2ae8a33794676733073344bb0301186c32fd09c3fc3ba34e41ca3` | Pass |
| UI after | 2 passed | ESLint and diff check passed | `f4a8ab0a9a271164750993107b0b41f883a99b0586b82df4f11054b32137dafd` | Pass; non-blocking note that a `0` ReactNode action is omitted by truthiness rendering |
| Chat baseline | 1 passed | ESLint and diff check passed | `0689f53ee3907a0b5e5f64a89f0451c110e954f74fb9295ad133bae010f436ff` | Pass |

| Chat after | 1 passed | ESLint passed | `f2c50d3625cf9c7fe9fafb90746b6f88d12e9d3f57d28d136858b0b8813b7732` | Pass |
| Permissions baseline | 1 passed, 9 deselected | Ruff and diff check passed | `72856e551cb59a49feb8764befd581d452d30a0e54406e3fd8f6d5151373b5d9` | Pass |
| Permissions after | 1 passed, 9 deselected | Ruff and diff check passed | `72856e551cb59a49feb8764befd581d452d30a0e54406e3fd8f6d5151373b5d9` | Pass |

The Chat-baseline red run fails at the public gate assertion before it reaches the controller duplicate-path assertion; the green run verifies duplicate rejection and next-turn behavior. This is a non-blocking test-boundary limitation.

Each patch changes only its intended source file. The corrected archive audit records exact candidate root, input commit, changed path, base blob, patch SHA-256, and resulting source SHA-256. The wrong-working-directory diffs found during packaging are preserved under `superseded/` as explicitly invalid audit artifacts; they are not candidate patches. Independent reviewers inspected the actual candidate trees; the corrected chat-after and both Permissions patch/source hashes received supplemental review.

## Reproduction

The portable archive is `dev-log/disclosure-dual-track/ticket08/ticket08-clean-restore-20261009.tar.gz`, SHA-256 `9ba23c1e51c7b075be4823c04ad573843997c525851f40e76e75e1ecf81616b0`; the identical external copy is `/tmp/ticket08-clean-restore-20261009.tar.gz`. Its 135 manifest entries were verified against file bytes and SHA-256. Clean restoration reconstructed all six parentless inputs, applied each candidate patch to its input, verified the one-file changed-path boundary and resulting source hashes, and reran the focused checks successfully. The recomputation record contains six restores with no failures. Raw session transcripts, commands, test/static outputs, reviews, fixture checks, manifests, patches, and superseded archive correction records are included.

Timing, evaluator-material exclusion, and instructional-blinding limits are retained in the audit records. This report records the practical subgate only; the ticket07 reading and cost gates remain as reported in [ticket 07 results](disclosure-dual-track-ticket07-results-2026-10-08.md).
