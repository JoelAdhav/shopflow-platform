# ADR 0004: CI design

**Status:** accepted (Phase 2)

## Decisions

### 1. CI runs the same commands as the laptop
Lint and tests run inside the Dockerfile `test` stage, locally (`.\tasks.ps1 test`) and in CI.
One definition of "tests pass", same tool versions in both places.

### 2. Scan before push; fail on fixable HIGH/CRITICAL
Trivy runs on the built image with `--severity HIGH,CRITICAL --ignore-unfixed --exit-code 1`.
The push step comes after it, so a vulnerable image never reaches the registry.

`--ignore-unfixed`: findings with no released fix are not reported. Blocking on something
nobody can fix only teaches the team to bypass the gate. Trade-off: an unfixed critical
is invisible here. A scheduled scan of running images would cover that later.

### 3. Tag images with the git SHA
`ghcr.io/<owner>/shopflow-api:<git sha>`. Immutable and traceable: the tag says which commit
is running. `latest` says nothing and changes under you. Phase 4 (GitOps) depends on this.

### 4. Pin actions to commit SHAs, tools to exact versions
A tag such as `v7` can be re-pointed to different code; a commit SHA cannot. Dependabot
keeps the pins fresh.

### 5. Least-privilege token
Workflow default is `contents: read`. Only the build job gets `packages: write`.
Registry login uses the built-in short-lived `GITHUB_TOKEN`, so there is no stored secret to leak.

### 6. Patch OS packages in the Dockerfile
The first scan failed on all three images (see interview notes). Fix: `apt-get upgrade` /
`apk upgrade` in the runtime stage, and remove the base image's bundled pip.
Trade-off: the build is less reproducible, because the same Dockerfile can pull newer
packages next week. Accepted: unpatched known CVEs are the bigger risk.

## Not done, on purpose
- **Trivy via plain `docker run`, not `aquasecurity/trivy-action`:** identical command locally
  and in CI, and one less third-party action to trust.
- **No multi-arch builds:** kind on this laptop is amd64 only.
- **No deploy step:** deployment is pull-based GitOps in Phase 4.
