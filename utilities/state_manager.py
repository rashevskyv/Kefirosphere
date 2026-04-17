import os
import json
import platform

STATE_FILE = os.path.join(os.path.dirname(__file__), 'build_state.json')

class StateManager:
    def __init__(self, state_file=STATE_FILE):
        self.state_file = state_file

    def _lock_file(self, f):
        pass

    def _unlock_file(self, f):
        pass

    def get_state(self):
        if not os.path.exists(self.state_file):
            return {}
            
        with open(self.state_file, 'r', encoding='utf-8') as f:
            self._lock_file(f)
            try:
                content = f.read()
                return json.loads(content) if content else {}
            except json.JSONDecodeError:
                return {}
            finally:
                self._unlock_file(f)

    def save_state(self, state):
        # We rewrite the whole state at once
        mode = 'r+' if os.path.exists(self.state_file) else 'w+'
        with open(self.state_file, mode, encoding='utf-8') as f:
            self._lock_file(f)
            try:
                # If reading existing to maybe merge? No, we overwrite with what we were given
                f.seek(0)
                f.truncate()
                json.dump(state, f, indent=4, ensure_ascii=False)
            finally:
                self._unlock_file(f)

    def get(self, key, default=None):
        return self.get_state().get(key, default)

    def set(self, key, value):
        state = self.get_state()
        state[key] = value
        self.save_state(state)

    def update(self, new_data_dict):
        state = self.get_state()
        state.update(new_data_dict)
        self.save_state(state)

# For easy import access
state = StateManager()
