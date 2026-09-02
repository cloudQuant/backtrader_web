# Contributing

How to contribute code and documentation to AI for Investor. The full local-development,
testing, and style guide lives in the root [CONTRIBUTING.md](https://github.com/cloudQuant/backtrader_web/blob/master/CONTRIBUTING.md).

## Branch model (iteration 195)

| Branch | Role | Accepts |
| --- | --- | --- |
| `dev` | Daily integration | All regular PRs (`feature/*`, `fix/*`, `docs/*`, …) |
| `master` | Release branch | Only `release/vX.Y.Z` promotion PRs and `hotfix/master-*` emergency PRs |

**Regular changes must target `dev`.** A PR into `master` from any other source branch is
rejected by the PR Governance gate.

## Fork and clone

1. Fork the repository on GitHub.
2. Clone your fork (replace `YOUR_USERNAME` with your own username):

   ```bash
   git clone https://github.com/YOUR_USERNAME/backtrader_web.git
   cd backtrader_web
   ```

3. Add the upstream remote and base your work on `dev`:

   ```bash
   git remote add upstream https://github.com/cloudQuant/backtrader_web.git
   git fetch upstream
   git checkout -b feature/your-feature upstream/dev
   ```

## Open a pull request

1. Push your branch and open a PR **targeting `dev`**.
2. Follow `.github/PULL_REQUEST_TEMPLATE.md`:
   - `## Governance declaration`: target-branch justification, risk level (auto-classified
     from changed paths; labels cannot lower it), and test evidence;
   - `master` hotfix PRs additionally declare a dev-backport plan; release promotion PRs
     additionally link the release checklist;
   - fill in the `i18n change manifest` when locale files change (CI-verified).
3. Wait for maintainer review — passing automation is necessary but not sufficient; merging
   requires human approval.

## Reporting issues

- Bugs: use the Bug Report form with minimal reproduction steps and environment details.
- Features: use the Feature Request form.
- Questions: ask in [Discussions](https://github.com/cloudQuant/backtrader_web/discussions)
  instead of opening a question issue.

## Code of conduct

Be constructive and respectful; review feedback targets code, not people. Submitting a
contribution licenses it under the MIT License.
