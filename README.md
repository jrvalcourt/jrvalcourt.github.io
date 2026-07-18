# jamesvalcourt.com

Source for https://jrvalcourt.github.io/jamesvalcourt/. Static HTML assembled
from `src/` by `scripts/build.py` -- no JS framework, no runtime dependencies
beyond Python's standard library.

## Layout

- `src/partials/` -- shared `<head>`, header/nav, and footer, injected into every page.
- `src/pages/` -- one file per site page, mirrors the output URL 1:1 (e.g. `src/pages/fun/money.html` -> `/fun/money/`).
- `src/blog/posts/` -- one file per blog post, named `YYYY-MM-DD-slug.html`.
- `src/static/` -- copied byte-for-byte into the output (CSS, images, PDFs, the standalone `jcraigvintner` joke page).
- `dist/` -- generated output. **Gitignored.** Never hand-edited; regenerate any time with `python scripts/build.py`.

Every page/post source file starts with a small front-matter block:

```
---
title: Page Title
description: Meta description text
nav: fun
main_class: generic-page page-whatever
---
<div class="container">
  ...page content...
</div>
```

`nav` picks which header link highlights as active (`home`, `cv`, `writing`,
`blog`, `systematic`, `fun`, `contact`, or blank for none). Blog posts only
need a `title:` -- `description` defaults to `Blog post: {title}`, and the
summary excerpt on `/blog/` is auto-generated (add an `excerpt:` field to
override it). If two posts land on the same date, add an `order: N` field
(lower sorts first) to break the tie -- see the three 2017-02-06 posts for an
example.

## Adding a new blog post

1. Create `src/blog/posts/YYYY-MM-DD-your-slug.html`:
   ```
   ---
   title: My New Post Title
   ---
   <p>First paragraph...</p>
   ```
2. `python scripts/build.py` -- regenerates `dist/`, including the new post and an updated `/blog/` index (newest first).
3. Preview: start the `valcourt-site` launch config (or `cd dist && python3 -m http.server 8420`) and check it locally.
4. `python scripts/deploy.py` when you're happy -- publishes to production.
5. Commit the new source file whenever you like -- committing to `main` never auto-deploys; only step 4 does.

## Build vs. deploy

- `python scripts/build.py` -- pure `src/` -> `dist/`. Zero git or network side effects. Safe to run constantly while previewing.
- `python scripts/deploy.py` -- rebuilds with the production path prefix (`/jamesvalcourt`) baked in, then pushes `dist/` to the `gh-pages` branch via a git worktree at `.deploy/` (gitignored). This is the only command that ever touches git remotes.

## One-time setup (already done, documented for posterity)

After the very first successful `python scripts/deploy.py` run creates the
`gh-pages` branch, the repo's GitHub Pages source needs to be pointed at it:

**Settings -> Pages -> Source: Deploy from a branch -> `gh-pages` / (root)**

(equivalent: `gh api -X PUT repos/jrvalcourt/jamesvalcourt/pages -f source[branch]=gh-pages -f 'source[path]=/'`)

Before that, Pages was serving directly from `main`'s root -- which is why
`main` used to be the deploy artifact itself. It no longer is; `main` is pure
source now, and nothing GitHub needs is only "on this laptop": `src/` and
`scripts/` are committed normally, `dist/` is 100% reproducible from them, and
the published output also lives in this same repo on the `gh-pages` branch.
