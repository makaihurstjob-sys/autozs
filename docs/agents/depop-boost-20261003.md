# Depop boost prevention checkpoint

Continues d81b6d8 in this isolated checkout. Fresh blank create-form inspection found the boost section identified by its exact h2 and one input[type=checkbox][data-testid=switch]. The new helper disables a checked switch and re-reads after rerender; missing, ambiguous or uncertain controls block publication. The submission guard rechecks opt-out both before arming and immediately before replaying Post.

Validation: all nine Depop/background Node test files passed, including nine boost cases and six submission cases. Live helper on the blank form returned before=false, after=false, verified=true. Live on-to-off transition remains untested; no listing was submitted or draft saved. API health ok; job2 completed and jobs3-8 queued at zero attempts.

Integration review: operational HEAD remains e12bb47, the base for the success-page repair. No operational extension files are modified. Combined changes remain isolated pending serial integration and controlled extension reload with scheduler disabled. Preserve unrelated operational context/board/database changes. No other publication is authorized.
