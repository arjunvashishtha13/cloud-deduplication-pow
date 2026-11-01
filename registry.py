"""Tag registries: a local JSON file (default, no network) or Firebase Realtime Database (optional)."""
import json
import os


class LocalRegistry:
    def __init__(self, path):
        self.path = path
        self.data = {}
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    self.data = json.load(f)
            except (OSError, ValueError):
                self.data = {}

    def _flush(self):
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2)

    def exists(self, tag):
        return tag in self.data

    def add(self, tag, user, filename):
        self.data.setdefault(tag, {"filename": filename, "owners": []})
        if user not in self.data[tag]["owners"]:
            self.data[tag]["owners"].append(user)
        self._flush()

    def owners(self, tag):
        return list(self.data.get(tag, {}).get("owners", []))


class FirebaseRegistry:
    """Needs `pip install firebase-admin` and YOUR service-account key (never commit it)."""

    def __init__(self, key_path, database_url, root="pow_demo", reset=True):
        import firebase_admin  # imported lazily so the project runs without it
        from firebase_admin import credentials, db
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(key_path), {"databaseURL": database_url})
        self._db = db
        self.root = root
        if reset:
            db.reference(root).delete()

    def exists(self, tag):
        return self._db.reference("%s/%s" % (self.root, tag)).get() is not None

    def add(self, tag, user, filename):
        ref = self._db.reference("%s/%s" % (self.root, tag))
        cur = ref.get() or {"filename": filename, "owners": []}
        owners = cur.get("owners", [])
        if user not in owners:
            owners.append(user)
        ref.set({"filename": cur.get("filename", filename), "owners": owners})

    def owners(self, tag):
        cur = self._db.reference("%s/%s" % (self.root, tag)).get() or {}
        return list(cur.get("owners", []))
