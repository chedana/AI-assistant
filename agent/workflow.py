from skills.search.handler import run_chat


def run() -> None:
    # Phase-1 migration keeps the proven search workflow behavior unchanged.
    run_chat()
