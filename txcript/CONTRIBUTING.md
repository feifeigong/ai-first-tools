# Contributing

Open an issue before opening a pull request.

## Propose a feature

Propose new ways to work with sessions in an [RFC issue](https://github.com/skillsynchq/txcript/issues/new?template=rfc.md). Explain what you want to do and show a small example of the input and expected output. Describe how you think it should work. We can work out API and CLI details in the issue.

You can start coding while we discuss the proposal. Every new feature needs discussion in the issue.

## Report a bug

[Open a bug report](https://github.com/skillsynchq/txcript/issues/new?template=bug_report.md). Include your txcript version, the agents and their versions, and the command or code you ran. Explain what you expected and what happened instead.

Attach the smallest session that still reproduces the problem. Real sessions are welcome after you remove private information. Check the whole file, including tool output and metadata, before uploading it.

For vulnerabilities, use [GitHub's private reporting](https://github.com/skillsynchq/txcript/security/advisories/new). See the [security policy](SECURITY.md).

## Submit a pull request

Link the issue in every PR. Explain what changed and why in plain English. Use simple terms and a before/after example if it helps. If you're writing with an agent, use [Unslop](https://www.skills.sh/cursor/plugins/unslop).

Use stacked PRs when an issue needs more than one PR. Open each PR against the branch of the PR it depends on. Link the PRs in review order.

Cover changed behavior with tests and update any affected docs. Follow the [test guide](tests/README.md) for test conventions.

## Work locally

Use the Rust version listed in [Cargo.toml](Cargo.toml) or newer.

```sh
git clone https://github.com/skillsynchq/txcript.git
cd txcript
cargo build --workspace
cargo test --workspace --all-features
```

More checks and the pre-push hook are in the [development reference](docs/usage.md#development). For the npm build, see the [JavaScript reference](docs/usage.md#npm-package).
