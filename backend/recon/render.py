"""render a Profile as human-readable markdown for the pitch and the viewer."""


def to_markdown(p):
    lines = [f"# {p.name}", ""]
    lines.append(f"**{p.role or 'role unknown'}** - {p.company}" + (f" ({p.domain})" if p.domain else ""))
    lines.append(f"**Exposure score:** {p.exposure_score}/100")
    lines.append("")

    lines.append("## Hooks (ranked)")
    for h in p.hooks:
        lines.append(f"- **{h.topic}** - p={h.probability:.2f} ({h.angle})")
        if h.rationale:
            lines.append(f"  - {h.rationale}")
    if not p.hooks:
        lines.append("- (none)")
    lines.append("")

    lines.append("## Facts")
    for f in p.facts:
        mark = "x" if f.verified else " "
        lines.append(f"- [{mark}] *{f.category}*: {f.value}")
        lines.append(f"  <{f.source_url}>")
    lines.append("")
    lines.append(f"_Sources: {len(p.sources)} - generated {p.generated_at}_")
    return "\n".join(lines)
