# main.py
# Simple CLI entry point for local testing of the Responser.
# Uses the same logic as the Speakeasy agent but runs once per query.

import sys
from core.responser import Responser
from core.data import load_graph, WD, WDT

def cli_answer(question: str) -> str:
    """Run a single-question test using the local graph."""
    graph = load_graph()
    r = Responser()
    return r.generate_response(question, graph, WDT, WD)

if __name__ == "__main__":
    # Allow the user to pass a question as a command-line argument.
    # Example:
    #   python main.py "Who directed 'Fargo'?"
    question = " ".join(sys.argv[1:]) or "Who directed 'Fargo'?"
    print(cli_answer(question))