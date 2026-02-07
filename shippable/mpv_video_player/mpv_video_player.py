from flask import Flask, request, jsonify
import subprocess
import json
import socket
import os
import time
from threading import Thread
import platform
import sys
import glob
import atexit

app = Flask(__name__)

def get_mpv_property(property_name):
    """
    Ask MPV for a property via the IPC socket.
    Returns a dict like {'data': value} or None if failed.
    """
    try:
        if platform.system() != 'Windows':
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(MPV_SOCKET)
            # send the 'get_property' command
            cmd = {"command": ["get_property", property_name]}
            sock.sendall((json.dumps(cmd) + "\n").encode())

            sock.settimeout(1)
            response = sock.recv(4096).decode()
            sock.close()

            # MPV returns JSON per line, take first line
            return json.loads(response.split("\n")[0])
    except Exception as e:
        print(f"get_mpv_property failed: {e}")
        return None


def get_mpv_path():
    """
    Returns the path to the mpv binary.
    Uses the bundled mpv if running from a PyInstaller .app,
    otherwise uses local ./mpv.
    """
    if getattr(sys, "frozen", False):
        # Running from PyInstaller bundle
        return os.path.join(sys._MEIPASS, "mpv")
    # Running normally in Python
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "mpv")

# ----------------------------
# Video folder and generic loader
# ----------------------------
VIDEO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "videos")

def get_video(name):
    """
    Returns the first video matching the name with any extension
    in the videos folder.
    """
    patterns = [os.path.join(VIDEO_DIR, f"{name}{ext}") for ext in [".mp4", ".MOV", ".mkv"]]
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    print(f"Video not found: {name}")
    return None

# ----------------------------
# Load videos dynamically
# ----------------------------
DEFAULT_VIDEO = get_video("default")
VIDEO_1 = get_video("video1")
VIDEO_2 = get_video("video2")
VIDEO_3 = get_video("video3")

# ----------------------------
# MPV socket path
# ----------------------------
if platform.system() == 'Windows':
    MPV_SOCKET = r'\\.\pipe\mpv-socket'
else:
    MPV_SOCKET = "/tmp/mpv-socket"

mpv_process = None
is_playing_action = False

# ----------------------------
# MPV functions
# ----------------------------
def start_mpv():
    global mpv_process
    if platform.system() != 'Windows' and os.path.exists(MPV_SOCKET):
        os.remove(MPV_SOCKET)

    if not DEFAULT_VIDEO:
        print("ERROR: Default video not found. Cannot start MPV.")
        return

    cmd = [
        get_mpv_path(),
        f"--input-ipc-server={MPV_SOCKET}",
        "--fullscreen",
        "--loop-file=inf",
        "--mute=yes",
        "--keep-open=yes",
        "--osd-level=0",
        DEFAULT_VIDEO
    ]
    print(f"Starting MPV: {' '.join(cmd)}")
    mpv_process = subprocess.Popen(cmd)

    # Wait for socket
    for i in range(10):
        if platform.system() == 'Windows':
            time.sleep(1)
            break
        elif os.path.exists(MPV_SOCKET):
            break
        time.sleep(0.5)

def mpv_command(command, retries=5):
    """Send command to MPV via IPC socket with retry"""
    for attempt in range(retries):
        try:
            if platform.system() != 'Windows':
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(MPV_SOCKET)
                sock.sendall((json.dumps(command) + "\n").encode())
                sock.close()
            return True
        except Exception as e:
            print(f"MPV command failed (attempt {attempt+1}): {e}")
            time.sleep(0.2)
    return False

def play_default_video():
    global is_playing_action
    if not DEFAULT_VIDEO:
        print("Default video missing.")
        return
    print("Playing default video")
    mpv_command({"command": ["playlist-clear"]})
    time.sleep(0.2)
    mpv_command({"command": ["loadfile", DEFAULT_VIDEO]})
    time.sleep(0.5)
    mpv_command({"command": ["set_property", "loop-file", "inf"]})
    mpv_command({"command": ["set_property", "mute", True]})
    mpv_command({"command": ["set_property", "pause", False]})
    is_playing_action = False

def play_action_video(video_path):
    global is_playing_action
    if not video_path:
        print("Action video missing.")
        return
    print(f"Playing action video: {video_path}")
    mpv_command({"command": ["playlist-clear"]})
    time.sleep(0.2)
    mpv_command({"command": ["loadfile", video_path]})
    time.sleep(0.2)
    mpv_command({"command": ["loadfile", DEFAULT_VIDEO, "append"]})
    time.sleep(0.3)
    mpv_command({"command": ["set_property", "loop-file", "no"]})
    mpv_command({"command": ["set_property", "mute", False]})
    mpv_command({"command": ["set_property", "pause", False]})
    is_playing_action = True

def monitor_playback():
    """Monitor playlist and apply mute/loop only to default video."""
    global is_playing_action
    while True:
        time.sleep(0.5)  # check more frequently

        if is_playing_action:
            # Get current playlist position
            try:
                playlist_pos = get_mpv_property("playlist-pos")
                if playlist_pos and playlist_pos.get("data") == 1:
                    # Only now we are on the default video
                    print("Switched to default video - enabling loop and mute")
                    mpv_command({"command": ["set_property", "loop-file", "inf"]})
                    mpv_command({"command": ["set_property", "mute", True]})
                    is_playing_action = False
            except Exception as e:
                # MPV might not be ready yet
                continue

def monitor_mpv():
    global mpv_process
    while True:
        time.sleep(5)
        if mpv_process and mpv_process.poll() is not None:
            print("MPV crashed! Restarting...")
            start_mpv()
            play_default_video()
        time.sleep(5)

# ----------------------------
# Flask routes
# ----------------------------
@app.route("/changeVideo", methods=["POST"])
def change_video():
    data = request.json
    video_id = data.get("video-id")
    video_map = {1: VIDEO_1, 2: VIDEO_2, 3: VIDEO_3}
    if video_id in video_map and video_map[video_id]:
        play_action_video(video_map[video_id])
    else:
        print(f"Unknown or missing video id: {video_id}")
    return jsonify({"status": "success", "video-id": video_id})

@app.route("/close", methods=["POST"])
def close_video():
    play_default_video()
    return jsonify({"status": "success"})

@app.route("/pause", methods=["POST"])
def pause_video():
    mpv_command({"command": ["cycle", "pause"]})
    return jsonify({"status": "success"})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "running"})

def cleanup():
    print("Cleaning up...")
    if mpv_process:
        mpv_process.terminate()
    if platform.system() != "Windows" and os.path.exists(MPV_SOCKET):
        os.remove(MPV_SOCKET)

atexit.register(cleanup)

# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    print("Starting MPV Player")
    start_mpv()
    Thread(target=monitor_mpv, daemon=True).start()
    Thread(target=monitor_playback, daemon=True).start()
    play_default_video()
    app.run(host="0.0.0.0", port=5555, threaded=True)
