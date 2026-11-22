"""Read-only architecture evidence inventory. Never computes official points."""


def judging_evidence(bundle):
    nodes = bundle.get('nodes') or []
    messages = bundle.get('messages') or []
    by_id = {n.get('id'): n for n in nodes if n.get('id')}
    gaps, steps = [], []
    for node in nodes:
        if node.get('level') != 'contact':
            continue
        identity = node.get('id')
        matches = [m for m in messages if m.get('node_id') == identity]
        message = matches[0] if len(matches) == 1 else {}
        if len(matches) != 1:
            gaps.append(f'{identity}: expected one saved message, found {len(matches)}')
        receipt = message.get('message_id') or message.get('conversation_id')
        if not isinstance(receipt,str) or not receipt:
            receipt = None
            gaps.append(f'{identity}: no saved API receipt ID')
        qa = message.get('qa') or node.get('qa')
        if not isinstance(qa,dict) or type(qa.get('passed')) is not bool:
            gaps.append(f'{identity}: no usable QA verdict')
        # Traverse only recorded parent links. Do not invent a causal relation.
        ancestors, visited, parent = [], {identity}, node.get('parent_id')
        while parent:
            if parent in visited:
                gaps.append(f'{identity}: cyclic decision ancestry'); break
            visited.add(parent)
            ancestor = by_id.get(parent)
            if not ancestor:
                gaps.append(f'{identity}: missing ancestor {parent}'); break
            ancestors.append(ancestor);parent=ancestor.get('parent_id')
        choice = next((n for n in ancestors if n.get('level') == 'approach'),None)
        prior_contact = next((n for n in ancestors if n.get('level') == 'contact'),None)
        reactions = [n for n in nodes if n.get('parent_id') == identity and n.get('level') == 'reaction']
        if not node.get('reasoning'):
            gaps.append(f'{identity}: no recorded contact reasoning')
        raw_events = (bundle.get('events') or {}).get(identity)
        steps.append(dict(node_id=identity,decision=node.get('decision'),reason=node.get('reasoning'),
            approach=choice.get('decision') if choice else None,
            approach_reason=choice.get('reasoning') if choice else None,
            prior_contact_node_id=prior_contact.get('id') if prior_contact else None,
            receipt_id=receipt,session_id=message.get('session_id'),
            cumulative_touches=message.get('touches_used'),channel=message.get('channel'),
            qa=qa,event_types=[e.get('type') for e in raw_events if isinstance(e,dict)] if isinstance(raw_events,list) else None,
            reactions=[dict(node_id=r.get('id'),decision=r.get('decision'),reason=r.get('reasoning')) for r in reactions]))
    facts=(bundle.get('profile') or {}).get('facts') or []
    sources=sorted({f['source_url'] for f in facts if isinstance(f,dict) and isinstance(f.get('source_url'),str) and f['source_url']})
    alternatives=[dict(node_id=n.get('id'),options=n['rejected']) for n in nodes if n.get('rejected')]
    if steps and not alternatives: gaps.append('No recorded rejected alternatives')
    if not sources: gaps.append('No source URLs in the supplied profile')
    return dict(run_id=bundle.get('run_id'),mode=bundle.get('mode'),run_status=bundle.get('run_status'),
        source_urls=sources,recorded_contact_nodes=len(steps),receipt_backed_contacts=sum(s['receipt_id'] is not None for s in steps),
        recorded_followups=sum(s['prior_contact_node_id'] is not None for s in steps),
        alternatives=alternatives,steps=steps,gaps=gaps,
        official_score=None,official_incident_confirmation=None,
        limitation='Inventory of supplied records only. Parent links do not prove useful adaptation; receipts are not authenticated here. No official points or effectiveness inferred.')
