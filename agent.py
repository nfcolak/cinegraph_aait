# agent.py
# Speakeasy-based agent that answers using the local graph.nt only.
# Loads the graph & embeddings once, then connects to Speakeasy.
# Includes in-memory dedup to avoid double replies.
# Enhanced with rate limiting, timeout protection, and concurrent request limiting.

import os
import time
import traceback
from typing import List
from collections import deque
from threading import Lock, Semaphore
import signal

from speakeasypy import Speakeasy, Chatroom
from dotenv import load_dotenv

from core.responser import Responser
from core.data import load_graph, load_embeddings, WD, WDT

DEFAULT_HOST_URL = "https://speakeasy.ifi.uzh.ch"
DEFAULT_MSG = "Could not generate an answer. Please rephrase your question in a simple way."
LISTEN_FREQ = 2  # seconds

# Rate limiting configuration
MAX_REQUESTS_PER_MINUTE = 30  # Maximum requests per minute per room
MAX_CONCURRENT_REQUESTS = 5   # Maximum concurrent processing requests
REQUEST_TIMEOUT = 30          # Maximum seconds to process a single request

# --- CREDENTIALS (read from environment variables) ---
BOT_USER = os.getenv("SPEAKEASY_USER", "SlateLeapingDeer")
BOT_PASS = os.getenv("SPEAKEASY_PASSWORD", "")


class TimeoutError(Exception):
    """Raised when a request processing times out"""
    pass


def timeout_handler(signum, frame):
    """Handler for timeout signal"""
    raise TimeoutError("Request processing timed out")


class RateLimiter:
    """Simple sliding window rate limiter"""
    def __init__(self, max_requests, window_seconds=60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()
        self.lock = Lock()

    def is_allowed(self):
        """Check if a new request is allowed under rate limit"""
        with self.lock:
            now = time.time()
            # Remove requests outside the window
            while self.requests and self.requests[0] < now - self.window_seconds:
                self.requests.popleft()

            if len(self.requests) >= self.max_requests:
                return False

            self.requests.append(now)
            return True

    def get_wait_time(self):
        """Get seconds to wait before next request is allowed"""
        with self.lock:
            if len(self.requests) < self.max_requests:
                return 0

            oldest = self.requests[0]
            wait_until = oldest + self.window_seconds
            return max(0, wait_until - time.time())


class Agent:
    def __init__(self, host: str, username: str, password: str):
        # Store a display name; Speakeasy auth uses provided user/pass below
        self.username = BOT_USER

        # 1) Load local graph (once)
        self.graph = load_graph()

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
            print("[agent] embeddings loaded and attached to Responser")
        except Exception as e:
            print(f"[agent] embeddings not available ({e}); falling back to factual-only")
            self.responser = Responser()

        # 3) Connect to Speakeasy
        self.speakeasy = Speakeasy(host=host, username=username, password=password)
        self.speakeasy.login()  # auto-logout on process end
        print("[agent] logged in to Speakeasy")

        # Dedup guards to prevent double replies
        self.seen = set()          # (room_id, ordinal)
        self.last_ord = {}         # room_id -> last processed ordinal

        # Rate limiting and concurrency control
        self.rate_limiters = {}    # room_id -> RateLimiter
        self.semaphore = Semaphore(MAX_CONCURRENT_REQUESTS)
        self.processing_count = 0
        self.count_lock = Lock()

        # Memory management
        self.message_count = 0
        self.last_cleanup = time.time()
        self.cleanup_interval = 3600  # Clean up every hour

    def _process_with_timeout(self, message: str) -> str:
        """Process a message with timeout protection."""
        import platform

        if platform.system() != 'Windows':
            # Use signal-based timeout on Unix-like systems
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(REQUEST_TIMEOUT)
            try:
                resp = self.responser.generate_response(message, self.graph, WDT, WD)
                resp = (resp or DEFAULT_MSG)
                signal.alarm(0)  # Cancel alarm
                return resp
            finally:
                signal.signal(signal.SIGALRM, old_handler)
        else:
            # Fallback for Windows - no timeout enforcement
            resp = self.responser.generate_response(message, self.graph, WDT, WD)
            return (resp or DEFAULT_MSG)

    def _cleanup_memory(self):
        """Periodic cleanup to prevent memory bloat"""
        now = time.time()
        if now - self.last_cleanup < self.cleanup_interval:
            return

        print("[CLEANUP] Performing periodic memory cleanup...")

        # Clean up old seen messages (keep only last 1000)
        if len(self.seen) > 1000:
            sorted_seen = sorted(self.seen, key=lambda x: (x[0], x[1]))
            self.seen = set(sorted_seen[-1000:])
            print(f"[CLEANUP] Reduced seen set from {len(sorted_seen)} to {len(self.seen)}")

        # Clean up inactive rate limiters (no requests in last hour)
        inactive_rooms = []
        for room_id, limiter in self.rate_limiters.items():
            if limiter.requests and (now - limiter.requests[-1]) > 3600:
                inactive_rooms.append(room_id)

        for room_id in inactive_rooms:
            del self.rate_limiters[room_id]

        if inactive_rooms:
            print(f"[CLEANUP] Removed {len(inactive_rooms)} inactive rate limiters")

        # Clear responser's label cache if it exists
        if hasattr(self.responser, '_label_cache'):
            cache_size = len(self.responser._label_cache)
            if cache_size > 10000:
                self.responser._label_cache.clear()
                print(f"[CLEANUP] Cleared responser label cache ({cache_size} entries)")

        self.last_cleanup = now
        print("[CLEANUP] Memory cleanup completed")

    def listen(self):
        """Main listen loop with basic backoff on transient errors."""
        backoff = 2
        while True:
            try:
                # Periodic memory cleanup
                self._cleanup_memory()

                rooms: List[Chatroom] = self.speakeasy.get_rooms(active=True)
                for room in rooms:
                    # Greet only once per process for this room object
                    if not getattr(room, "initiated", False):
                        try:
                            room.post_messages(
                                f"Hey there! I'm your movie assistant. "
                                f"Ask me anything about films!"
                            )
                            room.initiated = True
                        except Exception as e:
                            print(f"[warn] greeting failed: {e}")

                    # Process only new partner messages
                    for message in room.get_messages(only_partner=True, only_new=True):
                        key = (room.room_id, message.ordinal)

                        # Dedup: skip if we've already processed this ordinal (or a newer one) in this room
                        if room.room_id in self.last_ord and message.ordinal <= self.last_ord[room.room_id]:
                            continue
                        if key in self.seen:
                            continue

                        # Rate limiting check
                        if room.room_id not in self.rate_limiters:
                            self.rate_limiters[room.room_id] = RateLimiter(MAX_REQUESTS_PER_MINUTE)

                        rate_limiter = self.rate_limiters[room.room_id]
                        if not rate_limiter.is_allowed():
                            wait_time = rate_limiter.get_wait_time()
                            print(f"[RATE_LIMIT] room={room.room_id} - rate limit exceeded, waiting {wait_time:.1f}s")
                            try:
                                room.post_messages(
                                    f"Too many requests. Please wait {int(wait_time)} seconds "
                                    f"before asking again."
                                )
                                room.mark_as_processed(message)
                                self.last_ord[room.room_id] = message.ordinal
                            except Exception as e:
                                print(f"[warn] rate limit message failed: {e}")
                            continue

                        # Check concurrent request limit
                        if not self.semaphore.acquire(blocking=False):
                            print(f"[CONCURRENT_LIMIT] room={room.room_id} - too many concurrent requests")
                            try:
                                room.post_messages(
                                    "I'm currently processing too many requests. "
                                    "Please try again in a moment."
                                )
                                room.mark_as_processed(message)
                                self.last_ord[room.room_id] = message.ordinal
                            except Exception as e:
                                print(f"[warn] concurrent limit message failed: {e}")
                            continue

                        self.seen.add(key)

                        try:
                            with self.count_lock:
                                self.processing_count += 1
                                current_count = self.processing_count

                            print(
                                f"[PROC] room={room.room_id} ordinal={message.ordinal} "
                                f"concurrent={current_count} text={message.message!r}"
                            )

                            # Process with timeout protection
                            resp = self._process_with_timeout(message.message)

                        except TimeoutError:
                            print(
                                f"[TIMEOUT] room={room.room_id} ordinal={message.ordinal} - "
                                f"request timed out after {REQUEST_TIMEOUT}s"
                            )
                            resp = (
                                f"Your request took too long to process (>{REQUEST_TIMEOUT}s). "
                                f"Please try a simpler question."
                            )
                        except Exception as e:
                            print(f"[generate_response error] {e}")
                            traceback.print_exc()
                            resp = DEFAULT_MSG
                        finally:
                            self.semaphore.release()
                            with self.count_lock:
                                self.processing_count -= 1

                        # Post + mark processed
                        try:
                            room.post_messages(resp)
                            print(f"[POSTED] room={room.room_id} ordinal={message.ordinal}")
                        except Exception as e:
                            print(f"[warn] post_messages failed: {e}")

                        try:
                            room.mark_as_processed(message)
                            self.last_ord[room.room_id] = message.ordinal
                        except Exception as e:
                            # If marking fails, the platform may resend the same message later.
                            print(f"[warn] mark_as_processed failed: {e}")

                    # Optional: react to new reactions
                    for reaction in room.get_reactions(only_new=True):
                        try:
                            room.post_messages(f"Received your reaction: '{reaction.type}'")
                            room.mark_as_processed(reaction)
                        except Exception as e:
                            print(f"[warn] reaction handling failed: {e}")

                time.sleep(LISTEN_FREQ)
                backoff = 2  # reset on success

            except KeyboardInterrupt:
                print("Agent shutting down…")
                break
            except Exception as e:
                print(f"[listen] transient error: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)  # 2, 4, 8, …, 60 seconds


def _load_env():
    """Load SPEAKEASY configuration from .env"""
    load_dotenv()
    host = os.getenv("SPEAKEASY_HOST", DEFAULT_HOST_URL)
    user = os.getenv("SPEAKEASY_USER", BOT_USER)
    pwd = os.getenv("SPEAKEASY_PASSWORD", BOT_PASS)
    return host, user, pwd


if __name__ == "__main__":
    host, user, pwd = _load_env()
    Agent(host, user, pwd).listen()