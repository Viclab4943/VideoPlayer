from flask import Flask, request, jsonify
import subprocess
import time
import platform
import os
import requests
from requests.auth import HTTPBasicAuth
from threading import Thread, Lock
import xml.etree.ElementTree as ET

app = Flask(__name__)

# Video paths
DEFAULT_VIDEO = "/Users/victor/Desktop/Videor/zwift.mp4"
VIDEO_1 = "/Users/victor/Desktop/Videor/zwift.mp4"
VIDEO_2 = "/Users/victor/Desktop/Videor/IMG_1447.MOV"
VIDEO_3 = "/Users/victor/Desktop/Videor/zwift.mp4"

# VLC HTTP interface settings
VLC_HTTP_PORT = 8080
VLC_HTTP_PASSWORD = "vlcremote"
VLC_HTTP_URL = f"http://localhost:{VLC_HTTP_PORT}"

vlc_process = None
is_playing_action = False
vlc_lock = Lock()  # Prevent concurrent VLC restarts

def get_vlc_path():
    """Get VLC executable path based on OS"""
    system = platform.system()
    
    if system == 'Darwin':  # macOS
        return '/Applications/VLC.app/Contents/MacOS/VLC'
    elif system == 'Windows':
        paths = [
            r'C:\Program Files\VideoLAN\VLC\vlc.exe',
            r'C:\Program Files (x86)\VideoLAN\VLC\vlc.exe',
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        return 'vlc'
    else:  # Linux
        return 'vlc'

def kill_vlc():
    """Kill all VLC processes - aggressive approach"""
    system = platform.system()
    
    # Try multiple times to ensure all instances are killed
    for attempt in range(3):
        try:
            if system == 'Windows':
                subprocess.run(['taskkill', '/F', '/IM', 'vlc.exe'], 
                             stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            else:
                subprocess.run(['killall', '-9', 'vlc'],  # -9 for force kill
                             stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                # Also try VLC (capital V)
                subprocess.run(['killall', '-9', 'VLC'], 
                             stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            time.sleep(0.3)
        except:
            pass
    
    # Final wait to ensure processes are dead
    time.sleep(0.5)

def vlc_command(command, **params):
    """Send command to VLC HTTP interface"""
    auth = HTTPBasicAuth('', VLC_HTTP_PASSWORD)
    params['command'] = command
    
    try:
        response = requests.get(
            f"{VLC_HTTP_URL}/requests/status.xml",
            auth=auth,
            params=params,
            timeout=2
        )
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        return False

def get_vlc_status():
    """Get VLC playback status"""
    auth = HTTPBasicAuth('', VLC_HTTP_PASSWORD)
    
    try:
        response = requests.get(
            f"{VLC_HTTP_URL}/requests/status.xml",
            auth=auth,
            timeout=2
        )
        if response.status_code == 200:
            # Parse XML response
            root = ET.fromstring(response.content)
            state = root.find('state').text if root.find('state') is not None else None
            length = root.find('length').text if root.find('length') is not None else '0'
            time_pos = root.find('time').text if root.find('time') is not None else '0'
            
            return {
                'state': state,
                'length': int(length),
                'time': int(time_pos)
            }
    except Exception as e:
        pass
    
    return None

def play_video_in_vlc(video_path, mute=False, loop=False):
    """Restart VLC with the specified video and settings - thread-safe"""
    global vlc_process, vlc_lock
    
    # Use lock to prevent multiple concurrent restarts
    with vlc_lock:
        print(f"Restarting VLC with: {video_path}, mute={mute}, loop={loop}")
        
        # Kill ALL existing VLC instances aggressively
        kill_vlc()
        
        vlc_path = get_vlc_path()
        
        # Build command
        cmd = [
            vlc_path,
            '--extraintf', 'http',
            '--http-password', VLC_HTTP_PASSWORD,
            '--http-port', str(VLC_HTTP_PORT),
            '--fullscreen',
            '--no-video-title-show',
            '--no-osd',
            video_path
        ]
        
        # Add loop ONLY if requested
        if loop:
            cmd.extend(['--loop', '--repeat'])
        
        # Mute audio if requested
        if mute:
            cmd.append('--no-audio')
        
        # Platform-specific additions
        if platform.system() == 'Windows':
            cmd.extend(['--qt-start-minimized'])
        elif platform.system() == 'Linux':
            cmd.extend(['--vout', 'x11'])
        
        try:
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                vlc_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    startupinfo=startupinfo
                )
            else:
                vlc_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            
            print(f"VLC started successfully")
            time.sleep(2)  # Wait for VLC to start
            
            # Set volume if not muted
            if not mute:
                time.sleep(1)
                vlc_command('volume', val='256')
            
            return True
            
        except Exception as e:
            print(f"Error starting VLC: {e}")
            return False

def play_default_video():
    """Play default video silently on loop"""
    global is_playing_action
    print("Playing default video (muted, looping)")
    play_video_in_vlc(DEFAULT_VIDEO, mute=True, loop=True)
    is_playing_action = False

def monitor_playback():
    """Monitor playback and return to default when action video ends"""
    global is_playing_action
    
    while True:
        time.sleep(2)
        
        if is_playing_action:
            status = get_vlc_status()
            
            if status:
                # Check if video ended
                if status['state'] == 'stopped':
                    print("Action video ended - returning to default")
                    play_default_video()
                elif status['length'] > 0 and status['time'] > 0:
                    # If we're within 2 seconds of the end
                    time_remaining = status['length'] - status['time']
                    if time_remaining < 2:
                        print(f"Action video almost done ({time_remaining}s left)")
                        time.sleep(time_remaining + 0.5)
                        # Double check it ended
                        status = get_vlc_status()
                        if status and status['state'] != 'playing':
                            play_default_video()

def monitor_vlc():
    """Monitor VLC and restart if it crashes"""
    global vlc_process, is_playing_action
    while True:
        time.sleep(5)
        if vlc_process and vlc_process.poll() is not None:
            print("VLC crashed! Restarting with default video...")
            play_default_video()
        time.sleep(5)

# Route that matches your JS: /changeVideo
@app.route('/changeVideo', methods=['POST'])
def change_video():
    """Handle video change requests from Flic buttons"""
    global is_playing_action
    
    data = request.json
    video_id = data.get('video-id')
    click_type = data.get('click-type')
    
    print(f"Change video request: video-id={video_id}, click-type={click_type}")
    
    # Map video IDs to video files
    video_map = {
        1: VIDEO_1,
        2: VIDEO_2,
        3: VIDEO_3,
    }
    
    if video_id in video_map:
        video_path = video_map[video_id]
        print(f"Playing video {video_id}: {video_path}")
        play_video_in_vlc(video_path, mute=False, loop=False)
        is_playing_action = True
    else:
        print(f"Unknown video-id: {video_id}")
    
    return jsonify({"status": "success", "video-id": video_id}), 200

# Route that matches your JS: /close
@app.route('/close', methods=['POST'])
def close_video():
    """Handle close/stop requests - return to default video"""
    data = request.json
    video_id = data.get('video-id')
    click_type = data.get('click-type')
    
    print(f"Close request: video-id={video_id}, click-type={click_type}")
    print("Returning to default video")
    play_default_video()
    
    return jsonify({"status": "success"}), 200

# Route that matches your JS: /pause
@app.route('/pause', methods=['POST'])
def pause_video():
    """Handle pause requests"""
    data = request.json
    print(f"Pause request: {data}")
    
    vlc_command('pl_pause')
    
    return jsonify({"status": "success"}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "running"}), 200

def cleanup():
    """Cleanup on exit"""
    print("\nCleaning up...")
    kill_vlc()

if __name__ == '__main__':
    import atexit
    atexit.register(cleanup)
    
    print(f"Running on: {platform.system()}")
    print(f"VLC path: {get_vlc_path()}")
    
    # Install requests if not available
    try:
        import requests
    except ImportError:
        print("Installing requests library...")
        subprocess.run(['pip', 'install', 'requests'])
        import requests
    
    # Start with default video
    print("Starting with default video...")
    play_default_video()
    
    # Start VLC monitor thread
    monitor_thread = Thread(target=monitor_vlc, daemon=True)
    monitor_thread.start()
    
    # Start playback monitor thread
    playback_monitor_thread = Thread(target=monitor_playback, daemon=True)
    playback_monitor_thread.start()
    
    print(f"Default video: {DEFAULT_VIDEO}")
    print(f"Video 1: {VIDEO_1}")
    print(f"Video 2: {VIDEO_2}")
    print(f"Video 3: {VIDEO_3}")
    
    # Run Flask server on port 5555
    print("Flask server starting on http://0.0.0.0:5555")
    try:
        app.run(host='0.0.0.0', port=5555, threaded=True)
    except KeyboardInterrupt:
        print("\nShutting down...")
        cleanup()