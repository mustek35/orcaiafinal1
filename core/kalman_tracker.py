from collections import deque
from filterpy.kalman import KalmanFilter
import numpy as np

class KalmanBoxTracker:
    count = 0 # Class variable to assign unique IDs to trackers
    
    def __init__(self, bbox, cls=None, conf=None): # bbox is [x1, y1, x2, y2]
        # State is [cx, cy, w, h, d_cx, d_cy] (center_x, center_y, width, height, vel_cx, vel_cy)
        self.kf = KalmanFilter(dim_x=6, dim_z=4) # State: 6, Measurement: 4
        dt = 1.0 # Time step

        # State Transition Matrix (F)
        self.kf.F = np.array([[1, 0, 0, 0, dt, 0],  # cx = cx + dt * d_cx
                              [0, 1, 0, 0, 0, dt],  # cy = cy + dt * d_cy
                              [0, 0, 1, 0, 0, 0],  # w = w (assuming constant w for now)
                              [0, 0, 0, 1, 0, 0],  # h = h (assuming constant h for now)
                              [0, 0, 0, 0, 1, 0],  # d_cx = d_cx
                              [0, 0, 0, 0, 0, 1]]) # d_cy = d_cy

        # Measurement Function (H) - We measure cx, cy, w, h
        self.kf.H = np.array([[1, 0, 0, 0, 0, 0],
                              [0, 1, 0, 0, 0, 0],
                              [0, 0, 1, 0, 0, 0],
                              [0, 0, 0, 1, 0, 0]])

        # Measurement Uncertainty (R) - Adjust based on detection noise
        # Increased R for w,h as they might be less stable than cx,cy from detections
        self.kf.R = np.diag([10.**2, 10.**2, 20.**2, 20.**2]) # Use variance for R

        # Process Noise (Q) - uncertainty in the model
        # Assuming velocities are somewhat constant, but allow for some change
        q_vel = 0.1 # Smaller value means more confidence in constant velocity
        q_pos_w_h = 0.5 # Smaller value means more confidence in the state
        self.kf.Q = np.diag([q_pos_w_h, q_pos_w_h, q_pos_w_h, q_pos_w_h, q_vel, q_vel])
        # self.kf.Q = self.kf.Q * dt # Option: Scale by dt if dt can vary significantly. For dt=1, no change.

        # Initial State Covariance (P)
        self.kf.P = np.diag([10.**2, 10.**2, 20.**2, 20.**2, 100.**2, 100.**2])


        self.id = KalmanBoxTracker.count
        KalmanBoxTracker.count += 1
        
        # Initialization of tracker attributes as per requirements
        self.time_since_update = 0
        self.hits = 1 # Starts with a hit (the initial detection)
        self.hit_streak = 1 # Starts with a hit streak of 1
        self.age = 1 # Starts with age 1 (first frame it appears)
        
        self.last_cls = cls
        self.last_conf = conf
        self.confidence_history = deque(maxlen=5)
        
        # New attributes for motion detection logic
        self.last_center_position = None 
        self.frames_consecutivos_detenido = 0 # Initialized here

        self._iniciar_kf_state(bbox) # Private method to set initial KF state from bbox
        # Initialize last_center_position with the initial bbox's center
        initial_cwh = self._bbox_to_cwh(bbox)
        self.last_center_position = (initial_cwh[0], initial_cwh[1])


    def _bbox_to_cwh(self, bbox):
        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1
        if w <= 0: w = 1 # Ensure width is positive
        if h <= 0: h = 1 # Ensure height is positive
        cx = x1 + w / 2
        cy = y1 + h / 2
        return np.array([cx, cy, w, h])

    def _iniciar_kf_state(self, bbox): # Renamed from 'iniciar' to avoid confusion with __init__ process
        cwh = self._bbox_to_cwh(bbox)
        self.kf.x = np.array([cwh[0], cwh[1], cwh[2], cwh[3], 0, 0]).reshape(6, 1) # Initial velocities are 0

    def update(self, bbox, cls=None, conf=None): # bbox is [x1, y1, x2, y2]
        """
        Updates the state vector with observed bbox.
        """
        self.time_since_update = 0 # Reset as it got an update
        self.hits += 1
        self.hit_streak += 1 # Incremented on each successful update
        
        if cls is not None:
            self.last_cls = cls
        if conf is not None:
            self.last_conf = conf
            self.confidence_history.append(conf)
            
        measured_cwh = self._bbox_to_cwh(bbox)
        self.kf.update(measured_cwh.reshape(4, 1))

    def predict(self):
        """
        Advances the state vector and returns the predicted bounding box.
        Returns: [x1, y1, x2, y2]
        """
        # Ensure current w,h in state are positive before prediction if they somehow became non-positive
        if self.kf.x[2,0] <= 0: self.kf.x[2,0] = 1 
        if self.kf.x[3,0] <= 0: self.kf.x[3,0] = 1

        self.kf.predict()
        self.age += 1 # Tracker ages with each frame prediction
        
        # If time_since_update is > 0, it means predict() was called in the previous frame
        # but update() was not. So, the hit streak is broken.
        if self.time_since_update > 0: 
            self.hit_streak = 0
        self.time_since_update += 1 # Incremented each time predict is called

        cx, cy, w, h = self.kf.x[0,0], self.kf.x[1,0], self.kf.x[2,0], self.kf.x[3,0]

        if w <= 0: w = 1 
        if h <= 0: h = 1
            
        x1 = cx - w / 2
        y1 = cy - h / 2
        x2 = cx + w / 2
        y2 = cy + h / 2
        return np.array([x1, y1, x2, y2])

    def get_state(self):
        """
        Returns the current bounding box estimate.
        Returns: [x1, y1, x2, y2]
        """
        cx, cy, w, h = self.kf.x[0,0], self.kf.x[1,0], self.kf.x[2,0], self.kf.x[3,0]
        
        if w <= 0: w = 1
        if h <= 0: h = 1

        x1 = cx - w / 2
        y1 = cy - h / 2
        x2 = cx + w / 2
        y2 = cy + h / 2
        return np.array([x1, y1, x2, y2])