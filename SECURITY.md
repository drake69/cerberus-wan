# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest  | Yes       |
| < latest | No, please upgrade through HACS |

## Reporting a Vulnerability

If you discover a security vulnerability in Cerberus WAN, **please do not open a public issue.**

Report it privately instead:

1. **GitHub Security Advisories** (preferred): open the
   [Security tab](https://github.com/drake69/cerberus-wan/security/advisories)
   and click **Report a vulnerability**
2. **Email**: the address on the [maintainer's GitHub profile](https://github.com/drake69)

### What to include

- Description of the vulnerability
- Steps to reproduce
- Affected version(s)
- Potential impact
- Suggested fix, if you have one

### Response timeline

| Step | Timeline |
|------|----------|
| Acknowledgment | Within 48 hours |
| Initial assessment | Within 7 days |
| Patch release | Within 30 days, or within 7 days if critical |
| Public disclosure | After the patch is released |

## Scope

In scope:

- The integration code in `custom_components/cerberus_wan/`
- The GitHub Actions workflows in `.github/workflows/`, including the release
  workflow that builds and attaches the archive HACS downloads
- Handling of the configuration a user enters in the config flow

Out of scope:

- Vulnerabilities in upstream dependencies. Report those to the project that
  owns them; open an issue here only if this integration uses the dependency
  in a way that makes the problem worse
- Vulnerabilities in Home Assistant itself
- Social engineering and denial of service

## What this integration does and does not do

Worth stating plainly, because it bounds the attack surface:

- It performs outbound DNS lookups only: the public address of the connection,
  and the Team Cymru registry that maps that address to an autonomous system.
  No inbound listener, no open port, no cloud account, no credentials.
- It stores the address to ASN mapping in the Home Assistant store, and reads
  the provider table the user typed into the config flow. Nothing else is
  persisted.
- It never runs a shell, never deserialises untrusted input, and holds no
  secret of its own.

## Security measures

- **Static analysis**: Bandit and a forbidden pattern guard run on every pull
  request, together with CodeQL
- **Dependency audit**: `pip-audit` runs monthly and opens an issue when a
  known vulnerability appears; `uv.lock` pins every version
- **Pinned actions**: every GitHub Action is pinned to a commit SHA, so no
  third party workflow changes under us between one run and the next
- **Layer isolation, enforced by a test**: the domain layer cannot import
  Home Assistant or the infrastructure layer, so the logic that decides which
  provider is carrying traffic stays testable and free of side effects
- **Entity selectors are domain constrained**: the automations the integration
  can trigger are limited to `automation` and `script`

## Acknowledgments

Responsible disclosure is appreciated. Whoever reports a valid vulnerability is
credited in the release notes, unless they prefer to stay anonymous.
