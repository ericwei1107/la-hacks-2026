IGNORED = {'$id', '$schema', '$defs', 'title', 'description'}
SCALARS = (str, int, float, bool, type(None))


class Unsupported(Exception):
    pass


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_integer(value):
    return (isinstance(value, int) and not isinstance(value, bool)) or (isinstance(value, float) and value.is_integer())


TYPES = {
    'object': lambda value: isinstance(value, dict),
    'array': lambda value: isinstance(value, list),
    'string': lambda value: isinstance(value, str),
    'integer': is_integer,
    'number': is_number,
    'boolean': lambda value: isinstance(value, bool),
    'null': lambda value: value is None,
}


def same(left, right):
    return isinstance(left, bool) == isinstance(right, bool) and left == right


def scalar(value):
    if not isinstance(value, SCALARS):
        raise Unsupported('non-scalar constant')
    return value


def type_check(spec):
    names = spec if isinstance(spec, list) else [spec]
    if not names or any(name not in TYPES for name in names):
        raise Unsupported('type')
    tests = [TYPES[name] for name in names]
    if len(tests) == 1:
        return tests[0]
    return lambda value: any(test(value) for test in tests)


def conjunction(checks):
    checks = tuple(checks)
    if not checks:
        return lambda value: True
    if len(checks) == 1:
        return checks[0]

    def check(value):
        for test in checks:
            if not test(value):
                return False
        return True

    return check


def object_properties(members):
    members = tuple(members)

    def check(value):
        if not isinstance(value, dict):
            return True
        for name, test in members:
            if name in value and not test(value[name]):
                return False
        return True

    return check


def array_items(element):
    def check(value):
        if not isinstance(value, list):
            return True
        for item in value:
            if not element(item):
                return False
        return True

    return check


def required_names(names):
    names = frozenset(names)
    return lambda value: not isinstance(value, dict) or value.keys() >= names


def build(node, defs, active):
    if not isinstance(node, dict):
        raise Unsupported('schema form')
    checks = []
    for keyword, argument in node.items():
        if keyword in IGNORED:
            continue
        if keyword == 'type':
            checks.append(type_check(argument))
        elif keyword == 'const':
            expected = scalar(argument)
            checks.append(lambda value, expected=expected: same(value, expected))
        elif keyword == 'enum':
            options = tuple(scalar(option) for option in argument)
            if all(isinstance(option, str) for option in options):
                names = frozenset(options)
                checks.append(lambda value, names=names: isinstance(value, str) and value in names)
            else:
                checks.append(lambda value, options=options: any(same(value, option) for option in options))
        elif keyword == 'minimum':
            checks.append(lambda value, limit=argument: not is_number(value) or value >= limit)
        elif keyword == 'maximum':
            checks.append(lambda value, limit=argument: not is_number(value) or value <= limit)
        elif keyword == 'minItems':
            checks.append(lambda value, limit=argument: not isinstance(value, list) or len(value) >= limit)
        elif keyword == 'maxItems':
            checks.append(lambda value, limit=argument: not isinstance(value, list) or len(value) <= limit)
        elif keyword == 'required':
            checks.append(required_names(argument))
        elif keyword == 'properties':
            checks.append(object_properties((name, build(sub, defs, active)) for name, sub in argument.items()))
        elif keyword == 'items':
            if not isinstance(argument, dict):
                raise Unsupported('items form')
            checks.append(array_items(build(argument, defs, active)))
        elif keyword == '$ref':
            prefix = '#/$defs/'
            if not isinstance(argument, str) or not argument.startswith(prefix) or argument[len(prefix):] not in defs:
                raise Unsupported('reference')
            name = argument[len(prefix):]
            if name in active:
                raise Unsupported('recursive reference')
            checks.append(build(defs[name], defs, active | {name}))
        else:
            raise Unsupported(keyword)
    return conjunction(checks)


def compile_schema(schema):
    try:
        return build(schema, schema.get('$defs', {}), frozenset())
    except (Unsupported, TypeError, AttributeError):
        return None
