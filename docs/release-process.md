# Release process (maintainers)

`.github/workflows/release.yml` prepares releases, but never publishes them.
Neither pushes to `main` nor tag pushes trigger it; the only trigger is a manual
`workflow_dispatch` on `main`. The workflow creates **drafts only** — no tags,
no published releases, no release assets. HACS only serves published GitHub
releases, so a workflow artifact or a draft never opts users into anything.

The final publication of a draft is a separate, explicitly approved step that
runs outside this workflow through the publication approval queue
(`draft_queue.py` on the operations side). See
[Publication (separate approval queue)](#publication-separate-approval-queue).

## Security model

- All inputs are explicit: version, existing tag, and a reviewed full commit
  SHA. The workflow never derives a version, bumps a manifest, or creates a tag.
- The only write-capable job (`prepare-draft`) runs in the protected
  **`release` environment** and therefore blocks until the required reviewer
  approves. Validation **fails closed** if that protection cannot be verified.
- The candidate commit is checked out as data only (`persist-credentials:
  false`); candidate code is never executed.
- All drafts are created with `--latest=false`; beta drafts additionally get
  `--prerelease`. A beta preparation can never displace the stable "Latest"
  release, and no draft is ever visible to HACS users.

## One-time repository setup (owner action)

Create the GitHub environment **`release`** in Settings → Environments:

1. Add **marcelloceschia** as a required reviewer (type `User`).
2. Enable **Prevent self-review**.
3. Disable **Allow administrators to bypass configured protection rules**.
4. Restrict deployment to the `main` branch.

The workflow's `validate` job reads the live environment configuration via the
GitHub API and requires `can_admins_bypass == false`, a `required_reviewers`
rule with `prevent_self_review == true`, and `marcelloceschia` among the user
reviewers. If any of that cannot be verified — including a missing environment
(404) or unreadable configuration (403) — the run fails closed. Merely naming
an environment in YAML is not an approval gate, and the workflow never creates
or mutates environment settings. Do not weaken the check to work around a 403;
fix the token/environment configuration instead.

Because self-review is prevented, a **different authorized maintainer must
dispatch** the workflow so Marcello can approve it. No extra token or
third-party approval action is needed. Keep Actions workflow changes subject to
code review/branch protection.

## Inputs

All three inputs are required; `scripts/validate_release.py` enforces the exact
formats before anything else happens:

| Input        | Rule                                                                 |
| ------------ | -------------------------------------------------------------------- |
| `version`    | `X.Y.Z` or `X.Y.Z-beta.N` with `N >= 1`; no leading zeros anywhere. |
| `tag`        | Must equal `v` + `version` exactly (e.g. `v1.2.3-beta.1`).          |
| `commit_sha` | Full lowercase 40-character commit SHA; branch/tag names rejected.   |

Malformed versions (`1.2`, `01.2.3`, `1.2.3-beta.0`, `1.2.3-rc.1`), a tag that
does not equal `v<version>`, a non-SHA ref such as `main`, or a manifest whose
`version` does not match the requested version all abort the run before the
candidate is checked out.

## Per-candidate procedure

1. **Review the exact commit.** Confirm CI (including HACS and Hassfest) is
   green on the reviewed commit and that
   `custom_components/sec_energy/manifest.json` on that commit already carries
   the target version. The workflow never bumps versions or picks one for you.
2. **Create the tag outside the workflow**, under separate explicit approval:
   create `v<version>` pointing at the exact reviewed commit. This workflow
   never creates tags; it only verifies an existing one.
3. **Dispatch manually from `main`.** Run **Actions → Prepare release → Run
   workflow** with branch `main`, supplying `version`, the existing `tag`, and
   the full 40-character `commit_sha`. Dispatches are serialized per tag
   (`concurrency: release-<tag>`, no cancel-in-progress).
4. **Automatic validation (job `validate`).** The job
   - validates the three inputs against the formats above,
   - verifies the `release` environment protection (fails closed otherwise),
   - checks out the candidate commit as data only and re-validates against the
     candidate's `manifest.json`,
   - confirms the checked-out `HEAD` equals the input SHA and that
     `commits/refs/tags/<tag>` resolves to the same SHA (tag exists and points
     at the reviewed commit),
   - classifies the release: any `-beta.` suffix yields `prerelease=true`,
     everything else is stable,
   - builds `release-candidate.zip` (`custom_components/sec_energy` +
     `hacs.json`), records its SHA-256, and uploads a `release-candidate`
     artifact (retention 14 days) with a metadata summary. The ZIP is review
     evidence, **not** a HACS distribution asset.
5. **Inspect and approve.** Review the `release-candidate` artifact and the
   run summary. Only then approve the **`release` environment** deployment.
6. **Draft creation (job `prepare-draft`).** After approval, the write-capable
   job re-verifies that the tag still resolves to the same SHA, refuses to
   proceed if any release or draft already exists for the tag, and creates a
   **draft** release with `--verify-tag`, `--draft`, `--latest=false`, plus
   `--prerelease` for beta versions. It creates no tag and publishes nothing.

## Beta vs. stable classification

| Version example  | `prerelease` flag | Draft flags                          |
| ---------------- | ----------------- | ------------------------------------ |
| `1.2.3`          | `false`           | `--draft --latest=false`             |
| `1.2.3-beta.1`   | `true`            | `--draft --latest=false --prerelease`|

Because every draft uses `--latest=false`, a beta draft can never be marked
"Latest" and never displaces the current stable release in HACS. Set "Latest"
deliberately, by hand, only when publishing a stable release.

## Publication (separate approval queue)

Publishing a draft is **not** part of this workflow and never will be. Final
publication is a separate, explicit Marcello decision handled through the
publication approval queue (the same `draft_queue.py` gate used for all
outbound GitHub actions). Before publishing, verify in the GitHub UI:

- tag name and target commit SHA match the reviewed candidate,
- manifest version on the tag matches the release version,
- prerelease flag matches the beta/stable classification,
- release notes are correct and complete.

Only a human publish action in GitHub makes a release visible to HACS users.

## Local testing without a live release

No live tag, release, or publication is needed to test the validator and the
workflow constraints:

```sh
python3 tests/test_release_workflow.py
python3 scripts/validate_release.py --version 1.1.0 --tag v1.1.0 \
  --sha <reviewed-40-character-sha> \
  --manifest custom_components/sec_energy/manifest.json
```

The protected-environment approval flow itself must be verified by the
repository owner when configuring it. Do not dispatch a real candidate as a
test without approval.
