import cv2
import time
import os
import math
import threading
import zipfile
from pathlib import Path
from datetime import datetime


def str_to_bool(value, default=False):
    if value is None:
        return default
    value = value.strip().lower()
    return value in {"1", "true", "yes", "on"}

def load_env_from_file(env_path):
    """Load environment variables from a simple KEY=VALUE file."""
    path = Path(env_path)
    if not path.is_file():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

def test_ip_camera(url, label=None):
    """Test if an IP camera URL is accessible."""
    label_to_show = label or url
    print(f"Testing IP camera: {label_to_show}")
    cap = cv2.VideoCapture(url)
    
    if not cap.isOpened():
        print(f"❌ Cannot connect to IP camera: {label_to_show}")
        return False
    
    # Try to read a frame to verify the connection
    ret, frame = cap.read()
    cap.release()
    
    if ret and frame is not None:
        print(f"✅ IP camera is accessible: {label_to_show}")
        return True
    else:
        print(f"❌ IP camera connection failed: {label_to_show}")
        return False

def build_rtsp_url(ip, username, password, channel="101", port="554"):
    """Construct an RTSP URL for Hikvision cameras."""
    return f"rtsp://{username}:{password}@{ip}:{port}/Streaming/Channels/{channel}"

class DataCollector:
    def __init__(
        self,
        uid,
        connection_class,
        ip1,
        ip2,
        data_root=None,
        show_preview=False,
        crop_top=0,
        crop_bottom=0,
        crop_left=0,
        crop_right=0,
        jpeg_quality=95,
        archive_after_capture=True,
        archive_remove_originals=False,
    ):
        """
        uid — ID рельсового элемента
        connection_class — тип соединения (папка)
        ip1 — IP/индекс камеры сверху (top)
        ip2 — IP/индекс камеры спереди (front)
        """
        self.uid = uid
        self.connection_class = connection_class
        self.ip1 = ip1  # top
        self.ip2 = ip2  # front

        script_dir = Path(__file__).resolve().parent
        if data_root is None:
            self.data_root = script_dir / "data"
        else:
            data_root_path = Path(data_root)
            if data_root_path.is_absolute():
                self.data_root = data_root_path
            else:
                self.data_root = script_dir / data_root_path
        self.base_dir = self.data_root / self.connection_class / self.uid
        self.front_dir = self.base_dir / "front"
        self.top_dir = self.base_dir / "top"
        self.show_preview = show_preview
        self.crop_top = max(int(crop_top), 0)
        self.crop_bottom = max(int(crop_bottom), 0)
        self.crop_left = max(int(crop_left), 0)
        self.crop_right = max(int(crop_right), 0)
        self.jpeg_quality = max(10, min(int(jpeg_quality), 100))
        self.archive_after_capture = bool(archive_after_capture)
        self.archive_remove_originals = bool(archive_remove_originals)
        self.ensure_dirs()

    def ensure_dirs(self):
        self.front_dir.mkdir(parents=True, exist_ok=True)
        self.top_dir.mkdir(parents=True, exist_ok=True)

    def get_camera_url(self, camera_id):
        """Get camera source - can be index for local cameras or URL for IP cameras."""
        try:
            # Try to convert to int for local camera index
            return int(camera_id)
        except ValueError:
            # If not a number, treat as URL/IP
            return camera_id
    
    def is_ip_camera(self, camera_source):
        """Check if the camera source is an IP camera URL."""
        if isinstance(camera_source, int):
            return False
        return isinstance(camera_source, str) and ('http://' in camera_source or 'rtsp://' in camera_source or 'rtmp://' in camera_source)

    def process_frame(self, frame):
        """Apply post-processing like cropping to remove overlays."""
        h, w = frame.shape[:2]

        top = min(self.crop_top, h - 1)
        bottom = min(self.crop_bottom, h - top - 1)
        left = min(self.crop_left, w - 1)
        right = min(self.crop_right, w - left - 1)

        if top or bottom or left or right:
            frame = frame[top : h - bottom if bottom else h, left : w - right if right else w]
        return frame

    def archive_directory(self, directory: Path, prefix: str):
        """Compress captured images into a zip archive."""
        if not directory.exists():
            return None

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        zip_path = directory.parent / f"{prefix}_{timestamp}.zip"
        print(f"Archiving {directory} -> {zip_path}")

        with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for file_path in sorted(directory.glob("*.jpg")):
                zf.write(file_path, arcname=file_path.name)

        if self.archive_remove_originals:
            removed = 0
            for file_path in directory.glob("*.jpg"):
                try:
                    file_path.unlink()
                    removed += 1
                except Exception as exc:
                    print(f"Warning: failed to remove {file_path}: {exc}")
            print(f"Removed {removed} original files from {directory}")

        return zip_path

    def grab_and_save_frames(self, src, out_dir: Path, view: str, count: int, interval_sec: int):
        """Capture frames from a camera and save them to the specified directory."""
        print(f"Initializing camera for {view} view (source: {src})...")
        
        # Initialize camera with better error handling
        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open camera for {view} view: {src}")
        
        # Set camera properties based on camera type
        if self.is_ip_camera(src):
            print(f"Configuring IP camera for {view} view...")
            # IP cameras often have different optimal settings
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer for IP cameras
            cap.set(cv2.CAP_PROP_FPS, 15)  # Lower FPS for IP cameras
            # Don't force resolution for IP cameras as they may not support it
        else:
            print(f"Configuring local camera for {view} view...")
            # Local cameras can usually handle higher settings
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 30)
        
        print(f"Camera for {view} view initialized successfully")

        try:
            for i in range(count):
                # Record start time for this capture
                capture_start = time.time()
                
                # Flush camera buffer to get fresh frame
                if self.is_ip_camera(src):
                    # IP cameras need more aggressive buffer flushing
                    for _ in range(5):
                        cap.read()
                else:
                    # Local cameras need less buffer flushing
                    for _ in range(3):
                        cap.read()
                
                ret, frame = cap.read()
                if not ret:
                    print(f"Warning: Failed to read frame {i+1} from {view} camera")
                    continue

                # Post-process frame (e.g., crop overlays)
                frame = self.process_frame(frame)

                # Generate timestamp and filename with milliseconds
                now = datetime.now()
                ts = now.strftime("%Y-%m-%d_%H-%M-%S")
                ms = now.strftime("%f")[:3]  # Get milliseconds (first 3 digits)
                filename = f"{view}_{ts}-{ms}_{i+1:02d}.jpg"
                out_path = out_dir / filename
                
                # Save frame
                success = cv2.imwrite(str(out_path), frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                if success:
                    elapsed_so_far = time.time() - capture_start
                    print(f"[OK] Saved {view} frame {i+1}/{count} (took {elapsed_so_far:.2f}s): {out_path}")
                else:
                    print(f"[ERROR] Failed to save {view} frame {i+1}: {out_path}")
                
                # Show preview if enabled
                if self.show_preview:
                    cv2.imshow(f"{view.title()} View - Press 'q' to quit", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        print("Capture interrupted by user")
                        break
                
                # Calculate elapsed time and wait for the remaining interval
                if i < count - 1:  # Don't wait after the last frame
                    elapsed = time.time() - capture_start
                    remaining_time = interval_sec - elapsed
                    if remaining_time > 0:
                        print(f"Waiting {remaining_time:.1f} seconds until next capture...")
                        time.sleep(remaining_time)
                    else:
                        print("Warning: Capture took longer than interval, proceeding immediately")
                    
        except Exception as e:
            print(f"Error during {view} capture: {e}")
            raise
        finally:
            cap.release()
            if self.show_preview:
                cv2.destroyAllWindows()

    def capture(self, front_count=3, front_interval_sec=5, top_count=1, top_interval_sec=0):
        """Capture frames from both front and top cameras."""
        print(f"Starting data collection for UID: {self.uid}")
        print(f"Front camera source: {self.ip2}, Top camera source: {self.ip1}")
        
        front_src = self.get_camera_url(self.ip2)
        top_src = self.get_camera_url(self.ip1)
        
        results = {
            "front_dir": str(self.front_dir),
            "top_dir": str(self.top_dir),
            "front_saved": 0,
            "top_saved": 0,
            "errors": []
        }
        
        errors_lock = threading.Lock()

        def capture_task(view_name, src, out_dir, count, interval, result_key):
            print(f"\n=== Capturing {count} frames from {view_name.upper()} camera ===")
            try:
                self.grab_and_save_frames(src, out_dir, view_name, count, interval)
                results[result_key] = count
            except Exception as exc:
                error_msg = f"{view_name.title()} camera error: {exc}"
                print(f"[ERROR] {error_msg}")
                with errors_lock:
                    results["errors"].append(error_msg)

        threads = [
            threading.Thread(
                target=capture_task,
                args=("front", front_src, self.front_dir, front_count, front_interval_sec, "front_saved"),
                daemon=False,
            ),
            threading.Thread(
                target=capture_task,
                args=("top", top_src, self.top_dir, top_count, top_interval_sec, "top_saved"),
                daemon=False,
            ),
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        archives = {}
        if self.archive_after_capture:
            if results["front_saved"] > 0:
                archive = self.archive_directory(self.front_dir, f"{self.uid}_front")
                if archive:
                    archives["front_archive"] = str(archive)
            if results["top_saved"] > 0:
                archive = self.archive_directory(self.top_dir, f"{self.uid}_top")
                if archive:
                    archives["top_archive"] = str(archive)

        results.update(archives)
        
        print(f"\n=== Data collection completed ===")
        print(f"Front images saved: {results['front_saved']}")
        print(f"Top images saved: {results['top_saved']}")
        if results["errors"]:
            print(f"Errors encountered: {len(results['errors'])}")
            for error in results["errors"]:
                print(f"  - {error}")
        
        return results

if __name__ == "__main__":
    print("=== Data Collector for Network Cameras ===")

    env_file = os.environ.get("HIKVISION_ENV_FILE", ".env")
    load_env_from_file(env_file)
    
    camera_username = os.environ.get("HIKVISION_USER", "admin")
    camera_password = os.environ.get("HIKVISION_PASS", "+79855160728T")
    top_ip = os.environ.get("HIKVISION_TOP_IP", "192.168.1.104")
    front_ip = os.environ.get("HIKVISION_FRONT_IP", "192.168.1.105")
    rtsp_port = os.environ.get("HIKVISION_RTSP_PORT", "554")
    top_channel = os.environ.get("HIKVISION_TOP_CHANNEL", "101")
    front_channel = os.environ.get("HIKVISION_FRONT_CHANNEL", "101")
    show_preview = str_to_bool(os.environ.get("HIKVISION_PREVIEW"), default=False)
    capture_interval_sec = int(os.environ.get("HIKVISION_CAPTURE_INTERVAL", "3"))
    capture_duration_min = float(os.environ.get("HIKVISION_CAPTURE_DURATION_MIN", "90"))
    crop_top = int(os.environ.get("HIKVISION_CROP_TOP", "0"))
    crop_bottom = int(os.environ.get("HIKVISION_CROP_BOTTOM", "0"))
    crop_left = int(os.environ.get("HIKVISION_CROP_LEFT", "0"))
    crop_right = int(os.environ.get("HIKVISION_CROP_RIGHT", "0"))
    jpeg_quality = int(os.environ.get("HIKVISION_JPEG_QUALITY", "85"))
    archive_after_capture = str_to_bool(os.environ.get("HIKVISION_ARCHIVE_AFTER_CAPTURE"), default=True)
    archive_remove_originals = str_to_bool(os.environ.get("HIKVISION_ARCHIVE_REMOVE_ORIGINALS"), default=False)

    total_captures = max(1, math.ceil((capture_duration_min * 60) / capture_interval_sec))

    # Fixed configuration for Hikvision RTSP cameras (no auto-scan)
    TOP_CAMERA_URL = build_rtsp_url(top_ip, camera_username, camera_password, channel=top_channel, port=rtsp_port)
    FRONT_CAMERA_URL = build_rtsp_url(front_ip, camera_username, camera_password, channel=front_channel, port=rtsp_port)
    
    print("\nCamera Configuration:")
    print(f"Top camera: {top_ip}:{rtsp_port}/Streaming/Channels/{top_channel}")
    print(f"Front camera: {front_ip}:{rtsp_port}/Streaming/Channels/{front_channel}")
    print(f"Capture interval: {capture_interval_sec}s, planned duration: {capture_duration_min} min")
    print(f"Frames per camera: {total_captures}")
    if any([crop_top, crop_bottom, crop_left, crop_right]):
        print(f"Cropping applied (pixels) - top:{crop_top} bottom:{crop_bottom} left:{crop_left} right:{crop_right}")
    print(f"JPEG quality: {jpeg_quality}")
    print(f"Archive after capture: {archive_after_capture} (remove originals: {archive_remove_originals})")
    
    # Test camera connectivity
    print("\n=== Testing Camera Connectivity ===")
    top_label = f"rtsp://{top_ip}:{rtsp_port}/Streaming/Channels/{top_channel}"
    front_label = f"rtsp://{front_ip}:{rtsp_port}/Streaming/Channels/{front_channel}"
    top_accessible = test_ip_camera(TOP_CAMERA_URL, label=top_label)
    front_accessible = test_ip_camera(FRONT_CAMERA_URL, label=front_label)
    
    if not top_accessible and not front_accessible:
        print("❌ No cameras are accessible. Please check your network connections and camera URLs.")
        exit(1)
    
    # Create data collector
    collector = DataCollector(
        uid="TEST-001",
        connection_class="connection_class",
        ip1=TOP_CAMERA_URL,    # top camera
        ip2=FRONT_CAMERA_URL,  # front camera
        show_preview=show_preview,
        crop_top=crop_top,
        crop_bottom=crop_bottom,
        crop_left=crop_left,
        crop_right=crop_right,
        jpeg_quality=jpeg_quality,
        archive_after_capture=archive_after_capture,
        archive_remove_originals=archive_remove_originals,
    )
    
    # Capture settings - adjust as needed
    print("\n=== Starting Data Collection ===")
    result = collector.capture(
        front_count=total_captures,
        front_interval_sec=capture_interval_sec,
        top_count=total_captures,
        top_interval_sec=capture_interval_sec
    )
    
    print("\n=== Final Results ===")
    print(result)

