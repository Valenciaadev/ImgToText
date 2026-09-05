import sys


def _entrypoint() -> int:
    if "--self-test" in sys.argv:
        from imgtotext.diagnostics import run_self_test

        return run_self_test()
    from imgtotext.app import main

    return main()


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
