import os
import sys

import frappe
from frappe.model.document import Document

# Make the sibling `shared/` package (tap_lms/shared/) resolvable as a bare
# top-level `shared` import, independent of tap_app/api/__init__.py having
# been imported anywhere in this process first.
#
# tap_app/api/__init__.py patches sys.path the same way, but that patch
# only takes effect once something under tap_app.api is actually imported
# -- and nothing on this doctype's own save path goes through tap_app.api.
# Saving Shared Settings from the desk UI goes
# frappe.desk.form.save.savedocs -> Document.save -> this file's on_update
# directly, with no prior import of tap_app.api anywhere in that call
# chain, so relying on tap_app/api/__init__.py's patch here would leave
# `from shared.config.settings_cache import invalidate_config_cache` raising
# ModuleNotFoundError on every save made from the desk UI, a bench console
# session, or a migration -- any process that never happens to import
# tap_app.api first. This file must therefore ensure `shared` is importable
# on its own, the same way tap_app/api/__init__.py does for its own call
# path, rather than depending on that other module having already run.
#
# _APP_ROOT here is tap_lms/ (the app root), reached by the same number of
# directory levels up from this file's own location
# (tap_lms/tap_lms/doctype/shared_settings/shared_settings.py) as
# tap_app/api/__init__.py computes from its own location -- both resolve to
# the same directory, so this patch and that one are idempotent with each
# other regardless of which one runs first in a given process.
_APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)


class SharedSettings(Document):
    def on_update(self):
        from shared.config.settings_cache import invalidate_config_cache
        invalidate_config_cache()