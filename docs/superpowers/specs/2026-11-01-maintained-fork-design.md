# Maintained fork and Mealie 3.30 compatibility

User-authorized scope: implement the compatibility fix, then publish an independently maintained fork with original attribution. Existing public fork: nosuntoday/mealie-mcp-server. Preserve Robert Diao's MIT license and upstream Git history. No production rollout or database migration is included.

Approach: keep the existing Python/FastMCP API and incorporate the already tested hardening patch; add explicit durationSeconds and weekly endDate handling. Waiting for upstream does not meet the request; replacing the connector would unnecessarily discard established behavior. No new runtime dependencies or service.

Recipe step duration: preserve integer seconds through input, model conversion and replacement payloads. Support Mealie's null/zero clearing and whole-number JSON floats; reject booleans, fractions, strings, negatives and overflow. Omitted steps remain untouched; supplied step lists replace the list and must carry fields to preserve.

Weekly plans: optional end_date on creation (single/bulk), endDate at the HTTP boundary, exactly six days after the start. Updates preserve omitted end dates, validate the merged date range, and allow explicit clearing. Old single-day payloads remain unchanged.

Publication: release 0.2.0 from the existing fork after offline tests, lint, package/build validation, independent review and redacted secret scans. Clearly describe differences, non-affiliation and limits of compatibility evidence. No private server configuration, data or history enters this fork. Keep existing contribution branches intact.
