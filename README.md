# BrandCheck

Type a fashion brand name, press Enter, and get a viability report: trademark risk, domain availability, social handles, and name quality.

## Run

```bash
python3 server.py
```

Then open http://localhost:8765. Python 3.9+ only, no packages to install.

## Host it

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/pjcrisanti-90/brandcheck)

`render.yaml` sets up a free Render web service. Every push to `main` redeploys it. On the free plan the app sleeps after 15 minutes without visitors, so the first search after that takes about a minute.

Each visitor gets 20 checks per 10 minutes. Change `RATE_LIMIT` and `RATE_WINDOW` in Render's environment settings to adjust that. Identical searches are cached for 15 minutes and don't count against the limit.

## How it checks

| Area | Method | Reliability |
|---|---|---|
| Domains | Registry RDAP lookup (rdap.org), DNS fallback if the registry rate-limits | High |
| TikTok, YouTube, X, Pinterest | Public profile page | Good, but platforms change their pages |
| Instagram, Threads | Not checkable while logged out, so you get a direct link | Manual |
| Trademark conflicts | Offline check against ~250 major fashion and beauty brands (exact, misspelling, sound-alike, containment) | Screening only |
| Trademark strength | Generic → descriptive → suggestive → coined scale for clothing terms | Heuristic |
| Official registers | One-click links to USPTO, WIPO, EUIPO, UK IPO, and Google/Etsy for common-law use | You review these yourself |

The viability score is 60% trademark, 20% domains, and 20% handles. It is capped low when there's a high-risk conflict or the name is generic.

Customize it in `vetting.py`: add brands to `FAMOUS`, and add weak words to `GENERIC` or `DESCRIPTIVE`.

This is a screening tool, not legal advice. Have a trademark attorney run a clearance search before you launch.
