"""Strict, dependency-free storage primitives for the S1–S6 contract.

Frontmatter accepts a conservative flat YAML subset. Unsupported YAML is
quarantined on read and rejected before writes, never silently reserialized.
"""
import json
import os
import re

FIELDS = ('memory_schema', 'scope', 'status', 'project_id', 'scope_inferred',
          'scope_reason', 'status_reason')
ID_RX = re.compile(r'prj-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key: ' + key)
        result[key] = value
    return result


def strict_json(text):
    def reject(value):
        raise ValueError('non-finite JSON number')
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject)


def one_line(value, field):
    if not isinstance(value, str) or not value.strip() or any(c in value for c in '\r\n\x00\v\f\x85\u2028\u2029'):
        raise ValueError(field + ' must be a nonempty single line')
    return value.strip()


def project_id(value):
    value = one_line(value, 'project_id').translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))
    if not ID_RX.fullmatch(value):
        raise ValueError('project_id must be prj-UUID v4')
    return value


def root_path(value):
    one_line(value, 'root')  # Validate, but spaces are part of filesystem identity.
    return os.path.realpath(os.path.abspath(os.path.expanduser(value)))


def validate_metadata(value, registered):
    if not isinstance(value, dict) or set(value) != set(FIELDS):
        raise ValueError('metadata requires all seven v1 fields, no extra fields')
    value = dict(value)
    if type(value['memory_schema']) is not int or value['memory_schema'] != 1:
        raise ValueError('memory_schema must be integer 1')
    scope, status = value['scope'], value['status']
    if scope not in ('global', 'project', None) or status not in ('confirmed', 'candidate'):
        raise ValueError('invalid scope/status')
    if type(value['scope_inferred']) is not bool:
        raise ValueError('scope_inferred must be boolean')
    if scope == 'project':
        value['project_id'] = project_id(value['project_id'])
        if value['project_id'] not in registered:
            raise ValueError('unregistered project_id')
    elif value['project_id'] is not None or value['scope_inferred']:
        raise ValueError('global/null requires null project_id and false scope_inferred')
    if scope is None and status != 'candidate':
        raise ValueError('null scope requires candidate')
    for key in ('scope_reason', 'status_reason'):
        value[key] = one_line(value[key], key)
    return value


def scalar(raw):
    raw = raw.strip()
    if raw.startswith('"'):
        return strict_json(raw)
    if raw.startswith("'"):
        if not re.fullmatch(r"'(?:[^']|'')*'", raw):
            raise ValueError('unclosed YAML quote')
        return raw[1:-1].replace("''", "'")
    if raw in ('null', '~', ''):
        return None
    if raw in ('true', 'false'):
        return raw == 'true'
    if re.fullmatch(r'[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|[+-]?[0-9]+[eE][+-]?[0-9]+', raw):
        return float(raw)
    if re.fullmatch(r'-?[0-9]+', raw):
        return int(raw)
    if raw.startswith('[') and raw.endswith(']'):
        if raw == '[]':
            return []
        try:
            return strict_json(raw)
        except ValueError:
            if any(c in raw for c in (chr(34), chr(39), '{', '}')) or '[' in raw[1:] or ']' in raw[:-1]:
                raise ValueError('unsupported YAML flow sequence')
            return [scalar(item) for item in raw[1:-1].split(',')]
    if raw[:1] in '[{&*!|>%@`#' or raw.startswith(('- ', '? ')) or ': ' in raw or ' #' in raw:
        raise ValueError('unsupported YAML scalar')
    return raw


def parse_note(text):
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != '---':
        raise ValueError('missing frontmatter')
    values, raw_lines = {}, []
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == '---':
            return values, raw_lines, ''.join(lines[i + 1:])
        if not line.strip() or line.startswith('#'):
            raw_lines.append((None, line))
            continue
        match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*?)(?:\r?\n)?', line)
        if not match:
            raise ValueError('unsupported YAML frontmatter')
        key, raw = match.groups()
        if key in values:
            raise ValueError('duplicate frontmatter key: ' + key)
        values[key] = scalar(raw)
        raw_lines.append((key, line))
    raise ValueError('unclosed frontmatter')


def note_state(values, registered):
    selected = {k: values[k] for k in FIELDS if k in values}
    if not selected:
        return 'legacy', dict.fromkeys(FIELDS)
    return 'valid', validate_metadata(selected, registered)


def validate_registry(value):
    if not isinstance(value, dict) or set(value) != {'schema_version', 'projects'} or type(value['schema_version']) is not int or value['schema_version'] != 1 or not isinstance(value['projects'], list):
        raise ValueError('invalid projects registry')
    ids, owners, projects = set(), {}, []
    for entry in value['projects']:
        if not isinstance(entry, dict) or set(entry) != {'id', 'label', 'roots'}:
            raise ValueError('invalid registry entry')
        identity = project_id(entry['id'])
        if identity != entry['id'] or identity in ids:
            raise ValueError('duplicate or noncanonical registry ID')
        ids.add(identity)
        label = one_line(entry['label'], 'label')
        if not isinstance(entry['roots'], list) or not entry['roots']:
            raise ValueError('roots must be a nonempty array')
        roots = []
        for root in entry['roots']:
            if not isinstance(root, str) or not os.path.isabs(root):
                raise ValueError('registry root must be absolute')
            root = root_path(root)
            if root in owners:
                raise ValueError('duplicate normalized root ownership')
            owners[root] = identity
            roots.append(root)
        projects.append(dict(id=identity, label=label, roots=roots))
    return dict(schema_version=1, projects=projects)
