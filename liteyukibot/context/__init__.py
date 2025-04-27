class Context:
    def __init__(self):
        self._context = {}

    def set(self, key, value):
        self._context[key] = value

    def get(self, key):
        return self._context.get(key)

    def clear(self):
        self._context.clear()

    def __repr__(self):
        return f"Context({self._context})"