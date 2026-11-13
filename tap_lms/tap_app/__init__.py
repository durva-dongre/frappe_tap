import os
import sys

_APP_ROOT = os.path.dirname(__file__)
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

__version__ = '0.0.1'
