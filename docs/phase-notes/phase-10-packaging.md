# Phase 10: Packaging (Windows)

Making StudyMate usable by someone who isn't its developer: two PowerShell commands set it
up and start it, one server on one port serves both the app and its API, and the README
explains what to install and what to do when something goes wrong. No setting default
changed, and the phase used 0 Gemini calls.

## What was built

| Step | Commit | What |
|---|---|---|
| 1 | `81e0697` | `backend/app/web.py`: one site with the API under `/api` and the built frontend at `/`; fix for the upload-size check under the mount |
| 2 | `a21f77f` | `scripts/setup.ps1` (checks, venv, packages, `.env` only if missing, frontend build) and `scripts/start.ps1` (checks, start, open the browser) |
| 3 | `e4bcaa7` | `.env.example` lists every setting at its default (tested); README Quick start (Windows), Troubleshooting, sample-document licences |

## How the pieces connect

**For users:**

```
scripts\setup.ps1  (once)                     scripts\start.ps1  (each time)
  check Python 3.11 and Node 22.12+             check: .venv, frontend\dist, backend\.env, free port
  backend\.venv + pip install                   cd backend; uvicorn app.web:site --host 127.0.0.1 --port 8000
  backend\.env from .env.example, if missing    open the browser once /api/health answers
  npm ci + npm run build -> frontend\dist

app.web:site  (one FastAPI app, one port)
  /api/...  -> the existing API (app.main:app), mounted
  /         -> frontend\dist (StaticFiles, index.html), or a "run setup" page if not built
  startup   -> the API's own lifespan: tables, foreign-key check, optional cleanup
```

The browser calls `/api/...` exactly as in development, so the frontend code didn't change and
there is still no CORS: everything comes from the same origin.

**For developers (unchanged):** `uvicorn app.main:app --reload` serves the API at the root,
and `npm run dev` serves the frontend on port 5173 with a Vite proxy that turns `/api/...` into
`/...`. A test checks that `app.main:app` still has no `/api` prefix.

**Why the site runs the API's startup itself:** an app mounted inside another one doesn't run
its own startup steps. Without passing the API's `lifespan` to the site, the tables, the
foreign-key check and the optional cleanup would silently not run.

## Design tradeoffs

- **One server instead of two.** Users get one port and one window; the price is a small
  `web.py` and the mount subtlety below. Development keeps the two-window setup with hot
  reload.
- **PowerShell scripts instead of Docker or an installer.** The target user is a student on
  Windows; Docker Desktop is a large extra install, and an installer is far more to build and
  explain. The scripts are short, readable and safe to re-run.
- **`-ExecutionPolicy Bypass` per command.** It applies to that one PowerShell process only,
  so the user never changes a system-wide security setting.
- **`.env` created only if missing.** Setup checks `Test-Path` first, because `Copy-Item`
  itself would overwrite the file and with it the user's key.
- **`npm ci` instead of `npm install`.** It installs exactly the versions in
  `package-lock.json` and never changes that file. It reinstalls `node_modules` each time, which
  is slower and fails with EPERM if `npm run dev` holds files open (now in Troubleshooting).
- **Node 22.12 or newer.** Vite builds with 20.19+, but the frontend tests (Vitest) need 22.12+;
  asking for 22.12 covers both with one simple rule.
- **Bound to 127.0.0.1.** StudyMate is a local single-user app with no login, so the server
  isn't reachable from other computers.
- **Scripts tested in a temporary copy, never on the real folder.** The copy contained only
  what git tracks (no `backend\data`, no `backend\.env`, no installs), so a script bug couldn't
  touch the real key or data.

## Bugs found and fixed

- **The early upload-size check stopped working under `/api`.** A small experiment showed that
  inside a mounted app, `request.url.path` is the full `/api/documents` and the mount prefix is
  in `root_path`. The middleware compared against `/documents`, so oversized uploads were only
  caught by the slower byte-count backstop. Fix: compare the path within the app (url path minus
  `root_path`). The test was made strict enough to tell the two apart (the upload folder
  dependency raises if the request ever reaches the endpoint) and was run with the old check put
  back: it fails, and passes with the fix.
- **A wrong comment in `setup.ps1`** claimed `Copy-Item` without `-Force` won't overwrite a
  file. It would; the `Test-Path` check is the real protection, and the comment now says so.
- **The developer README** said `Copy-Item .env.example .env`, which would overwrite an
  existing `.env` and its key. It now copies only if `.env` doesn't exist.

## Testing

- **Automated:** 423 backend tests (6 for the site, 4 for `.env.example`) and 178 frontend
  tests, all without Gemini calls. The site tests use temporary folders and databases and
  replace the API's database, vector store and upload folder, so no request can reach the real
  `backend\data`. The `.env.example` test checks the key is empty and every value equals the
  default in `config.py` (read from the code, not from the environment).
- **The scripts, in a temporary copy of the repository:**
  - Python hidden from `PATH`, then Node hidden: each stopped with its message, exit code 1,
    nothing created;
  - a full first setup: venv, packages, `.env` identical to the template, frontend built;
  - a second setup: everything reused, and the copy's `.env` (edited with a marker line)
    unchanged byte for byte;
  - start on a spare port with `-NoBrowser`: the page, its JavaScript and the API answered,
    with the copy's data kept inside the copy; a second start on the same port stopped with
    "already in use".
- **The real project** was checked untouched after each step: `backend\.env` not opened (only
  its timestamp checked), `backend\data` with the same files, sizes and times.

## Limitations

- **Windows only.** The scripts are PowerShell; macOS and Linux users follow the developer
  instructions.
- **Local and single-user.** No login, no HTTPS, bound to 127.0.0.1.
- **No installer, auto-start or Docker image.** The user runs `start.ps1` each time.
- **Python and Node must be installed by the user**, and the first start downloads the
  embedding model (about 130 MB).
- **The sample documents' sources and licences** are placeholders in the README for the owner
  to fill in.

## Interview questions

1. **Q: How does one server serve both the React app and the API, and why keep the `/api`
   prefix?**
   A: `app/web.py` makes a small FastAPI "site" that mounts the existing API app under `/api`
   and serves the built frontend (`frontend/dist`) at `/` with `StaticFiles`. The frontend
   already calls `/api/...` in development, where Vite's proxy strips the prefix; mounting the
   API at `/api` reproduces exactly that, so the frontend code didn't change. Everything comes
   from one origin, so there's still no CORS. The API is mounted first so `/api/...` can never be
   answered by the static files, and if the frontend isn't built, `/` shows a page saying to run
   setup instead of an error.

2. **Q: What broke when you mounted the API, and how did you prove the fix?**
   A: Two things needed care. First, a mounted app doesn't run its own startup, so I pass the
   API's `lifespan` to the site; a test runs the site's startup against a temporary database and
   checks the tables exist. Second, my upload-size middleware compared `request.url.path` with
   `/documents`, but under the mount the path is `/api/documents` and `/api` is in `root_path`, so
   it silently stopped firing. I confirmed that with a five-line experiment, then compared the
   path within the app instead. The test had to be strict: the byte-count backstop also answers
   413, so I made the upload-folder dependency raise if the endpoint is ever reached. With the old
   check patched back in, that test fails; with the fix, it passes.

3. **Q: How do your setup scripts protect the user's `.env` and data?**
   A: Setup creates `backend\.env` from the template only if it doesn't exist, checked with
   `Test-Path`; `Copy-Item` alone would overwrite it. It never reads or prints the file, and
   start only checks that it exists. Neither script mentions `backend\data`. The template itself
   has an empty key, and a test fails if it ever holds a value or drifts from the code's
   defaults. I also fixed the developer README, which used an unconditional `Copy-Item` that
   would have wiped a key.

4. **Q: How did you test install scripts without risking your own setup?**
   A: In a temporary copy containing only what git tracks: no `backend\data`, no `backend\.env`,
   no venv or `node_modules`. I hid Python and then Node from `PATH` to check the error
   messages, ran a full first setup, then a second one after putting a marker in the copy's
   `.env` and comparing checksums to prove it wasn't overwritten. I ran start on a spare port
   with `-NoBrowser` and checked the page, its JavaScript and the API, then a second start on the
   same port for the "in use" message. Afterwards I checked the real folder was untouched and
   deleted the copy.

5. **Q: Why not ship it with Docker?**
   A: For this audience it adds more than it removes. A student on Windows would need Docker
   Desktop (a large install, often with WSL), and they'd have to learn about volumes to keep
   their documents across restarts. Two short PowerShell scripts that check for Python and Node,
   install, build and start are easier to understand and to debug, and they keep the data in a
   plain folder the user can see. Docker would make sense for deploying StudyMate as a shared
   server, which would also need login and HTTPS, so it's listed as a limitation rather than
   done halfway.
