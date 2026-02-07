from flask import Flask, request, jsonify
import subprocess
import json
import socket
import os
import time
from threading import Thread
import platform

app = Flask(__name__)

# Video paths
DEFAULT_VIDEO = "/Users/victor/Desktop/Videor/zwift.mp4"
VIDEO_1 = "/Users/victor/Desktop/Videor/zwift.mp4"
VIDEO_2 = "/Users/victor/Desktop/Videor/IMG_1447.MOV"
VIDEO_3 = "/Users/victor/Desktop/Videor/zwift.mp4"

# MPV socket path (platform-specific)
if platform.system() == 'Windows':
    MPV_SOCKET = r'\\.\pipe\mpv-socket'
else:
    MPV_SOCKET = "/tmp/mpv-socket"

mpv_process = None
is_playing_action = False

def start_mpv():
    """Start MPV once with IPC enabled"""
    global mpv_process
    
    # Remove old socket if exists
    if platform.system() != 'Windows' and os.path.exists(MPV_SOCKET):
        os.remove(MPV_SOCKET)
    
    cmd = [
        'mpv',
        f'--input-ipc-server={MPV_SOCKET}',
        '--fullscreen',
        '--loop-file=inf',  # Loop the default file
        '--mute=yes',       # Start muted (for default video)
        '--keep-open=yes',  # Don't close when file ends
        '--osd-level=0',    # No on-screen display
        DEFAULT_VIDEO
    ]
    
    print(f"Starting MPV with command: {' '.join(cmd)}")
    mpv_process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Wait for socket to be created
    for i in range(10):
        if platform.system() == 'Windows':
            time.sleep(1)
            break
        elif os.path.exists(MPV_SOCKET):
            break
        time.sleep(0.5)
    
    print("MPV started successfully")

def mpv_command(command):
    """Send command to MPV via IPC socket"""
    try:
        if platform.system() == 'Windows':
            # Windows named pipe
            import win32pipe, win32file
            handle = win32file.CreateFile(
                MPV_SOCKET,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None,
                win32file.OPEN_EXISTING,
                0, None
            )
            win32file.WriteFile(handle, (json.dumps(command) + '\n').encode())
            win32file.CloseHandle(handle)
        else:
            # Unix socket
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(MPV_SOCKET)
            sock.sendall((json.dumps(command) + '\n').encode())
            sock.close()
        return True
    except Exception as e:
        print(f"MPV command failed: {e}")
        return False

def get_mpv_property(property_name):
    """Get a property from MPV"""
    try:
        if platform.system() != 'Windows':
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(MPV_SOCKET)
            sock.sendall((json.dumps({"command": ["get_property", property_name]}) + '\n').encode())
            sock.settimeout(1)
            response = sock.recv(4096).decode()
            sock.close()
            return json.loads(response.split('\n')[0])
    except:
        pass
    return None

def play_default_video():
    """Play default video - LOOPING and MUTED"""
    global is_playing_action
    
    print("Playing default video (muted, looping)")
    
    # Clear playlist first
    mpv_command({"command": ["playlist-clear"]})
    time.sleep(0.2)
    
    # Load default video
    mpv_command({"command": ["loadfile", DEFAULT_VIDEO]})
    time.sleep(0.5)
    
    # LOOP this video infinitely
    mpv_command({"command": ["set_property", "loop-file", "inf"]})
    
    # MUTE the audio
    mpv_command({"command": ["set_property", "mute", True]})
    
    # Ensure playing
    mpv_command({"command": ["set_property", "pause", False]})
    
    is_playing_action = False

def play_action_video(video_path):
    """Play action video - NO LOOP and WITH SOUND"""
    global is_playing_action
    
    print(f"Playing action video: {video_path} (with sound, no loop)")
    
    # Clear playlist
    mpv_command({"command": ["playlist-clear"]})
    time.sleep(0.2)
    
    # Add action video followed by default video
    mpv_command({"command": ["loadfile", video_path]})
    time.sleep(0.2)
    mpv_command({"command": ["loadfile", DEFAULT_VIDEO, "append"]})
    time.sleep(0.3)
    
    # Don't loop the action video
    mpv_command({"command": ["set_property", "loop-file", "no"]})
    
    # Enable sound for action video
    mpv_command({"command": ["set_property", "mute", False]})
    
    # Start playing
    mpv_command({"command": ["set_property", "pause", False]})
    
    is_playing_action = True

def monitor_playback():
    """Monitor playlist position"""
    global is_playing_action
    
    while True:
        time.sleep(1)
        
        if is_playing_action:
            # Check playlist position
            playlist_pos = get_mpv_property("playlist-pos")
            
            if playlist_pos and playlist_pos.get("data") == 1:
                # We're on the second item (default video)
                print("Switched to default video in playlist - setting loop and mute")
                mpv_command({"command": ["set_property", "loop-file", "inf"]})
                mpv_command({"command": ["set_property", "mute", True]})
                is_playing_action = False

def monitor_mpv():
    """Monitor MPV process and restart if crashed"""
    global mpv_process
    
    while True:
        time.sleep(5)
        if mpv_process and mpv_process.poll() is not None:
            print("MPV crashed! Restarting...")
            start_mpv()
            play_default_video()
        time.sleep(5)

# Routes matching your Flic JS
@app.route('/changeVideo', methods=['POST'])
def change_video():
    """Handle video change requests from Flic buttons"""
    data = request.json
    video_id = data.get('video-id')
    click_type = data.get('click-type')
    
    print(f"Change video request: video-id={video_id}, click-type={click_type}")
    
    video_map = {
        1: VIDEO_1,
        2: VIDEO_2,
        3: VIDEO_3,
    }
    
    if video_id in video_map:
        play_action_video(video_map[video_id])
    else:
        print(f"Unknown video-id: {video_id}")
    
    return jsonify({"status": "success", "video-id": video_id}), 200

@app.route('/close', methods=['POST'])
def close_video():
    """Return to default video"""
    data = request.json
    print(f"Close request: {data}")
    play_default_video()
    return jsonify({"status": "success"}), 200

@app.route('/pause', methods=['POST'])
def pause_video():
    """Toggle pause"""
    data = request.json
    print(f"Pause request: {data}")
    mpv_command({"command": ["cycle", "pause"]})
    return jsonify({"status": "success"}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "running"}), 200

def cleanup():
    """Cleanup on exit"""
    print("\nCleaning up...")
    if mpv_process:
        mpv_process.terminate()
    if platform.system() != 'Windows' and os.path.exists(MPV_SOCKET):
        os.remove(MPV_SOCKET)

if __name__ == '__main__':
    import atexit
    atexit.register(cleanup)
    
    print(f"Running on: {platform.system()}")
    
    # Check if MPV is installed
    try:
        subprocess.run(['mpv', '--version'], capture_output=True, check=True)
        print("MPV found!")
    except:
        print("ERROR: MPV not found. Install with: brew install mpv")
        exit(1)
    
    # Start MPV
    print("Starting MPV player...")
    start_mpv()
    
    # Start monitor threads
    Thread(target=monitor_mpv, daemon=True).start()
    Thread(target=monitor_playback, daemon=True).start()
    
    print(f"Default video: {DEFAULT_VIDEO}")
    print(f"Video 1: {VIDEO_1}")
    print(f"Video 2: {VIDEO_2}")
    print(f"Video 3: {VIDEO_3}")
    
    print("\nBehavior:")
    print("  - Default video: LOOPS FOREVER, NO SOUND")
    print("  - Action videos (1,2,3): PLAY ONCE WITH SOUND, then back to default")
    
    print("\nFlask server starting on http://0.0.0.0:5555")
    try:
        app.run(host='0.0.0.0', port=5555, threaded=True)
    except KeyboardInterrupt:
        cleanup()