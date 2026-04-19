# skills

A collection of Claude Code skills and plugins.

## Skills

| Name | Description |
|---|---|
| [immutable-prd](immutable-prd/) | Guided authoring for immutable, append-only PRD/pitch files. Interview + adversarial review + 90% completeness gate. |

More skills will be added here over time.

## Installation

### Plugin marketplace

```sh
claude plugin marketplace add choi88andys/skills
claude plugin install <skill-name>
```

### Local

Clone the repo and reference the individual skill directory, or copy it into your Claude Code skills path.

## Structure

```
skills/
├── LICENSE                    # MIT
├── README.md                  # this file
├── .claude-plugin/
│   └── marketplace.json       # plugin marketplace manifest
└── <skill-name>/
    ├── SKILL.md               # skill definition (frontmatter + instructions)
    └── README.md              # usage documentation
```

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

Individual skills cite their design-pattern sources. Common references:

- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT)
- [zscole/adversarial-spec](https://github.com/zscole/adversarial-spec)
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT)
