from flask import Flask, jsonify, request

import os
import vlc

app = Flask(__name__)

instance = vlc.Instance()
player = instance.media_player_new()
current_media = None

