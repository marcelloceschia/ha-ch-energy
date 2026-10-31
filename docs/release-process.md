# Release preparation (maintainers)

`.github/workflows/release.yml` never publishes a release automatically. Neither
pushes to main nor tag pushes trigger it. HACS uses published GitHub releases;
a workflow artifact or a draft does not opt users into a beta.

## One-time repository setup (owner action)

Create the GitHub environment **release** in Settings → Environments. Require
user **marcelloceschia** as reviewer, enable **Prevent self-review**, and disable
**Allow administrators to bypass configured protection rules**. Restrict deployment
to main. The workflow reads the environment configuration and fails closed when
reviewer/self-review/bypass protection cannot be verified; merely declaring an
environment in YAML is not an approval gate. Check that the repository's Actions
token can read that configuration. Do not weaken the check to work around a 403.
No environment settings are created or changed by this workflow.

With self-review disabled, a different authorized maintainer must dispatch the
workflow so Marcello can approve it. No token or third-party approval action is
needed. Keep Actions workflow changes subject to code review/branch protection.

## Per candidate

1. Review the exact commit and its CI checks, including HACS and Hassfest.
   Manifest version must already be `X.Y.Z` or `X.Y.Z-beta.N` (N >= 1, no leading
   zeros). This workflow never bumps versions or chooses a future version.
2. Obtain separate explicit approval for creating the tag. Create `v<version>`
   at that exact commit outside the workflow. No tags are created here.
3. From main, manually run **Prepare release**, supplying version, existing tag,
   and the full lowercase 40-character commit SHA. Tag and manifest must match.
4. Inspect the `release-candidate` Actions artifact and summary. The ZIP is
   review evidence, not a HACS distribution asset. Approve the **release**
   environment only after inspecting it. The write-capable job then rechecks the
   tag and creates a **draft** release, refusing any existing release/draft.
   Beta suffixes produce `prerelease=true`; stable versions do not. All drafts
   use `--latest=false` so beta preparation cannot displace stable.
5. Publication is a separate, explicit Marcello decision in GitHub after draft
   review. Verify tag, target SHA, manifest, prerelease status and release notes
   before publishing. Set Latest deliberately for a stable release if desired.
   No workflow step publishes a release or attaches published assets.

No live tag, release, or publication is needed to test the validator:

```sh
python3 tests/test_release_workflow.py
python3 scripts/validate_release.py --version 1.1.0 --tag v1.1.0 \
  --sha <reviewed-40-character-sha> \
  --manifest custom_components/sec_energy/manifest.json
```

The protected-environment approval flow must be verified by the repository owner
when configuring it. Do not dispatch a real candidate as a test without approval.
