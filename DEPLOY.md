# Deploying to Netlify

## Read this before you share the URL with anyone

**The site currently ships invented numbers.** The pipeline has never had
access to real DOL filings (see README.md), so `web/index.html` generates
synthetic figures from hardcoded employer profiles. A purple banner at the
top of the page says so, unmissably.

Deploying it is fine — you need a URL to test against, and Netlify sites
are effectively unlisted until you hand out the link. **Handing that link
to job seekers is not fine** until real data is loaded. These are real
company names attached to made-up filing counts; someone acting on them
would be acting on fiction, and that is exactly the failure the whole
"honesty requirements" section of the brief exists to prevent.

Two rules until Phase 2 is done:

1. Do not remove the demo banner.
2. Do not post the link anywhere public — DMs to people who know it's a
   preview are fine.

---

## First deploy (~10 minutes, one time)

1. Go to [app.netlify.com](https://app.netlify.com) → **Add new site** →
   **Import an existing project** → **GitHub**.
2. Authorize Netlify for the `alenparmar-collab` account if prompted, then
   pick **Sales-tool**.
3. Netlify reads `netlify.toml` and fills in the settings itself:
   - Publish directory: `web`
   - Build command: none (static HTML, nothing to build)

   Don't override these.
4. **Deploy site.**

You get a URL like `random-words-123.netlify.app`. To change it:
**Site configuration → General → Site details → Change site name.**
Something like `sponsorship-reality-check` gives you
`sponsorship-reality-check.netlify.app` free, no domain purchase.

Every push to `main` redeploys automatically from then on.

## Where the emails go

The email field is wired to **Netlify Forms** — no third-party account, no
API key. Netlify detects the `data-netlify="true"` form in `index.html` at
deploy time and starts capturing.

Submissions land in **Site configuration → Forms → early-access**. Each one
carries the email plus the role bucket and metro the person had selected,
which tells you what they were actually looking for.

To get notified: **Forms → Form notifications → Add notification → Email
notification**, pointed at your inbox.

Free tier is **100 submissions/month**. If you clear that, the tool is
working and Netlify's paid tier is not going to be your bottleneck.

Spam is handled by a honeypot field (`bot-field`) — invisible to people,
usually filled in by bots, silently dropped.

### Verifying capture actually works

Form submissions only work on the deployed Netlify site. On the artifact
preview or a local `file://` open, the POST fails and the page says
"Preview only" instead of confirming. That's expected, not a bug. After
the first deploy, submit a test address on the live URL and confirm it
shows up under Forms.

## Going live for real (the sequence)

1. Run the pipeline somewhere with real internet (`python run_pipeline.py`).
2. Do the two curation passes — `config/employer_aliases.yaml` from
   `top_500_employers.csv`, `config/role_taxonomy.yaml` from
   `unmatched_titles_top_100.csv`.
3. Build the static aggregate index from the real output and drop it in
   `web/data/`.
4. Replace the demo data block in `web/index.html` with a fetch of that
   index, and delete the demo banner.
5. Add a privacy policy page — you're collecting email addresses.
6. *Then* share the link.

Steps 3 and 4 are code and are mine to do. Steps 1, 2, 5 need you.
