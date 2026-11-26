"""BookSide settings, with compatibility for existing local installations."""
import os


def setting(name, default=None):
    return os.getenv(name, os.getenv(name.replace("BOOKSIDE_", "LEARNEST_"), default))
