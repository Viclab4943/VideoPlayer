from flask import Flask, request, jsonify
import subprocess
import json
import socket
import os

app = Flask(__name__)

# Video paths
DEFAULT_VIDEO = "/Users/victor/Desktop/Videor/zwift.mp4"
VIDEO_1 = "/Users/victor/Desktop/Videor/zwift.mp4"
VIDEO_2 = "/Users/victor/Desktop/Videor/IMG_1447.MOV"
VIDEO_3 = "/Users/victor/Desktop/Videor/zwift.mp4"

MPV_SOCKET = "/tmp/mpv-socket"

def start_mpv():
    """Start MPV once with IPC enabled"""
    cmd = [
        'mpv',
        f'--input-ipc-server={MPV_SOCKET}',
        '--fullscreen',
        '--loop-playlist=inf',
        '--no-audio',
        DEFAULT_VIDEO
    ]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def mpv_command(command):
    """Send command to MPV via IPC"""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(MPV_SOCKET)
        sock.sendall((json.dumps(command) + '\n').encode())
        sock.close()
        return True
    except:
        return False

def play_video(path, loop=True, mute=True):
    """Switch video smoothly"""
    # Load new file
    mpv_command({"command": ["loadfile", path, "replace"]})
    # Set loop
    mpv_command({"command": ["set_property", "loop-file", "inf" if loop else "no"]})
    # Set audio
    mpv_command({"command": ["set_property", "mute", mute]})

@app.route('/changeVideo', methods=['POST'])
def change_video():
    data = request.json
    video_map = {1: VIDEO_1, 2: VIDEO_2, 3: VIDEO_3}
    
    if data.get('video-id') in video_map:
        play_video(video_map[data['video-id']], loop=False, mute=False)
    
    return jsonify({"status": "success"}), 200

@app.route('/close', methods=['POST'])
def close_video():
    play_video(DEFAULT_VIDEO, loop=True, mute=True)
    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    start_mpv()
    app.run(host='0.0.0.0', port=5555)