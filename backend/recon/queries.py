"""build the per-target search queries.

- a list of templates covering the facets the brief asks for:
  name + company, talks, podcasts, github, news, events, job ads, social
"""

TEMPLATES = [
    '"{name}" {company}',
    '"{name}" {company} linkedin',
    '"{name}" talk OR keynote OR speaker',
    '"{name}" podcast OR interview',
    '"{name}" github',
    '"{name}" news OR announcement',
    '"{name}" conference OR event',
    '{company} hiring OR careers OR jobs',
    '"{name}" x.com OR twitter',
]


def build_queries(name, company):
    # fill each template; collapse the double space left when company is empty
    return [t.format(name=name, company=company).replace("  ", " ").strip() for t in TEMPLATES]
