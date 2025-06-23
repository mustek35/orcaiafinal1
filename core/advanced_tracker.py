from collections import defaultdict
from deep_sort_realtime.deepsort_tracker import DeepSort
import torch
import time
from logging_utils import get_logger

logger = get_logger(__name__)

def _iou(boxA, boxB):
    """Compute IoU between two boxes given as [x1, y1, x2, y2]."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interW = max(0, xB - xA)
    interH = max(0, yB - yA)
    interArea = interW * interH
    if interArea == 0:
        return 0.0
    boxAArea = max(0, boxA[2] - boxA[0]) * max(0, boxA[3] - boxA[1])
    boxBArea = max(0, boxB[2] - boxB[0]) * max(0, boxB[3] - boxB[1])
    union = boxAArea + boxBArea - interArea
    if union == 0:
        return 0.0
    return interArea / union

class AdvancedTracker:
    """Wrapper around DeepSort tracker maintaining history of track centers."""

    MOVEMENT_HISTORY_STEPS = 7
    MOVEMENT_THRESHOLD = 5.0
    MOVEMENT_SMOOTHING_FRAMES = 5

    def __init__(self, max_age=30, n_init=3, conf_threshold=0.25, device="cpu", lost_ttl=5):
        use_gpu = device != "cpu" and torch.cuda.is_available()

        self.tracker = DeepSort(
            max_age=max_age,
            n_init=n_init,
            embedder='mobilenet',
            embedder_gpu=use_gpu,
            half=use_gpu,
            nms_max_overlap=1.0,
            bgr=True
        )
        self.track_history = defaultdict(list)  # track_id -> list of (cx, cy)
        self.track_meta = {}  # track_id -> (cls, conf)
        self.moving_flags = defaultdict(list)  # track_id -> list of recent moving bools
        self.conf_threshold = conf_threshold
        self.last_result = {}  # track_id -> last returned result dict
        self.lost_counts = defaultdict(int)  # track_id -> frames since last seen
        self.lost_ttl = lost_ttl

    def update(self, detections, frame=None):
        start_time = time.time()

        formatted = []
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            conf = det.get('conf', 1.0)
            cls = det.get('cls', 0)
            formatted.append([[x1, y1, x2, y2], conf, cls])

        tracks = self.tracker.update_tracks(formatted, frame=frame)
        results = []
        active_ids = set()
        detections_boxes = [d['bbox'] for d in detections]
        for t in tracks:
            if not t.is_confirmed():
                continue
            track_id = t.track_id
            pred_bbox = t.to_ltrb()
            best_bbox = pred_bbox
            best_iou = 0.0
            for det_box in detections_boxes:
                iou_val = _iou(pred_bbox, det_box)
                if iou_val > best_iou:
                    best_iou = iou_val
                    best_bbox = det_box
            bbox = best_bbox
            cls = getattr(t, 'det_class', None)
            conf = getattr(t, 'det_conf', None)
            if cls is None:
                stored_cls, stored_conf = self.track_meta.get(track_id, (None, None))
                cls = stored_cls
                if conf is None:
                    conf = stored_conf
            else:
                self.track_meta[track_id] = (cls, conf)
            if conf is None:
                conf = 0.0
            if conf < self.conf_threshold:
                continue
            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
            centers = self.track_history[track_id]
            centers.append((cx, cy))
            if len(centers) > 30:
                centers.pop(0)
            moving = None

            if len(centers) >= self.MOVEMENT_HISTORY_STEPS + 1:
                window = centers[-self.MOVEMENT_HISTORY_STEPS - 1:-1]
                mean_cx = sum(p[0] for p in window) / self.MOVEMENT_HISTORY_STEPS
                mean_cy = sum(p[1] for p in window) / self.MOVEMENT_HISTORY_STEPS
                dist_sq = (cx - mean_cx) ** 2 + (cy - mean_cy) ** 2

                instant = dist_sq ** 0.5 > self.MOVEMENT_THRESHOLD
                flags = self.moving_flags[track_id]
                flags.append(instant)
                if len(flags) > self.MOVEMENT_SMOOTHING_FRAMES:
                    flags.pop(0)
                moving = sum(flags) > len(flags) // 2

            result = {
                'bbox': bbox,
                'id': track_id,
                'cls': cls,
                'conf': conf,
                'centers': list(centers),
                'moving': moving,
            }
            results.append(result)
            active_ids.add(track_id)
            self.last_result[track_id] = result
            self.lost_counts[track_id] = 0

        for tid in list(self.last_result.keys()):
            if tid not in active_ids:
                self.lost_counts[tid] += 1
                if self.lost_counts[tid] <= self.lost_ttl:
                    results.append(self.last_result[tid])
                else:
                    logger.info(f"Track {tid}: Removed after {self.lost_counts[tid]} lost frames")
                    self.track_history.pop(tid, None)
                    self.track_meta.pop(tid, None)
                    self.moving_flags.pop(tid, None)
                    self.last_result.pop(tid, None)
                    self.lost_counts.pop(tid, None)

        # Cleanup ghost tracks
        ghost_tracks = []
        for tid in list(self.last_result.keys()):
            if tid not in active_ids and self.lost_counts[tid] > 3:
                last_bbox = self.last_result[tid]['bbox']
                last_center = ((last_bbox[0] + last_bbox[2])/2, (last_bbox[1] + last_bbox[3])/2)
                
                # Check distance to current detections
                min_dist = float('inf')
                for det in detections:
                    det_bbox = det['bbox']
                    det_center = ((det_bbox[0] + det_bbox[2])/2, (det_bbox[1] + det_bbox[3])/2)
                    dist = ((last_center[0] - det_center[0])**2 + (last_center[1] - det_center[1])**2)**0.5
                    min_dist = min(min_dist, dist)
                
                if min_dist > 200:  # Threshold for ghost detection
                    ghost_tracks.append((str(tid), f"Too far from detections ({min_dist:.0f}px)"))
        
        if ghost_tracks:
            logger.info(f"Removed {len(ghost_tracks)} ghost tracks: {ghost_tracks}")
            for tid_str, reason in ghost_tracks:
                tid = int(tid_str)
                self.track_history.pop(tid, None)
                self.track_meta.pop(tid, None)
                self.moving_flags.pop(tid, None)
                self.last_result.pop(tid, None)
                self.lost_counts.pop(tid, None)

        end_time = time.time()
        elapsed_ms = (end_time - start_time) * 1000
        logger.debug("⏱️ Frame procesado en %.2f ms", elapsed_ms)

        return results