from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition
from collections import defaultdict

class CrossLineCounter(QThread):
    """Count objects crossing a user defined line without blocking the UI.

    The line is defined by two points in relative coordinates (0-1 range).
    Crossing is detected by monitoring the sign change of the object center
    relative to the line. The optional ``orientation`` parameter currently only
    defines the default orientation for display and does not affect counting.
    """

    # counts_updated emits a dictionary with two keys: "Entrada" and "Salida".
    # Each maps to another dict of label -> count.
    counts_updated = pyqtSignal(dict)
    log_signal = pyqtSignal(str)
    cross_event = pyqtSignal(dict)

    def __init__(self, line=((0.5,0.2),(0.5,0.8)), orientation='vertical', parent=None):
        super().__init__(parent)
        self.line = line
        self.orientation = orientation
        self.active = True
        self._queue = []
        self._mutex = QMutex()
        self._wait = QWaitCondition()
        self.running = True
        self.prev_sides = {}
        # Dictionary structure: {"Entrada": defaultdict(int), "Salida": defaultdict(int)}
        self.counts = {"Entrada": defaultdict(int), "Salida": defaultdict(int)}

    def update_boxes(self, boxes, frame_size):
        if not self.active:
            return
        self._mutex.lock()
        self._queue.append((boxes, frame_size))
        self._wait.wakeAll()
        self._mutex.unlock()

    def set_line(self, line):
        """Update line position expressed in relative coordinates."""
        self.line = line
        self.prev_sides.clear()

    def stop(self):
        self.running = False
        self.active = False
        self._wait.wakeAll()

    def _process(self, boxes, frame_size):
        width, height = frame_size
        x1_rel, y1_rel = self.line[0]
        x2_rel, y2_rel = self.line[1]
        line_x1 = x1_rel * width
        line_y1 = y1_rel * height
        line_x2 = x2_rel * width
        line_y2 = y2_rel * height
        dx = line_x2 - line_x1
        dy = line_y2 - line_y1
        for b in boxes:
            tid = b.get('id')
            x1, y1, x2, y2 = b.get('bbox', (0, 0, 0, 0))
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            value = (cx - line_x1) * dy - (cy - line_y1) * dx
            side = 'pos' if value >= 0 else 'neg'

            prev_side = self.prev_sides.get(tid)
            crossed = prev_side is not None and prev_side != side

            if crossed:
                entrada = prev_side == 'neg' and side == 'pos'
                cls = b.get('cls', 0)
                label = {0: 'personas', 2: 'autos', 8: 'barcos', 9: 'barcos'}.get(cls, 'objetos')
                direc = 'Entrada' if entrada else 'Salida'
                self.counts[direc][label] += 1
                count_for_label = self.counts[direc][label]
                self.log_signal.emit(f"{direc}: {count_for_label} {label}")
                self.cross_event.emit({
                    'id': tid,
                    'cls': cls,
                    'direction': direc,
                })

            self.prev_sides[tid] = side

        # Convert defaultdicts to plain dicts before emitting
        plain = {k: dict(v) for k, v in self.counts.items()}
        self.counts_updated.emit(plain)

    def run(self):
        while self.running:
            self._mutex.lock()
            if not self._queue:
                self._wait.wait(self._mutex, 100)
                self._mutex.unlock()
                continue
            boxes, size = self._queue.pop(0)
            self._mutex.unlock()
            self._process(boxes, size)
        
