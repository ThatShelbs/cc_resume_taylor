"""Job search engine: pulls live postings from company career pages (ATS APIs first),
plus a light job-board sweep, then filters, scores and verifies them. No web-app code;
the app runs it as a subprocess (`python -m resume_taylor.search`)."""
