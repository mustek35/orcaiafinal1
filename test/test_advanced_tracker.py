import sys
import types
import unittest
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Stub torch module used by advanced_tracker
torch_mod = types.ModuleType('torch')
cuda_mod = types.SimpleNamespace(is_available=lambda: False)
torch_mod.cuda = cuda_mod
sys.modules['torch'] = torch_mod

# Create dummy deep_sort_realtime module for testing
pkg = types.ModuleType('deep_sort_realtime')
tracker_mod = types.ModuleType('deep_sort_realtime.deepsort_tracker')

class DummyTrack:
    def __init__(self, track_id, bbox, det_cls=0, det_conf=1.0):
        self.track_id = track_id
        self._bbox = bbox
        self.det_class = det_cls
        self.det_conf = det_conf
    def is_confirmed(self):
        return True
    def to_ltrb(self):
        return self._bbox

class DummyDeepSort:
    def __init__(self, *args, **kwargs):
        self.next_id = 0
        self.active = {}
    def update_tracks(self, dets, frame=None):
        tracks = []
        if not dets:
            for tid, bbox in list(self.active.items()):
                pred_bbox = [bbox[0] + 50, bbox[1], bbox[2] + 50, bbox[3]]
                self.active[tid] = pred_bbox
                tracks.append(DummyTrack(tid, pred_bbox))
            return tracks
        bbox, conf, cls = dets[0]
        if self.active:
            tid = next(iter(self.active))
        else:
            tid = self.next_id
            self.next_id += 1
        self.active[tid] = bbox
        tracks.append(DummyTrack(tid, bbox, cls, conf))
        return tracks

tracker_mod.DeepSort = DummyDeepSort
pkg.deepsort_tracker = tracker_mod
sys.modules['deep_sort_realtime'] = pkg
sys.modules['deep_sort_realtime.deepsort_tracker'] = tracker_mod

from core.advanced_tracker import AdvancedTracker

class AdvancedTrackerReassignTest(unittest.TestCase):
    def test_reassign_after_large_shift(self):
        tracker = AdvancedTracker(lost_ttl=2)
        # initial detection
        tracker.update([{'bbox':[100,100,150,150], 'conf':1.0, 'cls':0}])
        # slight movement to build velocity
        tracker.update([{'bbox':[110,100,160,150], 'conf':1.0, 'cls':0}])
        # lost detection
        tracker.update([])
        # reappear far from last bbox but along predicted path
        result = tracker.update([{'bbox':[140,100,190,150], 'conf':1.0, 'cls':0}])
        self.assertEqual(result[0]['id'], 0)

class AdvancedTrackerMinIouTest(unittest.TestCase):
    def test_keep_last_bbox_when_missing(self):
        tracker = AdvancedTracker(lost_ttl=2, min_iou_update=0.5)
        tracker.update([{'bbox':[100,100,150,150], 'conf':1.0, 'cls':0}])
        result = tracker.update([])
        self.assertEqual(result[0]['bbox'], [100,100,150,150])

if __name__ == '__main__':
    unittest.main()