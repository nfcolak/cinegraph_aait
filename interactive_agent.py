# interactive_agent.py
# Dual-mode agent: Speakeasy bot + interactive CLI
# Run both simultaneously - Speakeasy in background thread, CLI in foreground

import os
import sys
import time
import traceback
import threading
from typing import List

# Make sure local wheel installs (e.g., ./libs/speakeasypy) are visible without
# modifying the user's PYTHONPATH manually.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LOCAL_LIBS = os.path.join(PROJECT_ROOT, "libs")
if os.path.isdir(LOCAL_LIBS) and LOCAL_LIBS not in sys.path:
    sys.path.insert(0, LOCAL_LIBS)

from speakeasypy import Speakeasy, Chatroom
from dotenv import load_dotenv

from core.responser import Responser
from core.data import load_graph, load_embeddings, WD, WDT

DEFAULT_HOST_URL = "https://speakeasy.ifi.uzh.ch"
DEFAULT_MSG = "Could not generate an answer. Please rephrase your question in a simple way."
LISTEN_FREQ = 2  # seconds

# --- CREDENTIALS ---
BOT_USER = os.getenv("SPEAKEASY_USER", "SlateLeapingDeer")
BOT_PASS = os.getenv("SPEAKEASY_PASSWORD", "")


class InteractiveAgent:
    def __init__(self, host: str, username: str, password: str):
        self.username = BOT_USER

        # 1) Load local graph (once)
        print("[interactive_agent] Loading graph...")
        self.graph = load_graph()
        print("[interactive_agent] Graph loaded successfully")

        # 2) Load embeddings (once, optional)
        try:
            (
                self.entity_embeds,
                self.relation_embeds,
                self.ent_uri_to_id,
                self.rel_uri_to_id,
                self.id_to_ent_uri,
            ) = load_embeddings()
            self.responser = Responser(
                self.entity_embeds,
                self.relation_embeds,
                self.ent_uri_to_id,
                self.rel_uri_to_id,
                self.id_to_ent_uri,
            )
            print("[interactive_agent] Embeddings loaded and attached to Responser")
        except Exception as e:
            print(f"[interactive_agent] Embeddings not available ({e}); falling back to factual-only")
            self.responser = Responser()

        # 3) Connect to Speakeasy
        print("[interactive_agent] Connecting to Speakeasy...")
        self.speakeasy = Speakeasy(host=host, username=username, password=password)
        self.speakeasy.login()
        print("[interactive_agent] Logged in to Speakeasy")

        # Dedup guards to prevent double replies
        self.seen = set()
        self.last_ord = {}

        # Thread control
        self.running = True

    def speakeasy_loop(self):
        """Speakeasy listen loop running in background thread"""
        backoff = 2
        print("[speakeasy_thread] Started listening...")

        while self.running:
            try:
                rooms: List[Chatroom] = self.speakeasy.get_rooms(active=True)
                for room in rooms:
                    # Greet only once per room
                    if not getattr(room, "initiated", False):
                        try:
                            room.post_messages(f"Hey there! I am {self.username}. Ask me about the graph.")
                            room.initiated = True
                        except Exception as e:
                            print(f"[speakeasy_warn] greeting failed: {e}")

                    # Process new partner messages
                    for message in room.get_messages(only_partner=True, only_new=True):
                        key = (room.room_id, message.ordinal)

                        # Dedup check
                        if room.room_id in self.last_ord and message.ordinal <= self.last_ord[room.room_id]:
                            continue
                        if key in self.seen:
                            continue
                        self.seen.add(key)

                        print(f"\n[SPEAKEASY] room={room.room_id} ordinal={message.ordinal}")
                        print(f"[SPEAKEASY] Question: {message.message}")

                        try:
                            resp = self.responser.generate_response(message.message, self.graph, WDT, WD)
                            resp = (resp or DEFAULT_MSG)
                        except Exception as e:
                            print(f"[speakeasy_error] generate_response: {e}")
                            traceback.print_exc()
                            resp = DEFAULT_MSG

                        # Post and mark processed
                        try:
                            room.post_messages(resp)
                            print(f"[SPEAKEASY] Posted answer\n")
                        except Exception as e:
                            print(f"[speakeasy_warn] post_messages failed: {e}")

                        try:
                            room.mark_as_processed(message)
                            self.last_ord[room.room_id] = message.ordinal
                        except Exception as e:
                            print(f"[speakeasy_warn] mark_as_processed failed: {e}")

                    # Handle reactions
                    for reaction in room.get_reactions(only_new=True):
                        try:
                            room.post_messages(f"Received your reaction: '{reaction.type}'")
                            room.mark_as_processed(reaction)
                        except Exception as e:
                            print(f"[speakeasy_warn] reaction handling failed: {e}")

                time.sleep(LISTEN_FREQ)
                backoff = 2  # reset on success

            except Exception as e:
                if self.running:
                    print(f"[speakeasy_error] transient error: {e}")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60)

        print("[speakeasy_thread] Stopped")

    def cli_loop(self):
        """Interactive CLI loop running in main thread"""
        print("\n" + "="*60)
        print("INTERACTIVE CLI - Ask me anything about the graph!")
        print("Type 'exit' or 'quit' to stop")
        print("="*60 + "\n")

        while self.running:
            try:
                question = input("\n> ").strip()

                if not question:
                    continue

                if question.lower() in ['exit', 'quit', 'q']:
                    print("\nShutting down...")
                    self.running = False
                    break

                print(f"\n[CLI] Processing your question...")

                try:
                    answer = self.responser.generate_response(question, self.graph, WDT, WD)
                    answer = answer or DEFAULT_MSG
                    print(f"\n[ANSWER]\n{answer}")
                except Exception as e:
                    print(f"\n[ERROR] {e}")
                    traceback.print_exc()
                    print(f"\n[ANSWER]\n{DEFAULT_MSG}")

            except (EOFError, KeyboardInterrupt):
                print("\n\nShutting down...")
                self.running = False
                break

    def start(self):
        """Start both Speakeasy bot and CLI interface"""
        # Start Speakeasy in background thread
        speakeasy_thread = threading.Thread(target=self.speakeasy_loop, daemon=True)
        speakeasy_thread.start()

        # Run CLI in main thread
        try:
            self.cli_loop()
        finally:
            self.running = False
            speakeasy_thread.join(timeout=5)


def _load_env():
    """Load SPEAKEASY configuration from .env"""
    load_dotenv()
    host = os.getenv("SPEAKEASY_HOST", DEFAULT_HOST_URL)
    user = os.getenv("SPEAKEASY_USER", BOT_USER)
    pwd = os.getenv("SPEAKEASY_PASSWORD", BOT_PASS)
    return host, user, pwd


if __name__ == "__main__":
    host, user, pwd = _load_env()
    agent = InteractiveAgent(host, user, pwd)
    agent.start()
