import math
import time
from collections import Counter, deque


class GestureRecognizer:
    """Advanced, smoothed hand-gesture recognizer for AirDash."""

    def __init__(self):
        # Swipe tracking
        self.past_positions = deque(maxlen=14)
        self.past_timestamps = deque(maxlen=14)

        # Temporal smoothing for stable output
        self._recent_predictions = deque(maxlen=7)
        self._last_stable = "Unknown"
        self._last_swipe_ts = 0.0
        self._unknown_streak = 0
        self._unknown_release_frames = 1
        self._pinch_active = False
        self._pinch_candidate_frames = 0

        # Tunable thresholds
        self.pinch_enter_thresh = 0.21
        self.pinch_exit_thresh = 0.29
        self.pinch_confirm_frames = 1
        self.swipe_dx_thresh = 0.14
        self.swipe_dy_thresh = 0.14
        self.swipe_min_interval = 0.28
        self.stable_ratio = 0.45
        self.confidence_floor = 0.68
        self.hold_ratio = 0.34

    @staticmethod
    def _distance(p1, p2):
        return math.dist([p1.x, p1.y], [p2.x, p2.y])

    def _palm_scale(self, landmarks):
        # Palm size proxy used for normalization.
        wrist = landmarks[0]
        index_mcp = landmarks[5]
        pinky_mcp = landmarks[17]
        scale = (self._distance(wrist, index_mcp) + self._distance(wrist, pinky_mcp)) / 2.0
        return max(scale, 1e-5)

    def _finger_states(self, landmarks):
        """Return robust extended/curl state per finger."""
        wrist = landmarks[0]
        index_mcp = landmarks[5]

        fingers = {"thumb": False, "index": False, "middle": False, "ring": False, "pinky": False}

        # Thumb: distance + direction combined heuristic
        thumb_tip = landmarks[4]
        thumb_ip = landmarks[3]
        thumb_cmc = landmarks[1]
        thumb_dist_gain = self._distance(thumb_tip, index_mcp) > self._distance(thumb_ip, index_mcp) * 1.08
        thumb_from_palm = self._distance(thumb_tip, wrist) > self._distance(thumb_cmc, wrist) * 1.18
        fingers["thumb"] = thumb_dist_gain and thumb_from_palm

        # Other fingers: tip farther than PIP and PIP farther than MCP (distance from wrist)
        triplets = {
            "index": (8, 6, 5),
            "middle": (12, 10, 9),
            "ring": (16, 14, 13),
            "pinky": (20, 18, 17),
        }
        for name, (tip_i, pip_i, mcp_i) in triplets.items():
            tip = landmarks[tip_i]
            pip = landmarks[pip_i]
            mcp = landmarks[mcp_i]
            tip_far = self._distance(tip, wrist)
            pip_far = self._distance(pip, wrist)
            mcp_far = self._distance(mcp, wrist)
            fingers[name] = (tip_far > pip_far * 1.05) and (pip_far > mcp_far * 1.01)

        return fingers

    def get_finger_states(self, landmarks):
        """Public accessor used by custom-gesture builder/runtime matcher."""
        return self._finger_states(landmarks)

    def _detect_swipe(self, landmarks, is_open_palm):
        now = time.time()
        wrist = landmarks[0]
        self.past_positions.append((wrist.x, wrist.y))
        self.past_timestamps.append(now)

        if not is_open_palm or len(self.past_positions) < 8:
            return None
        if now - self._last_swipe_ts < self.swipe_min_interval:
            return None

        x0, y0 = self.past_positions[0]
        x1, y1 = self.past_positions[-1]
        dx = x1 - x0
        dy = y1 - y0

        # Prefer dominant axis motion to avoid diagonal noise.
        if abs(dx) > abs(dy) * 1.25:
            if dx <= -self.swipe_dx_thresh:
                self._last_swipe_ts = now
                return "Swipe_Left"
            if dx >= self.swipe_dx_thresh:
                self._last_swipe_ts = now
                return "Swipe_Right"

        if abs(dy) > abs(dx) * 1.25:
            if dy <= -self.swipe_dy_thresh:
                self._last_swipe_ts = now
                return "Swipe_Up"
            if dy >= self.swipe_dy_thresh:
                self._last_swipe_ts = now
                return "Swipe_Down"

        return None

    def _raw_detect(self, landmarks):
        fingers = self._finger_states(landmarks)
        up_count = sum(fingers.values())

        palm_scale = self._palm_scale(landmarks)
        pinch_dist = self._distance(landmarks[4], landmarks[8]) / palm_scale
        pinch_shape = (
            fingers["index"]
            and not fingers["middle"]
            and not fingers["ring"]
            and not fingers["pinky"]
        )

        # Pinch hysteresis:
        # - enter only after a couple of consecutive tight-pinch frames
        # - exit quickly once fingers separate enough
        if self._pinch_active:
            if (pinch_dist > self.pinch_exit_thresh) or (not pinch_shape):
                self._pinch_active = False
                self._pinch_candidate_frames = 0
            else:
                return "Pinch", 0.95
        else:
            if pinch_shape and pinch_dist < self.pinch_enter_thresh:
                self._pinch_candidate_frames += 1
                if self._pinch_candidate_frames >= self.pinch_confirm_frames:
                    self._pinch_active = True
                    return "Pinch", 0.95
            else:
                self._pinch_candidate_frames = 0

        if up_count == 0:
            return "Closed Fist", 0.90

        open_palm = up_count >= 4 and fingers["index"] and fingers["middle"]
        swipe = self._detect_swipe(landmarks, open_palm)
        if swipe:
            return swipe, 0.93

        if open_palm:
            return "Open Palm", 0.88

        if fingers["index"] and fingers["middle"] and not fingers["ring"] and not fingers["pinky"]:
            return "Peace", 0.90

        if fingers["pinky"] and not fingers["index"] and not fingers["middle"] and not fingers["ring"]:
            return "Pinky_Only", 0.90

        if fingers["index"] and fingers["pinky"] and fingers["thumb"] and not fingers["middle"] and not fingers["ring"]:
            return "Spiderman", 0.90

        return "Unknown", 0.0

    def detect_gesture(self, landmarks):
        gesture, conf = self._raw_detect(landmarks)

        # Keep fast gestures/snaps responsive.
        if gesture.startswith("Swipe_") or gesture in {"Pinch", "Closed Fist"}:
            self._recent_predictions.append(gesture)
            self._last_stable = gesture
            self._unknown_streak = 0
            return gesture

        self._recent_predictions.append(gesture)
        if not self._recent_predictions:
            return "Unknown"

        if gesture == "Unknown":
            self._unknown_streak += 1
        else:
            self._unknown_streak = 0

        if self._unknown_streak >= self._unknown_release_frames:
            self._last_stable = "Unknown"
            return "Unknown"

        counts = Counter(self._recent_predictions)
        best, count = counts.most_common(1)[0]
        stability = count / len(self._recent_predictions)

        if best != "Unknown" and stability >= self.stable_ratio and conf >= self.confidence_floor:
            self._last_stable = best
            return best

        # Avoid jitter by holding previous stable gesture briefly.
        if self._last_stable != "Unknown" and stability >= self.hold_ratio:
            return self._last_stable

        return "Unknown"
