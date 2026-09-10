"""Keep new repository entries small while displaying defaults in the form."""


def omit_unchanged_defaults(entry: dict, defaults: dict) -> None:
    for section, fields in defaults.items():
        target = entry.get(section)
        if not isinstance(target, dict):
            continue
        for field, default in fields.items():
            if field not in target:
                continue
            value = target[field]
            if value == default or (value == "" and default is None):
                target.pop(field)
        if not target:
            entry.pop(section)
