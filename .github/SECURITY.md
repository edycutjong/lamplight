# Security Policy

## Supported Versions
| Version | Supported |
|---|---|
| latest (`main`) | ✅ |

## Reporting a Vulnerability
Please **do not** open a public issue for security vulnerabilities. Instead,
report them privately:

- Email **edy.cu@live.com**, or
- Use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) (Security → Report a vulnerability).

You'll get an acknowledgment within 48 hours and a resolution timeline after
triage. Please give us a reasonable window to patch before public disclosure.

## Notes on This Project
Lamplight ships with **synthetic fixture data only** — no real patient
information, no PHI. Signing seeds (`LAMPLIGHT_SIGNING_SEED_HEX`,
`LAMPLIGHT_SEAL_SEED_HEX`) and `DASHSCOPE_API_KEY` must never be committed;
see `.env.example` and `.gitignore`.
