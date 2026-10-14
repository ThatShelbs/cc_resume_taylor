# Resume best practices (evidence-based)

Researched once and cached here so `generate_resume.py` doesn't have to re-research
best practices (or spend tokens/time on it) on every run. Only claims traceable to a
named study, a described methodology, or a company's own reported platform data are
included. A first pass of web search turned up dozens of "resumes with quantified
achievements get 3.2x more callbacks (Harvard Business Review)"-style statistics that
are repeated verbatim across SEO content-mill sites with no link to an actual HBR
study — those are excluded. If a number below can't be traced to a source, it isn't
here.

## Sources

- **TheLadders Eye-Tracking Study** (2012, updated 2018) — eye-tracking of 30
  professional recruiters over a 10-week period reviewing resumes.
  [recruiter.com summary](https://www.recruiter.com/recruiting/theladders-reveals-research-reporting-that-resumes-spend-six-seconds-with-a-recruiter/),
  [2018 update via PRNewswire](https://www.prnewswire.com/news-releases/ladders-updates-popular-recruiter-eye-tracking-study-with-new-key-insights-on-how-job-seekers-can-improve-their-resumes-300744217.html)
- **ResumeGo field experiments** — real fictitious resumes submitted to real job
  postings on Indeed/ZipRecruiter/Glassdoor, with actual callback rates measured.
  [One vs. two-page resume study, n=7,712](https://www.resumego.net/research/one-or-two-page-resumes/),
  [Cover letter study, n=7,287, Jul 2019–Jan 2020](https://www.resumego.net/research/cover-letters/),
  [Employment gaps study](https://www.resumego.net/research/resume-employment-gaps/)
- **Jobscan** — ATS optimization platform; claims below are their reported product/usage
  data, not independent academic research, and are treated accordingly.
  [State of the Job Search report / ATS resume guide](https://www.jobscan.co/blog/ats-resume/),
  [ATS formatting mistakes](https://www.jobscan.co/blog/ats-formatting-mistakes/),
  [Resume tables/columns and ATS parsing](https://www.jobscan.co/blog/resume-tables-columns-ats/)
- **Ge, Knox, et al., "Algorithmic Writing Assistance on Jobseekers' Resumes Increases
  Hires"** — field experiment (RCT) in an online labor market, ~half a million
  jobseekers, randomized to receive AI writing assistance or not; outcome was actual
  hire probability. [arXiv:2301.08083](https://arxiv.org/abs/2301.08083)
- **CareerBuilder recruiter surveys** — large annual surveys of hiring
  managers/recruiters on resume preferences (opinion/preference data, not outcome data).

## What the evidence supports

### Content and substance
- Quantify accomplishments (dollars, percentages, counts, time saved) wherever the
  underlying fact supports it. The evidence here is indirect: the RCT on AI writing
  assistance found that clearer, better-written resumes raised hire probability, with no
  drop in employer satisfaction. It tested writing clarity, not quantification itself, so
  treat "quantify" as sound practice, not a measured effect size. (Ge et al.,
  arXiv:2301.08083)
- Explaining an employment gap performs better than leaving it unaddressed.
  (ResumeGo employment gaps study)
- Don't pad with unquantified duty-lists — the eye-tracking research found recruiters
  spend the majority of their initial scan on name, titles, dates, and education, then
  scan for keywords; they are not reading dense paragraphs closely on a first pass.
  (TheLadders eye-tracking study)

### Language and phrasing
- Lead bullets with strong, specific action verbs ("led," "built," "reduced") rather
  than passive/duty phrasing ("was responsible for"). Recruiter surveys consistently
  report a preference for direct, active language over passive descriptions.
  (CareerBuilder recruiter surveys)

### Tailoring to the specific posting
- Include the exact job title language from the posting where it's an honest match —
  ATS keyword filters are used near-universally, and job-title/keyword alignment is
  the single factor ATS platforms report most strongly correlating with getting
  surfaced to a recruiter. (Jobscan)
- Tailoring the application to the specific role (not just the resume, but supporting
  materials like a cover letter) measurably raises callback rates in real submitted-
  application experiments. (ResumeGo cover letter study)
- Mirror the posting's own terminology for skills/tools the candidate genuinely has.
  Exact phrasing still carries the most weight in keyword filters.

### How screening works in 2026 (vendor and industry reports; not independent studies)
- Major platforms (Workday, iCIMS, Greenhouse and others) layer NLP/semantic or LLM
  matching on top of exact-match scoring, so "led cross-functional teams" can earn partial
  credit for "team leadership." Exact terms are still safest; synonyms are a bonus.
- Modern parsers build a candidate profile from skills, roles, and responsibilities and
  check whether a claimed skill is demonstrated in the work history. A skill that appears
  only in a skills list and in no bullet is weak evidence.
- Recency and title trajectory matter. Relevant skills in the most recent roles count for
  more than the same skills ten years back.
- Most tools shortlist or rank; a human still makes the final call. Keyword stuffing and
  hidden text (white-on-white, tiny fonts) are detected and penalized.
- Write acronyms with their spelled-out form once (e.g. "Search Engine Optimization (SEO)")
  so either form matches.
- Sources: [Jobscan on AI detection](https://www.jobscan.co/blog/can-ats-detect-ai-resume/),
  [AI resume screening in 2026](https://atsverification.com/blog/ai-resume-screening-2026/),
  [How ATS systems work in 2026](https://www.atscvchecker.pro/blog/how-ats-systems-work-2026/).

### Avoiding AI-writing tells
- ATS software rarely flags AI-written text. The risk is a human recruiter noticing
  generic, uniform prose (buzzword verbs, every bullet the same length and shape, a
  metric tacked onto every line, em-dash-heavy sentences, rhetorical triads).
- Fix it with specifics, the candidate's own vocabulary, varied bullet length and
  structure, and plain verbs. The pipeline's `guards_quality.py` flags the common tells.
- Keep the file clean too: no zero-width characters, and document properties that name
  the candidate, not a library default.

### Structure and length
- One page is the safer default for less than ~10 years of experience; two pages is
  standard and performs at least as well for candidates with 10+ years of experience —
  do not artificially compress a long career into one page at the cost of cutting
  strong, relevant material. (ResumeGo one-vs-two-page study, n=7,712)
- Put the highest-value information first: name, current title, most recent
  employer/title/dates, and education are what get the most attention in the initial
  scan — don't bury the strongest, most relevant qualification below weaker material.
  (TheLadders eye-tracking study)
- Skills section length: no traceable study was found pinning an exact "optimal"
  count. Search results here were dominated by the same unsourced content-mill
  statistics called out above (e.g. a specific "10-15 skills" or "60% hard / 40% soft"
  split attributed to no actual study). The generator targets ~20 skills, drawn from a
  mix of tools, soft/leadership skills, methodologies, and discipline subfields,
  selected for relevance to the specific posting — a reasonable default in the absence
  of real evidence for a different number, not a research-backed figure.

### ATS-safe formatting (technical parsing mechanics, not a "study" per se — this is
how ATS text-extraction actually works)
- Single-column, left-to-right reading order. Tables and multi-column layouts cause
  ATS parsers to scramble text order because they read linearly.
- No headers/footers for content that must be parsed (contact info, section content) —
  most ATS systems skip the header/footer layer entirely.
- No text boxes, icons, or graphics for content — these live outside the normal text
  flow and are often invisible to parsers.
- Standard section headings ("Experience," "Education," "Skills") rather than creative
  labels — ATS and recruiters both pattern-match on conventional headings.
- Standard fonts (e.g., Calibri, Arial, Times New Roman), simple bullet characters, and
  a .docx or text-extractable PDF rather than a flattened image/design-tool export.

## How the generator uses this

The tailoring rules the model actually sees live in
`.claude/skills/resume-tailoring/SKILL.md`; this file is the sourced background for them.
Change behavior in the skill, and update this file when the evidence changes.
