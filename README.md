# AccessPath — AccessCheck (Hackathon MVP)

**Problem:** People with mobility limitations cannot reliably know whether a public building entrance is currently accessible. A ramp may be blocked or an entrance may have stairs without a known step-free alternative.

**Solution:** A focused, map-first community reporting prototype. **Report → Check → Verify → Prepare a complaint draft**.

## MVP features (only 3 core capabilities)
1. **Report a barrier** — upload a photo, describe the barrier, choose category/place type, and pin the entrance. Optional OpenAI vision gives a *preliminary* image review, model confidence percentage, and OCR transcription of readable signs/text. When confidence is at least 70% and the reported category visually matches, the report earns 10 provisional XP. The result is automatically saved with the report.
2. **Check an entrance** — view the latest reported condition, image, date/status, and location on an interactive Baku map.
3. **Contribute evidence / prepare ASAN Müraciət draft** — upload an after-photo for human review, record a demo confirmation, and generate a structured Azerbaijani complaint draft that the user can copy and submit **manually** on the official ASAN platform.

The ASAN draft is a **handoff**, not an integration: **no API, automatic submission, or government affiliation is claimed**. The complaint is not sent by this app. Users must review the text and attach photos themselves.

## Run on Windows 11 (PowerShell)

Install Python 3.10+ first. Unzip and open the extracted `accesspath-final` folder in VS Code.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

Open **http://127.0.0.1:8000** (API docs: http://127.0.0.1:8000/docs).

If PowerShell blocks activation, run `.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000` instead.

## Optional AI vision

```powershell
$env:OPENAI_API_KEY="YOUR_KEY"
python -m uvicorn main:app --reload --port 8000
```

Without an API key, photo upload still works; report status remains `pending_review`, confidence shows `—%`, OCR is unavailable and XP stays 0. No fabricated AI verdicts. Optional vision calls require internet access and may incur API charges.

## Demo scenario (fictional)

The map starts with four **fictional** accessibility reports around central Baku: blocked clinic ramp, university steps, missing curb ramp at a bus stop, and uneven sidewalk. The pins are **not real verified incidents** and must not be presented as such. No photographs are prefilled for these fictional examples. Create your own report using a consented or appropriately licensed test image.

Suggested judge demo: open the clinic example → explain why outdated entrance information matters → click **Prepare ASAN draft** → copy draft → show official handoff → create a new report and upload a second photo as *pending independent review*. Do not claim a repair was automatically confirmed.

## Future development (NOT in MVP)

- Verified-user identities and anti-spam/anti-duplicate controls
- Official ASAN Müraciət API integration (only with permission and published API)
- Personalised step-free routing
- Real-time entrance sensors, institution-managed status
- Priority ranking and municipal impact analytics
- AI before/after comparisons with human oversight
- Accessible multilingual voice interface

## Architecture

FastAPI + SQLite + vanilla HTML/CSS/JavaScript + Leaflet/OpenStreetMap. Single origin: backend serves frontend, avoiding CORS setup. The SQLite database is created at `backend/data/accesspath.db` on first run. Uploaded images go to `backend/data/uploads/`.

## Percentage and XP rules

The displayed percentage is **model confidence in a visual match**, NOT a measured accessibility score or a guaranteed correctness rate. OCR extracts only text visible to the vision model (e.g. signage); it cannot prove where the photo was taken. Provisional XP is awarded only when an AI review returns a matching barrier at confidence >=70%. There is no account system or anti-fraud yet, so XP is a demo total across reports, not a real personal balance.

## Limitations

- Prototype only. No login, identity verification, moderation, rate limiting, or production security.
- Community confirmations are unverified and can be repeated; counts are illustrative, not trusted evidence.
- New after-photos do **not** automatically change the status to accessible.
- AI review cannot establish authenticity, location, safety, or the existence of an alternative entrance.
- Map tiles and Google Fonts require internet; app's list and backend can run locally.
- Uploaded photos are publicly served from `/uploads`; do not use sensitive photos or personal information in the demo.

## References

- ASAN Müraciət: https://asanmuraciet.gov.az/
- Official ASAN info: https://vxsida.gov.az/az/amis
- OpenStreetMap: https://www.openstreetmap.org/copyright
- Leaflet: https://leafletjs.com/
- FastAPI: https://fastapi.tiangolo.com/


## One-photo immediate XP flow
Choose a location on the map and upload one image. If AI finds a likely accessibility barrier, the report is saved and a **+10 XP** result appears immediately. There is **no verification-photo step** in this MVP user journey. No confidence percentage is displayed. If AI is unavailable, the report is saved as pending and XP remains zero. AI cannot prove photo authenticity or location. ASAN draft remains available from report details; submission is manual.

## Map location selection (updated)
- Click **Report a Barrier**. Tap the mini-map to select the barrier's location, or choose **Use My Location** (browser permission required; localhost or HTTPS).
- Alternatively, tap anywhere on the main map to select the location and open the report form automatically.
- Location selection is mandatory; the app no longer silently assigns a default Baku location.
- Upload **one photo** and press **Analyze & save photo**. The AI review may award provisional XP if an accessibility barrier is likely visible. No verification photo or confidence percentage is required from the user.
- Map tiles and location selection require internet access to load Leaflet/OpenStreetMap; geolocation is optional.


### Location options
In Report a Barrier, use **Use My Location** (GPS permission), **Choose on Map** (tap a map point), or **Enter Coordinates** (latitude/longitude; works even if map tiles cannot load). A location must be selected before submission. The AI upload still requires internet and a configured API key.


## Instant AI verification and XP
On one-photo upload, the backend calls the configured vision model, detects a **visible possible** physical barrier, extracts any clearly readable text (OCR), and stores the report. A sufficiently strong AI visual match receives +10 provisional XP immediately. No second verification image or visible confidence percentage is required. Exact image re-uploads and same-category reports within ~25 m are flagged as possible duplicates and earn 0 XP pending review. This is a conservative heuristic and may flag legitimate separate barriers. AI cannot authenticate photo origin, location or date. Without an OpenAI API key or when the model fails, reports remain pending with 0 XP. The MVP does not have authenticated user accounts, so XP is an aggregate demo reward, not a secure per-user wallet.
