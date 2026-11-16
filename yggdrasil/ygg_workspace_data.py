"""Read-only, scoped Workspace queries, executed inside the memory engine."""
from __future__ import annotations

import json


def _text(value, name, maximum=1000):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f'Некорректное поле {name}')
    return value


def _integer(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f'Некорректное поле {name}')
    return value


def normalize(record):
    """Stable browser contract, independent of legacy engine aliases."""
    meta = record.get('metadata')
    if not isinstance(meta, dict):
        try:
            meta = json.loads(record.get('metadata_json') or '{}')
        except (TypeError, ValueError):
            meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return {'id': record['id'], 'content': record.get('content', record.get('memory', '')),
            'project': record.get('project') or meta.get('project') or '',
            'type': record.get('type') or meta.get('type') or 'memory',
            'source': record.get('source') or meta.get('source') or '',
            'created_at': record.get('created_at') or 0,
            'archived': bool(record.get('archived')), 'metadata': meta}


def workspace_query(store, body):
    """Identity is mandatory; null project means all, empty means unassigned."""
    op = body.get('op')
    user = _text(body.get('user_id'), 'user_id')
    namespace = _text(body.get('namespace'), 'namespace')
    if not user or not namespace:
        raise ValueError('Нужны user_id и namespace')
    if op not in ('projects', 'memories', 'memory', 'sources', 'graph', 'search'):
        raise ValueError('Неизвестная операция Workspace')
    if op != 'projects' and 'project' not in body:
        raise ValueError('Нужна явная область project')
    project = body.get('project')
    if project is not None:
        _text(project, 'project')
    query = _text(body.get('query', ''), 'query', 8000)
    kind = _text(body.get('type', ''), 'type')
    source = _text(body.get('source', ''), 'source', 4000)
    archived = body.get('archived', False)
    if not isinstance(archived, bool):
        raise ValueError('archived должен быть boolean')
    limit = _integer(body.get('limit', 50), 'limit', 1, 200)
    offset = _integer(body.get('offset', 0), 'offset', 0, 100_000_000)
    where = ['m.user_id=?', 'm.namespace=?']
    params = [user, namespace]
    if project is not None:
        where.append("COALESCE(m.project,'')=?")
        params.append(project)

    if op == 'search':
        filters = {'workspace_unassigned': True} if project == '' else {}
        if project:
            filters['project'] = project
        records = store.search(query=query, user_id=user, limit=min(limit, 20),
                               filters=filters, namespaces=[namespace])
        return {'items': [normalize(r) for r in records]}

    with store._lock:
        conn = store._conn
        if op == 'projects':
            groups = conn.execute('''SELECT COALESCE(project,'') AS name,
                COALESCE(NULLIF(type,''),'memory') AS type, archived, count(*) AS count,
                max(created_at) AS latest_at FROM memories
                WHERE user_id=? AND namespace=? GROUP BY project,type,archived''', (user, namespace))
            projects = {}
            for row in groups:
                item = projects.setdefault(row['name'], {'name': row['name'], 'count': 0,
                    'archived_count': 0, 'latest_at': 0, 'types': {}})
                if row['archived']:
                    item['archived_count'] += row['count']
                else:
                    item['count'] += row['count']
                    item['types'][row['type']] = item['types'].get(row['type'], 0) + row['count']
                item['latest_at'] = max(item['latest_at'], row['latest_at'])
            return {'projects': sorted(projects.values(), key=lambda p: (-p['latest_at'], p['name']))}
        if op == 'memory':
            ident = _text(body.get('id'), 'id')
            row = conn.execute('SELECT m.* FROM memories m WHERE ' + ' AND '.join(where)
                               + ' AND m.id=?', [*params, ident]).fetchone()
            if row is None:
                raise KeyError('Запись не найдена в этой области')
            return {'memory': normalize(dict(row)),
                    'relations': _edges(conn, [ident], user, namespace, project)}

        where.append('m.archived=?')
        params.append(int(archived) if op == 'memories' else 0)
        if query:
            where.append("m.content LIKE ? ESCAPE '\\'")
            params.append('%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
        if kind:
            where.append("COALESCE(NULLIF(m.type,''),'memory')=?")
            params.append(kind)
        if 'source' in body:
            where.append("COALESCE(m.source,'')=?")
            params.append(source)
        focus = body.get('focus')
        if op == 'graph' and focus:
            _text(focus, 'focus')
            # Only the chosen node and its immediate neighbours, inside this scope.
            where.append('''(m.id=? OR m.id IN (
                SELECT to_id FROM relations WHERE from_id=? AND user_id=?
                UNION SELECT from_id FROM relations WHERE to_id=? AND user_id=?))''')
            params.extend([focus, focus, user, focus, user])
        clause = ' AND '.join(where)
        if op == 'sources':
            rows = conn.execute("SELECT COALESCE(m.source,'') AS name, count(*) AS count "
                                'FROM memories m WHERE ' + clause + ' GROUP BY m.source ORDER BY count DESC,name', params)
            return {'sources': [dict(r) for r in rows]}
        total = conn.execute('SELECT count(*) FROM memories m WHERE ' + clause, params).fetchone()[0]
        cap, start = (300, 0) if op == 'graph' else (limit, offset)
        rows = conn.execute('SELECT m.* FROM memories m WHERE ' + clause
                            + ' ORDER BY m.created_at DESC,m.id LIMIT ? OFFSET ?', [*params, cap, start])
        items = [normalize(dict(r)) for r in rows]
        if op == 'graph':
            return {'nodes': items, 'edges': _edges(conn, [r['id'] for r in items], user, namespace, project),
                    'total': total, 'truncated': total > len(items)}
        return {'items': items, 'total': total}


def _edges(conn, ids, user, namespace, project):
    if not ids:
        return []
    marks = ','.join('?' for _ in ids)
    rows = conn.execute(f'''SELECT r.from_id,r.to_id,r.rel_type,
        COALESCE(a.project,'') AS a_project, COALESCE(b.project,'') AS b_project
        FROM relations r JOIN memories a ON a.id=r.from_id JOIN memories b ON b.id=r.to_id
        WHERE r.user_id=? AND a.user_id=? AND b.user_id=? AND a.namespace=? AND b.namespace=?
        AND (r.from_id IN ({marks}) OR r.to_id IN ({marks}))
        ORDER BY r.from_id,r.to_id,r.rel_type''', [user, user, user, namespace, namespace, *ids, *ids])
    selected = set(ids)
    edges = []
    for row in rows:
        external = project is not None and (row['a_project'] != project or row['b_project'] != project)
        if not external and (row['from_id'] not in selected or row['to_id'] not in selected):
            # Detail panel (one id) still needs its neighbours, graph omits unloaded nodes.
            if len(ids) != 1:
                continue
        edge = {key: row[key] for key in ('from_id', 'to_id', 'rel_type')}
        if external:
            edge.update(external=True, other_project=row['b_project'] if row['a_project'] == project else row['a_project'])
        edges.append(edge)
    return edges
