# Draft Importer recovery ? October 17, 2026

The reported 14 waiting captures were all Amazon products already handed off to Depop. The Depop importer pauses these products and deliberately removes unused eBay drafts. The generic capture queue interpreted absent eBay descriptions and unknown Amazon shipping as unfinished work, reopening the same successfully imported product indefinitely once dispatch was enabled.

The extension also filtered claims and runner ownership to Home Depot. Amazon capture/closure and stale-runner recognition now share the supported host allowlist. A single-flight dispatcher prevents simultaneous polls from opening duplicates. The backend excludes paused products with retained Depop variants from eBay capture repair; genuinely uncaptured phone drafts remain eligible. Unknown shipping remains unknown.

Operational changes: e21d89c, d91c52b, e2d5a11. Isolated branch fixes/draft-importer-amazon-20261017 retained.

Validation: six disposable API queue/channel/lease regressions pass in both isolated and integrated trees. Background runner tests cover Amazon routing, duplicate prevention and foreign host rejection; capture regression script passes. All operational feeds were idle before the standard AUTOZS stop/start. Live API health is OK, capture queue is zero, and the extension is enabled without an active capture runner. Scoped live dispatcher updates avoided reloading a saved Depop publication context; the same fix is in the persistent extension resource.

Zero queue means the 14 misleading repair entries were correctly excluded, not that 14 new products were imported in this repair. No purchase or marketplace publication was performed.
