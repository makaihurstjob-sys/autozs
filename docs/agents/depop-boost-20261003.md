# Depop boost prevention checkpoint

Continues d81b6d8 in this isolated checkout. Fresh blank create-form inspection found the boost section identified by its exact h2 and one input[type=checkbox][data-testid=switch]. The new helper disables a checked switch and re-reads after rerender; missing, ambiguous or uncertain controls block publication. The submission guard rechecks opt-out both before arming and immediately before replaying Post.

Validation: all nine Depop/background Node test files passed, including nine boost cases and six submission cases. Live helper on the blank form returned before=false, after=false, verified=true. Live on-to-off transition remains untested; no listing was submitted or draft saved. API health ok; job2 completed and jobs3-8 queued at zero attempts.

Integration review: operational HEAD remains e12bb47, the base for the success-page repair. No operational extension files are modified. Combined changes remain isolated pending serial integration and controlled extension reload with scheduler disabled. Preserve unrelated operational context/board/database changes. No other publication is authorized.

## Integrated and loaded
Operational commits 3777854 and 62e433e integrate the success-page and boost safeguards. All nine Depop/background Node test files pass on the combined operational tree; combined diff check passes. Reloaded the identified AutoZS Source Capture extension ainpidpkelkbggebjijlcmmdcdgoggpg. After reload its depop-fill.js SHA256 equals the repository file (c45cb74e621138070a6a0b0b8177e74209588577388c459d41a545a14c6928a6); both repair functions are present. Executed the packaged script on the blank create form (no job parameters), and verified its loaded marker with no error status. Scheduler storage and pending-publication storage are absent; enabled===true guard therefore prevents job claims. No scheduler settings changed.

API health returned ok. Jobs1/2 completed; jobs3-8 queued with zero attempts. No Post or Save draft action performed. Full end-to-end confirmation on a new publication and live boost on-to-off transition remain untested. Further publication or unattended scheduling needs separate owner authorization; the authorized repair/integration work is complete.
