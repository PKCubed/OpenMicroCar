import socket
import threading
import sys
import time
from queue import Queue
from flask import Flask, render_template_string, jsonify
from datetime import datetime
import json

# --- Helper function for consistent logging ---
def log_with_timestamp(message):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(f"{timestamp} {message}")

# --- Configuration ---
HOST = '0.0.0.0'
PORT = 5000
TEAMS = {1: "Team Alpha", 2: "Team Beta"}

# Mappings of IP addresses to their IR addresses (for CARS ONLY) and IDs
IP_TO_CAR = {
    '192.168.77.51': {'id': 1, 'ir_address': 0x01},
    '192.168.77.52': {'id': 2, 'ir_address': 0x02},
    '192.168.77.53': {'id': 3, 'ir_address': 0x03},
    '192.168.77.54': {'id': 4, 'ir_address': 0x04},
    '192.168.77.55': {'id': 5, 'ir_address': 0x05},
}

# Mappings of IP addresses to their IDs (for BASE STATIONS ONLY)
IP_TO_BASE_STATION = {
    '192.168.77.11': {'id': 1},
    '192.168.77.12': {'id': 2},
}

# Derived mappings from the primary configuration
IR_ADDRESS_TO_CAR_ID = {car['ir_address']: car['id'] for car in IP_TO_CAR.values()}
CAR_IR_ADDRESSES = list(IR_ADDRESS_TO_CAR_ID.keys())

CAR_TEAM_MAPPING = {
    1: 1, # Car 1 is on Team Alpha
    2: 1, # Car 2 is on Team Alpha
    3: 2, # Car 3 is on Team Beta
    4: 2, # Car 4 is on Team Beta
}
BASE_STATION_TEAM_MAPPING = {
    1: 1, # Base Station 1 is for Team Alpha
    2: 2, # Base Station 2 is for Team Beta
}

# Game Constants
PENALTY_DURATION = 10 # seconds
SAFE_ZONE_TIMEOUT = 2 # seconds
COMMAND_TIMEOUT = 2 # seconds. If no command received in this time, assume disconnect.

WEB_COMMANDS = {
    'forward':  {'address': 0x02, 'command': 0x01},
    'backward': {'address': 0x02, 'command': 0x02},
    'left':     {'address': 0x02, 'command': 0x03},
    'right':    {'address': 0x02, 'command': 0x04},
    'stop':     {'address': 0x02, 'command': 0x05},
    'shoot':    {'address': 0x03, 'command': 0x01},
}
# --- End Configuration ---

# Thread-safe data structures
active_clients = {}
active_clients_lock = threading.Lock()
message_queue = Queue()

class GameState:
    def __init__(self):
        self.cars = {}
        self.base_stations = {}
        self.flags = {1: None, 2: None}

    def add_car(self, car_obj):
        self.cars[car_obj.id] = car_obj
    
    def add_base_station(self, bs_obj):
        self.base_stations[bs_obj.id] = bs_obj

    def get_car_by_id(self, car_id):
        return self.cars.get(car_id)

    def get_base_station_by_id(self, bs_id):
        return self.base_stations.get(bs_id)

    def get_device_by_ip(self, ip):
        for car in self.cars.values():
            if car.ip == ip: return car
        for bs in self.base_stations.values():
            if bs.ip == ip: return bs
        return None

    def update_car_safety(self, car_id, is_safe):
        car = self.get_car_by_id(car_id)
        if car:
            if car.is_safe != is_safe:
                car.is_safe = is_safe
                if is_safe:
                    log_with_timestamp(f"[GAME STATE] Car {car_id} ({TEAMS[car.team_id]}) is now in a safe zone.")
                else:
                    log_with_timestamp(f"[GAME STATE] Car {car_id} ({TEAMS[car.team_id]}) has left the safe zone.")

class Device:
    def __init__(self, device_id, ip, client_thread):
        self.id = device_id
        self.ip = ip
        self.client_thread = client_thread
        self.status = "connected"
        self.last_seen = time.time()

    def send_command(self, address, command):
        self.client_thread.send_data(f"{address:02X}{command:02X}\n")

class Car(Device):
    def __init__(self, car_id, ip, client_thread):
        super().__init__(car_id, ip, client_thread)
        self.device_type = "car"
        self.team_id = CAR_TEAM_MAPPING.get(car_id)
        self.is_disabled = False
        self.disabled_until_time = 0
        self.has_flag = False
        self.is_safe = False
        self.last_seen_safe_time = 0.0
        self.control_url = f"http://{socket.gethostbyname(socket.gethostname())}:8000/control/{self.id}"
        self.last_command_time = time.time()
        self.is_moving = False

class BaseStation(Device):
    def __init__(self, bs_id, ip, client_thread):
        super().__init__(bs_id, ip, client_thread)
        self.device_type = "base_station"
        self.team_id = BASE_STATION_TEAM_MAPPING.get(bs_id)

class ClientThread(threading.Thread):
    def __init__(self, conn, addr):
        threading.Thread.__init__(self)
        self.conn = conn
        self.addr = addr
        self.is_connected = True
        self.device = None
        log_with_timestamp(f"[NEW CONNECTION] {self.addr} connected. Starting new thread.")

    def run(self):
        try:
            ip = self.addr[0]
            
            car_config = IP_TO_CAR.get(ip)
            if car_config:
                self.device = Car(car_config['id'], ip, self)
            else:
                bs_config = IP_TO_BASE_STATION.get(ip)
                if bs_config:
                    self.device = BaseStation(bs_config['id'], ip, self)
                else:
                    log_with_timestamp(f"[{ip}] [ERROR] Unknown IP address. Closing connection.")
                    return
            
            with active_clients_lock:
                active_clients[ip] = self.device
            
            message_queue.put(('DEVICE_CONNECT', self.device))

            while self.is_connected:
                data = self.conn.recv(1024)
                if not data: break
                
                received_message = data.decode('utf-8').strip()
                try:
                    event_type, payload = received_message.split(':', 1)
                    
                    if self.device.device_type == "car":
                        if event_type == "CAR_SEEN":
                            seen_ir_address = int(payload, 16)
                            if seen_ir_address in CAR_IR_ADDRESSES:
                                seen_car_id = IR_ADDRESS_TO_CAR_ID[seen_ir_address]
                                message_queue.put(('CAR_SEEN', self.device.id, seen_car_id))
                    
                    elif self.device.device_type == "base_station":
                        if event_type == "BS_SEEN":
                            seen_ir_address = int(payload, 16)
                            if seen_ir_address in CAR_IR_ADDRESSES:
                                seen_car_id = IR_ADDRESS_TO_CAR_ID[seen_ir_address]
                                message_queue.put(('BS_SEEN', self.device.id, seen_car_id))
                except (ValueError, IndexError):
                    log_with_timestamp(f"[{ip}] [ERROR] Invalid message format: {received_message}.")

        except (ConnectionResetError, ConnectionAbortedError):
            log_with_timestamp(f"[ABRUPT DISCONNECTION] {self.addr} unplugged.")
        finally:
            if self.device:
                log_with_timestamp(f"[CLEANUP] Device {self.device.id} at {self.addr} is disconnecting.")
                message_queue.put(('DEVICE_DISCONNECT', self.device.id, self.addr[0]))
            self.conn.close()
            self.is_connected = False
            with active_clients_lock:
                if self.addr[0] in active_clients: del active_clients[self.addr[0]]
            log_with_timestamp(f"[STATUS] {self.addr} thread finished. Active connections: {len(active_clients)}")

    def send_data(self, data):
        try:
            if self.is_connected:
                self.conn.sendall(data.encode('utf-8'))
                log_with_timestamp(f"[{self.addr}] Sent: {data.strip()}")
        except Exception as e:
            log_with_timestamp(f"[{self.addr}] [ERROR] Failed to send data: {e}")

class ServerThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.is_running = True
    def run(self):
        try:
            self.socket.bind((HOST, PORT))
        except OSError as e:
            log_with_timestamp(f"Error binding to port {PORT}: {e}")
            self.is_running = False
            sys.exit()
        self.socket.listen()
        log_with_timestamp(f"Server is listening on {HOST}:{PORT} in a separate thread.")
        while self.is_running:
            try:
                self.socket.settimeout(1.0)
                conn, addr = self.socket.accept()
                new_client_thread = ClientThread(conn, addr)
                new_client_thread.daemon = True
                new_client_thread.start()
            except socket.timeout: continue
            except Exception as e:
                log_with_timestamp(f"An unexpected error occurred in ServerThread: {e}")
                self.is_running = False; break
    def stop(self):
        self.is_running = False
        self.socket.close()

game_state = GameState()
app = Flask(__name__)

INDEX_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Game Server Controls</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; text-align: center; background-color: #f0f0f0; }
        .container { max-width: 600px; margin: 50px auto; padding: 20px; border: 1px solid #ccc; background-color: #fff; border-radius: 10px; }
        h1 { color: #333; }
        ul { list-style-type: none; padding: 0; }
        li { margin: 10px 0; }
        a { text-decoration: none; color: #2196F3; font-size: 1.2em; border: 1px solid #2196F3; padding: 10px 20px; border-radius: 5px; display: inline-block; width: 80%; }
        a:hover { background-color: #2196F3; color: #fff; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Select a Car to Control</h1>
        <ul>
            {% for car in cars.values() %}
            <li><a href="{{ url_for('control_page', car_id=car.id) }}">Car {{ car.id }} ({{ TEAMS[car.team_id] }})</a></li>
            {% else %}
            <li>No cars are currently connected.</li>
            {% endfor %}
        </ul>
    </div>
</body>
</html>
"""

# --- UPDATED: HTML template with landscape layout and proper touch events ---
CONTROL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Car {{ car_id }} Controls</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <style>
        body { font-family: Arial, sans-serif; text-align: center; background-color: #f0f0f0; margin: 0; padding: 0; }
        .controls-container {
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            height: 100vh;
            width: 100%;
        }
        h1 { color: #333; margin: 20px; font-size: 1.5em; }
        
        .d-pad-container {
            display: grid;
            grid-template-areas:
                ". forward ."
                "left . right"
                ". backward .";
            grid-gap: 10px;
            width: 300px;
            height: 300px;
            margin: 20px;
        }

        .control-button {
            width: 100%;
            height: 100%;
            padding: 0;
            font-size: 1.5em;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            color: #fff;
            box-sizing: border-box;
            user-select: none; /* Prevent text selection */
            -webkit-user-select: none;
            -moz-user-select: none;
            -ms-user-select: none;
        }
        
        .forward-btn { background-color: #4CAF50; grid-area: forward; }
        .backward-btn { background-color: #f44336; grid-area: backward; }
        .left-btn { background-color: #2196F3; grid-area: left; }
        .right-btn { background-color: #2196F3; grid-area: right; }
        
        .shoot-button-container {
            display: flex;
            justify-content: center;
            align-items: center;
            width: 300px;
            height: 300px;
            margin: 20px;
        }
        .shoot-btn {
            background-color: #ff9800;
            font-size: 2em;
            border: none;
            border-radius: 50%; /* Make it a circular button */
            width: 150px;
            height: 150px;
            cursor: pointer;
            color: #fff;
            user-select: none;
            -webkit-user-select: none;
            -moz-user-select: none;
            -ms-user-select: none;
        }

        /* --- Media Query for Landscape Mode --- */
        @media (orientation: landscape) {
            .controls-container {
                flex-direction: row;
                justify-content: space-around;
            }
        }
    </style>
</head>
<body>
    <div class="controls-container">
        <div class="shoot-button-container">
            <button class="shoot-btn" onmousedown="sendCommand('shoot')" ontouchstart="sendCommand(event, 'shoot')">SHOOT</button>
        </div>

        <div class="d-pad-container">
            <button class="control-button forward-btn" onmousedown="startContinuousCommand('forward')" onmouseup="stopContinuousCommand()" ontouchstart="startContinuousCommand(event, 'forward')" ontouchend="stopContinuousCommand()">Forward</button>
            <button class="control-button left-btn" onmousedown="startContinuousCommand('left')" onmouseup="stopContinuousCommand()" ontouchstart="startContinuousCommand(event, 'left')" ontouchend="stopContinuousCommand()">Left</button>
            <button class="control-button right-btn" onmousedown="startContinuousCommand('right')" onmouseup="stopContinuousCommand()" ontouchstart="startContinuousCommand(event, 'right')" ontouchend="stopContinuousCommand()">Right</button>
            <button class="control-button backward-btn" onmousedown="startContinuousCommand('backward')" onmouseup="stopContinuousCommand()" ontouchstart="startContinuousCommand(event, 'backward')" ontouchend="stopContinuousCommand()">Backward</button>
        </div>
    </div>
    <script>
        let commandInterval = null;

        function sendCommand(event, action) {
            if (event) event.preventDefault();
            fetch(`/command/{{ car_id }}/` + action)
                .then(response => response.json())
                .then(data => console.log('Command sent:', data))
                .catch(error => console.error('Error:', error));
        }

        function startContinuousCommand(event, action) {
            if (event) event.preventDefault();
            if (commandInterval) {
                clearInterval(commandInterval);
            }
            sendCommand(null, action);
            commandInterval = setInterval(() => sendCommand(null, action), 1000);
        }

        function stopContinuousCommand() {
            if (commandInterval) {
                clearInterval(commandInterval);
                commandInterval = null;
                sendCommand(null, 'stop');
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(INDEX_TEMPLATE, cars=game_state.cars, TEAMS=TEAMS)

@app.route('/control/<int:car_id>')
def control_page(car_id):
    return render_template_string(CONTROL_TEMPLATE, car_id=car_id)

@app.route('/command/<int:car_id>/<string:action>')
def handle_web_command(car_id, action):
    car = game_state.get_car_by_id(car_id)
    if not car:
        return jsonify({"status": "error", "message": "Car not found"}), 404
    
    if car.is_disabled:
        return jsonify({"status": "disabled", "message": "Car is disabled"}), 200

    command_data = WEB_COMMANDS.get(action)
    if command_data:
        car.last_command_time = time.time()
        car.is_moving = (action not in ['stop', 'shoot'])
        
        car.send_command(command_data['address'], command_data['command'])
        log_with_timestamp(f"[WEB COMMAND] Car {car_id} received command: {action}")
        return jsonify({"status": "success", "command": action})
    else:
        return jsonify({"status": "error", "message": "Invalid command"}), 400

def start_web_server():
    app.run(host='0.0.0.0', port=8000, debug=False)

def main_game_loop():
    log_with_timestamp("Main program thread is free and running the game loop.")
    server = ServerThread()
    server.daemon = True
    server.start()
    
    last_print_time = time.time()
    
    try:
        while True:
            current_time = time.time()
            
            for car in game_state.cars.values():
                if car.is_disabled and current_time >= car.disabled_until_time:
                    car.is_disabled = False
                    car.disabled_until_time = 0
                    log_with_timestamp(f"[GAME LOGIC] CAR {car.id} is no longer disabled and can now resume playing.")
                    car.send_command(0x80, 0x02)

                if car.is_safe and (current_time - car.last_seen_safe_time) > SAFE_ZONE_TIMEOUT:
                    game_state.update_car_safety(car.id, False)

                if car.is_moving and (current_time - car.last_command_time) > COMMAND_TIMEOUT:
                    log_with_timestamp(f"[GAME LOGIC] Car {car.id} web control timed out. Sending STOP command.")
                    command_data = WEB_COMMANDS.get('stop')
                    car.send_command(command_data['address'], command_data['command'])
                    car.is_moving = False


            if not message_queue.empty():
                event = message_queue.get()
                event_type = event[0]
                
                if event_type == 'DEVICE_CONNECT':
                    _, device_obj = event
                    if device_obj.device_type == 'car':
                        game_state.add_car(device_obj)
                        log_with_timestamp(f"[DEVICE] Identified CAR {device_obj.id} on {TEAMS[device_obj.team_id]} at {device_obj.ip}. Control at: {device_obj.control_url}")
                    elif device_obj.device_type == 'base_station':
                        game_state.add_base_station(device_obj)
                        log_with_timestamp(f"[DEVICE] Identified BASE STATION {device_obj.id} for {TEAMS[device_obj.team_id]} at {device_obj.ip}")
                
                elif event_type == 'CAR_SEEN':
                    _, shooter_id, target_id = event
                    shooter = game_state.get_car_by_id(shooter_id)
                    target = game_state.get_car_by_id(target_id)
                    if shooter and target and shooter.team_id != target.team_id and not target.is_safe and not target.is_disabled and not shooter.is_disabled:
                        target.is_disabled = True
                        target.disabled_until_time = current_time + PENALTY_DURATION
                        log_with_timestamp(f"[GAME LOGIC] CAR {shooter.id} ({TEAMS[shooter.team_id]}) shot CAR {target.id} ({TEAMS[target.team_id]}). It is now disabled for {PENALTY_DURATION}s.")
                        target.send_command(0x80, 0x01)

                elif event_type == 'BS_SEEN':
                    _, bs_id, car_id = event
                    base_station = game_state.get_base_station_by_id(bs_id)
                    car = game_state.get_car_by_id(car_id)
                    if base_station and car:
                        is_safe = (base_station.team_id == car.team_id)
                        
                        if is_safe:
                            car.last_seen_safe_time = current_time
                        
                        game_state.update_car_safety(car_id, is_safe)
                        
                        if not is_safe and car.has_flag and not car.is_disabled:
                            log_with_timestamp(f"[GAME LOGIC] CAR {car.id} ({TEAMS[car.team_id]}) captured the flag!")
                            game_state.flags[car.team_id] = None
                            car.has_flag = False
                
                elif event_type == 'DEVICE_DISCONNECT':
                    _, device_id, ip = event
                    log_with_timestamp(f"[GAME LOGIC] Device {device_id} at {ip} disconnected.")
                    if device_id in game_state.cars: del game_state.cars[device_id]
                    if device_id in game_state.base_stations: del game_state.base_stations[device_id]
            
    except KeyboardInterrupt:
        log_with_timestamp("\nShutting down main program and server.")
    finally:
        server.stop()
        log_with_timestamp("Server thread stopped.")
        sys.exit(0)

if __name__ == "__main__":
    game_loop_thread = threading.Thread(target=main_game_loop)
    game_loop_thread.daemon = True
    game_loop_thread.start()
    
    web_server_thread = threading.Thread(target=start_web_server)
    web_server_thread.daemon = True
    web_server_thread.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log_with_timestamp("\nMain thread received interrupt, shutting down.")
        sys.exit(0)