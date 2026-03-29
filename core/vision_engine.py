import cv2
import mediapipe as mp
import threading
import time
import winsound
from collections import deque
from core.gesture_recognizer import GestureRecognizer
from core.action_mapper import ActionMapper
import math


class _NoHandResults:
    multi_hand_landmarks = None
    multi_handedness = None


class _NoHandsContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def process(self, _rgb_image):
        return _NoHandResults()


class VisionEngine:
    def __init__(self, update_image_callback=None, update_gesture_callback=None, camera_ready_callback=None, update_hands_callback=None):
        self._run_flag = True
        self._camera_active = True
        self._camera_just_opened = False
        self._camera_lock = threading.Lock()
        self._camera_index = 0
        self._requested_camera_index = None
        self._target_fps = 60
        self._render_device = "cpu"
        self._gpu_available = False
        self._cuda_available = False
        self._opencl_available = False
        try:
            self._cuda_available = cv2.cuda.getCudaEnabledDeviceCount() > 0
        except Exception:
            self._cuda_available = False
        try:
            self._opencl_available = bool(cv2.ocl.haveOpenCL())
            if self._opencl_available:
                cv2.ocl.setUseOpenCL(True)
        except Exception:
            self._opencl_available = False
        self._gpu_available = self._cuda_available or self._opencl_available
        self.gesture_recognizer = GestureRecognizer()
        self.action_mapper = ActionMapper()
        self.processing_paused = False
        self.mp_hands = None
        self.mp_drawing = None
        self._mediapipe_available = False
        self._mediapipe_error_message = ""
        try:
            if hasattr(mp, "solutions") and hasattr(mp.solutions, "hands"):
                self.mp_hands = mp.solutions.hands
                self.mp_drawing = mp.solutions.drawing_utils
                self._mediapipe_available = True
            else:
                self._mediapipe_error_message = "MediaPipe hand solutions not available in installed package."
        except Exception as e:
            self._mediapipe_error_message = f"MediaPipe initialization failed: {e}"
        self.theme = "Dr. Strange" # Default
        self._gesture_confirm_frames = 1
        self._gesture_release_frames = 1
        self._repeatable_gestures = {"Pinch", "Closed Fist", "Open Palm", "Peace", "Pinky_Only", "Spiderman"}
        self._dynamic_gesture_prefixes = ("Swipe_",)
        self._gesture_repeat_interval = 0.45
        self._pending_gesture = None
        self._pending_count = 0
        self._active_gesture = None
        self._release_count = 0
        self._last_trigger_ts = 0.0
        self._hand_motion_history = {
            "left": deque(maxlen=10),
            "right": deque(maxlen=10),
            "unknown": deque(maxlen=10),
        }

        self.update_image_callback = update_image_callback
        self.update_gesture_callback = update_gesture_callback
        self.camera_ready_callback = camera_ready_callback
        self.update_hands_callback = update_hands_callback

        self.thread = threading.Thread(target=self._run, daemon=True)

    @staticmethod
    def _safe_cap_set(cap, prop, value):
        """Best-effort camera property setter; never let backend errors crash init."""
        if cap is None:
            return False
        try:
            return bool(cap.set(prop, value))
        except Exception:
            return False

    @staticmethod
    def _safe_read_frame(cap):
        if cap is None:
            return False, None
        try:
            ok, frame = cap.read()
            if not ok or frame is None:
                return False, None
            return True, frame
        except Exception:
            return False, None

    def start(self):
        self.thread.start()

    def set_camera_active(self, active):
        self._camera_active = active
        if active:
            # Clear stale hand-position history so old positions don't
            # trigger phantom swipe gestures the moment the feed resumes.
            self.gesture_recognizer.past_positions.clear()
            self._reset_gesture_stabilizer()

    def _reset_gesture_stabilizer(self):
        self._pending_gesture = None
        self._pending_count = 0
        self._active_gesture = None
        self._release_count = 0
        self._last_trigger_ts = 0.0

    def _stabilize_gesture(self, raw_gesture):
        """
        Universal gesture hysteresis for all current and future gesture labels.
        Returns (stable_gesture_or_none, should_trigger_action).
        """
        valid = raw_gesture and raw_gesture not in {"None", "Unknown"}
        if valid:
            now = time.time()
            is_dynamic = any(raw_gesture.startswith(prefix) for prefix in self._dynamic_gesture_prefixes)
            confirm_frames = 1 if is_dynamic else self._gesture_confirm_frames

            if raw_gesture == self._pending_gesture:
                self._pending_count += 1
            else:
                self._pending_gesture = raw_gesture
                self._pending_count = 1

            self._release_count = 0

            if self._active_gesture == raw_gesture:
                # Optional repeat trigger for held static gestures.
                if (
                    raw_gesture in self._repeatable_gestures
                    and (now - self._last_trigger_ts) >= self._gesture_repeat_interval
                ):
                    self._last_trigger_ts = now
                    return raw_gesture, True
                return raw_gesture, False

            if self._pending_count >= confirm_frames:
                self._active_gesture = raw_gesture
                self._last_trigger_ts = now
                return raw_gesture, True

            return None, False

        self._pending_gesture = None
        self._pending_count = 0

        if self._active_gesture is not None:
            self._release_count += 1
            if self._release_count >= self._gesture_release_frames:
                self._active_gesture = None
                self._release_count = 0
        return None, False

    def set_camera_index(self, index):
        try:
            idx = int(index)
        except (TypeError, ValueError):
            return
        if idx < 0:
            return
        with self._camera_lock:
            self._requested_camera_index = idx

    def get_camera_index(self):
        with self._camera_lock:
            if self._requested_camera_index is not None:
                return self._requested_camera_index
            return self._camera_index

    def set_target_fps(self, fps):
        try:
            value = int(fps)
        except (TypeError, ValueError):
            return
        # 0 means uncapped / max speed.
        if value < 0:
            return
        with self._camera_lock:
            self._target_fps = value

    def get_target_fps(self):
        with self._camera_lock:
            return self._target_fps

    def get_available_render_devices(self):
        # Keep GPU selectable in UI even when acceleration backend is missing.
        # Engine will gracefully fallback to CPU if GPU backend isn't available.
        return ["cpu", "gpu"]

    def set_render_device(self, device):
        requested = str(device or "").strip().lower()
        if requested not in {"cpu", "gpu"}:
            return {"ok": False, "active": self.get_render_device(), "message": "Invalid render mode"}
        with self._camera_lock:
            if requested == "cpu":
                self._render_device = "cpu"
                return {"ok": True, "active": "cpu", "message": "CPU mode enabled"}

            if self._gpu_available:
                self._render_device = "gpu"
                if self._cuda_available:
                    return {"ok": True, "active": "gpu", "message": "GPU mode enabled (CUDA)"}
                if self._opencl_available:
                    return {"ok": True, "active": "gpu", "message": "GPU mode enabled (OpenCL)"}
                return {"ok": True, "active": "gpu", "message": "GPU mode enabled"}

            self._render_device = "cpu"
            return {
                "ok": False,
                "active": "cpu",
                "message": "GPU is not connecting."
            }

    def get_render_device(self):
        with self._camera_lock:
            return self._render_device

    def _build_hand_snapshot(self, results):
        snapshot = []
        hand_landmarks_list = results.multi_hand_landmarks or []
        handedness_list = results.multi_handedness or []

        for idx, hand_landmarks in enumerate(hand_landmarks_list):
            label = "Unknown"
            try:
                if idx < len(handedness_list):
                    label = handedness_list[idx].classification[0].label
            except Exception:
                label = "Unknown"
            fingers = self.gesture_recognizer.get_finger_states(hand_landmarks.landmark)
            wrist = hand_landmarks.landmark[0]
            snapshot.append({
                "hand": label,
                "fingers": fingers,
                "wrist": {"x": wrist.x, "y": wrist.y},
            })
        return snapshot

    def _update_motion_history(self, hands_snapshot):
        seen = set()
        for hand in hands_snapshot:
            label = str(hand.get("hand", "Unknown")).strip().lower()
            if label not in self._hand_motion_history:
                label = "unknown"
            wrist = hand.get("wrist") or {}
            point = (wrist.get("x"), wrist.get("y"))
            if point[0] is None or point[1] is None:
                continue
            self._hand_motion_history[label].append(point)
            seen.add(label)

    def _classify_motion(self, hand_label):
        label = str(hand_label or "unknown").strip().lower()
        if label not in self._hand_motion_history:
            label = "unknown"
        history = self._hand_motion_history[label]
        if len(history) < 4:
            return "static"
        x0, y0 = history[0]
        x1, y1 = history[-1]
        dx = x1 - x0
        dy = y1 - y0
        if abs(dx) < 0.08 and abs(dy) < 0.08:
            return "static"
        if abs(dx) > abs(dy) * 1.2:
            return "left" if dx < 0 else "right"
        if abs(dy) > abs(dx) * 1.2:
            return "up" if dy < 0 else "down"
        return "moving"

    @staticmethod
    def _matches_finger_rule(required, actual):
        req = str(required or "any").strip().lower()
        if req == "any":
            return True
        if req == "up":
            return bool(actual)
        if req == "down":
            return not bool(actual)
        return True

    def _matches_motion_rule(self, required, hand_label):
        req = str(required or "any").strip().lower()
        if req == "any":
            return True
        motion = self._classify_motion(hand_label)
        if req == "move":
            return motion in {"left", "right", "up", "down", "moving"}
        return motion == req

    def _matches_custom_rule(self, custom_rule, hands_snapshot):
        if not custom_rule:
            return False

        hand_mode = str(custom_rule.get("hand_mode", "any")).strip().lower()
        left_req = custom_rule.get("left_fingers", {})
        right_req = custom_rule.get("right_fingers", {})
        any_req = custom_rule.get("any_fingers", {})
        left_motion = custom_rule.get("left_motion", "any")
        right_motion = custom_rule.get("right_motion", "any")
        any_motion = custom_rule.get("any_motion", "any")

        left_hand = next((h for h in hands_snapshot if str(h.get("hand", "")).lower() == "left"), None)
        right_hand = next((h for h in hands_snapshot if str(h.get("hand", "")).lower() == "right"), None)

        def hand_matches(requirements, hand_data):
            if not requirements:
                return True
            if not hand_data:
                return False
            actual = hand_data.get("fingers", {})
            for finger_name, req_state in requirements.items():
                if not self._matches_finger_rule(req_state, actual.get(finger_name, False)):
                    return False
            return True

        if hand_mode == "both":
            return (
                hand_matches(left_req, left_hand)
                and hand_matches(right_req, right_hand)
                and self._matches_motion_rule(left_motion, "left")
                and self._matches_motion_rule(right_motion, "right")
            )
        if hand_mode == "left":
            return hand_matches(left_req, left_hand) and self._matches_motion_rule(left_motion, "left")
        if hand_mode == "right":
            return hand_matches(right_req, right_hand) and self._matches_motion_rule(right_motion, "right")

        # any one hand
        if any_req:
            for hand in hands_snapshot:
                if hand_matches(any_req, hand) and self._matches_motion_rule(any_motion, hand.get("hand", "unknown")):
                    return True
            return False
        # If no explicit any-hand requirements, fallback to left/right templates.
        return (
            (hand_matches(left_req, left_hand) and self._matches_motion_rule(left_motion, "left"))
            or (hand_matches(right_req, right_hand) and self._matches_motion_rule(right_motion, "right"))
        )

    def _detect_custom_gesture(self, hands_snapshot):
        if not hands_snapshot:
            return None
        for gesture_name, mapping in self.action_mapper.mappings.items():
            custom_rule = mapping.get("custom_rule")
            if self._matches_custom_rule(custom_rule, hands_snapshot):
                return gesture_name
        return None

    def _run(self):
        cap = None

        if self._mediapipe_available:
            hands_context = self.mp_hands.Hands(
                model_complexity=1,
                min_detection_confidence=0.55,
                min_tracking_confidence=0.60,
                max_num_hands=2,
            )
        else:
            hands_context = _NoHandsContext()
            if self.update_gesture_callback:
                self.update_gesture_callback("Hand Tracking Unavailable")
            if self._mediapipe_error_message:
                print(self._mediapipe_error_message)

        with hands_context as hands:

            while self._run_flag:
                with self._camera_lock:
                    requested_index = self._requested_camera_index
                    active_index = self._camera_index
                    render_device = self._render_device

                if requested_index is not None:
                    with self._camera_lock:
                        self._camera_index = requested_index
                        self._requested_camera_index = None
                        active_index = self._camera_index
                    if cap is not None:
                        cap.release()
                        cap = None
                    self._camera_just_opened = False

                if not self._camera_active or self.processing_paused:
                    # Release camera hardware when FULLY paused (camera_active=False)
                    if not self._camera_active and cap is not None:
                        cap.release()
                        cap = None
                    time.sleep(0.05)
                    continue

                # Open camera if not already open
                if cap is None:
                    try:
                        with self._camera_lock:
                            target_fps = self._target_fps
                        
                        # Prefer DirectShow on Windows for faster open time,
                        # then fall back to MSMF/default for compatibility.
                        cap = None
                        backends = []
                        if hasattr(cv2, "CAP_DSHOW"):
                            backends.append(("CAP_DSHOW", cv2.CAP_DSHOW))
                        if hasattr(cv2, "CAP_MSMF"):
                            backends.append(("CAP_MSMF", cv2.CAP_MSMF))
                        backends.append(("DEFAULT", None))

                        for backend_name, backend in backends:
                            trial_cap = cv2.VideoCapture(active_index, backend) if backend is not None else cv2.VideoCapture(active_index)
                            if not trial_cap.isOpened():
                                print(f"✗ Camera {active_index} failed with {backend_name}")
                                trial_cap.release()
                                continue

                            # Apply properties before read-probe so each backend is
                            # validated in near-runtime conditions.
                            self._safe_cap_set(trial_cap, cv2.CAP_PROP_FRAME_WIDTH, 960)
                            self._safe_cap_set(trial_cap, cv2.CAP_PROP_FRAME_HEIGHT, 540)
                            if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                                self._safe_cap_set(trial_cap, cv2.CAP_PROP_BUFFERSIZE, 1)

                            print("Initializing camera stream...")
                            time.sleep(0.35)
                            probe_ok = False
                            for retry in range(4):
                                ok, _frame_test = self._safe_read_frame(trial_cap)
                                if ok:
                                    print(f"✓ Camera {active_index} ready with {backend_name}")
                                    probe_ok = True
                                    break
                                print(f"✗ {backend_name} frame probe {retry + 1} failed")
                                time.sleep(0.15)

                            if probe_ok:
                                cap = trial_cap
                                break

                            print(f"✗ Camera {active_index} probe failed with {backend_name}")
                            trial_cap.release()

                        if cap is not None and cap.isOpened():
                            if target_fps > 0:
                                self._safe_cap_set(cap, cv2.CAP_PROP_FPS, float(target_fps))
                            self._camera_just_opened = True

                        if cap is None or not cap.isOpened():
                            print(f"Error: Could not open camera {active_index}.")
                            if self.update_gesture_callback:
                                self.update_gesture_callback("Cam Error")
                            cap = None
                            time.sleep(2)
                            continue
                    except Exception as e:
                        print(f"Webcam initialization error: {e}")
                        if self.update_gesture_callback:
                            self.update_gesture_callback("Webcam Error")
                        cap = None
                        time.sleep(1)
                        continue

                ret, frame = self._safe_read_frame(cap)
                if not ret:
                    if cap is not None:
                        cap.release()
                        cap = None
                    time.sleep(0.1)
                    continue
                frame_start = time.perf_counter()

                # First successful frame — camera is truly live
                if self._camera_just_opened:
                    self._camera_just_opened = False
                    threading.Thread(
                        target=lambda: winsound.MessageBeep(winsound.MB_ICONASTERISK),
                        daemon=True
                    ).start()
                    if self.camera_ready_callback:
                        self.camera_ready_callback()

                if render_device == "gpu" and self._gpu_available:
                    if self._cuda_available:
                        try:
                            gpu_frame = cv2.cuda_GpuMat()
                            gpu_frame.upload(frame)
                            gpu_flipped = cv2.cuda.flip(gpu_frame, 1)
                            gpu_rgb = cv2.cuda.cvtColor(gpu_flipped, cv2.COLOR_BGR2RGB)
                            frame = gpu_flipped.download()
                            rgb_image = gpu_rgb.download()
                        except Exception:
                            # Safety fallback to CPU mode if CUDA path fails at runtime.
                            with self._camera_lock:
                                self._render_device = "cpu"
                            frame = cv2.flip(frame, 1)
                            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    elif self._opencl_available:
                        try:
                            uframe = cv2.UMat(frame)
                            uflipped = cv2.flip(uframe, 1)
                            urgba = cv2.cvtColor(uflipped, cv2.COLOR_BGR2RGB)
                            frame = uflipped.get()
                            rgb_image = urgba.get()
                        except Exception:
                            with self._camera_lock:
                                self._render_device = "cpu"
                            frame = cv2.flip(frame, 1)
                            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    else:
                        with self._camera_lock:
                            self._render_device = "cpu"
                        frame = cv2.flip(frame, 1)
                        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                else:
                    frame = cv2.flip(frame, 1)
                    rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                results = hands.process(rgb_image)
                detected_gesture = "None"
                hands_snapshot = self._build_hand_snapshot(results)
                self._update_motion_history(hands_snapshot)
                custom_detected = self._detect_custom_gesture(hands_snapshot)
                
                if results.multi_hand_landmarks:
                    for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                        if self.theme != "Minimal" and self.mp_drawing is not None and self.mp_hands is not None:
                            self.mp_drawing.draw_landmarks(
                                rgb_image,
                                hand_landmarks,
                                self.mp_hands.HAND_CONNECTIONS)
                            
                        detected_gesture = self.gesture_recognizer.detect_gesture(hand_landmarks.landmark)
                        
                        if self.theme == "Dr. Strange" and detected_gesture == "Open Palm":
                            h, w, c = rgb_image.shape
                            cx, cy = int(hand_landmarks.landmark[9].x * w), int(hand_landmarks.landmark[9].y * h)
                            cv2.circle(rgb_image, (cx, cy), 80, (255, 165, 0), 2)
                            cv2.circle(rgb_image, (cx, cy), 90, (255, 200, 0), 1)
                        elif self.theme == "Iron Man" and detected_gesture == "Open Palm":
                            h, w, c = rgb_image.shape
                            cx, cy = int(hand_landmarks.landmark[9].x * w), int(hand_landmarks.landmark[9].y * h)
                            cv2.circle(rgb_image, (cx, cy), 30, (255, 255, 255), -1)
                            cv2.circle(rgb_image, (cx, cy), 40, (0, 255, 255), 4)
                            
                if custom_detected:
                    detected_gesture = custom_detected

                stable_gesture, should_trigger = self._stabilize_gesture(detected_gesture)

                if stable_gesture and should_trigger:
                    self.action_mapper.execute_action(stable_gesture)

                if stable_gesture and self.update_gesture_callback:
                    self.update_gesture_callback(stable_gesture)

                if self.update_hands_callback:
                    self.update_hands_callback(hands_snapshot)

                if self.update_image_callback:
                    # Send RGB frame with annotations to callback for UI rendering
                    self.update_image_callback(rgb_image)

                with self._camera_lock:
                    target_fps = self._target_fps
                if target_fps > 0:
                    elapsed = time.perf_counter() - frame_start
                    sleep_for = max(0.0, (1.0 / target_fps) - elapsed)
                    if sleep_for > 0:
                        time.sleep(sleep_for)

        if cap is not None:
            cap.release()

    def stop(self):
        self._run_flag = False
        try:
            if self.thread.is_alive():
                self.thread.join(timeout=2.0)
        except Exception:
            pass
