"""`python -m daftar_spec FILE...`. Exit codes follow C-5: 0 ok, 2 unreadable, 3 invalid."""

import sys

from daftar_spec import format_errors, load_spec_file, validate_spec


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m daftar_spec FILE...", file=sys.stderr)
        return 2
    code = 0
    for name in argv:
        try:
            spec = load_spec_file(name)
        except (OSError, ValueError) as error:
            print(f"{name}: unreadable: {error}", file=sys.stderr)
            code = max(code, 2)
            continue
        errors = validate_spec(spec)
        if errors:
            print(f"{name}: invalid\n{format_errors(errors)}", file=sys.stderr)
            code = 3
        else:
            print(f"{name}: ok")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
