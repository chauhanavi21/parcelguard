# ParcelGuard

[![Verify portfolio](https://github.com/chauhanavi21/parcelguard/actions/workflows/verify.yml/badge.svg)](https://github.com/chauhanavi21/parcelguard/actions/workflows/verify.yml)

An independent **idempotency and delivery failure lab**, inspired by public engineering guidance. Working Python backend, analytics, failure cases, reproducible evidence and an accessible animated interface.

**[Open interactive demo](https://chauhanavi21.github.io/parcelguard/) | [Watch the walkthrough](https://chauhanavi21.github.io/parcelguard/watch.html)**

![ParcelGuard overview](parcelguard/docs/overview.png)

Run locally with Python 3.11+: `python parcelguard/server.py`. No runtime install or build step. The [application README](parcelguard/README.md) covers controls and measured findings. See the [recruiter guide](RECRUITER_GUIDE.md) for a quick technical review and the [research/design](parcelguard/docs/RESEARCH_AND_DESIGN.md) for source-to-code decisions.

The live demo runs the existing Python logic in your browser. Each tab is isolated and data resets on reload. Its first load downloads the Python runtime; it does not host the Python HTTP server. [Execution modes and validation limits](parcelguard/docs/RELEASE.md) explain the boundary, accessibility audit, mobile lab results, historical data and recording.

```powershell
python parcelguard/verify.py
python tools/package.py
python tools/package.py --check
```

GitHub Actions runs core/HTTP tests on Windows and Ubuntu, browser workflows in Chromium/Firefox/WebKit, accessibility and mobile lab checks, historical-data validation, and the Pages build. Deployment waits for validation and source packaging. [View actual CI runs](https://github.com/chauhanavi21/parcelguard/actions).

This is a portfolio prototype, with no company endorsement, affiliation, or implied hiring outcome.
