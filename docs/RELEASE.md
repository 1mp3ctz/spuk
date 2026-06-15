# Spuk Release Runbook

How to cut a downloadable release that builds **both** the macOS `.app` and the
Windows `.exe` automatically in the cloud — no Windows machine required.

## One-time setup

- Ensure `.github/workflows/release.yml` is committed on `main`.
- The workflow uses the built-in `GITHUB_TOKEN` (no secrets to configure).

## Cut a release

From the repo root, on `main`, with everything committed:

```bash
# 1. Make sure main is clean and pushed
git status
git push origin main

# 2. Pick the next version and tag it (match pyproject.toml version)
git tag v0.1.0
git push origin v0.1.0
```

Pushing the `v*` tag triggers the workflow. It will:

1. Build `Spuk.app` on a macOS runner → `Spuk-macos.zip`.
2. Build `Spuk\Spuk.exe` on a Windows runner → `Spuk-windows.zip`.
3. Create a **GitHub Release** for the tag and attach both zips.

Watch progress in the **Actions** tab on GitHub. When the `release` job is green,
the downloads are live at:

```
https://github.com/1mp3ctz/spuk/releases/latest
```

### Manual run (no release, just test the builds)

Actions tab → **Release Spuk** → **Run workflow**. This builds and uploads the zips
as **build artifacts** (downloadable from the run page) but does **not** publish a
Release — handy for verifying a build before tagging.

### Re-cutting / fixing a bad release

```bash
git tag -d v0.1.0
git push origin :refs/tags/v0.1.0   # delete the remote tag
# (also delete the Release in the GitHub UI if one was published)
git tag v0.1.0
git push origin v0.1.0
```

For a real new version, bump: `v0.1.1`, `v0.2.0`, etc. (and update `version` in
`pyproject.toml` to match).

## How your family then downloads

Send them: `https://github.com/1mp3ctz/spuk/releases/latest` — open it, scroll to
**Assets**, click `Spuk-macos.zip` (Mac) or `Spuk-windows.zip` (Windows), then follow
the README's **Download & Install** steps.

## ⚠️ The private-repo gotcha (read before sending links)

The repo is currently **private**, so the Releases page and download links are **not
visible** to anyone not signed in with access. Options:

- **Easiest for non-technical parents — make the repo public.** Releases and links
  then work for everyone, no login. The code contains no secrets (post-processing
  keys are off by default and never committed). Recommended.
- **Keep it private + invite their GitHub accounts** (repo → Settings → Collaborators).
  They must be signed in to GitHub to download — an extra hurdle.
- **Keep it private + send the files directly** (download the zips yourself, share via
  iCloud/Drive/WeTransfer). Private-release asset URLs are tokenized and expire, so
  send the actual file, not the link.

## What CI can and can't verify

- ✅ Confirms the app **builds** and bundles its native libs on real macOS + Windows.
- ❌ Does **not** download the ~480 MB Whisper model, so it can't prove end-to-end
  transcription — that still needs a human on a clean machine (especially Windows).
- Output is **unsigned** (no Apple/Windows certs) — expected; users do the one-time
  right-click→Open / Run-anyway.
