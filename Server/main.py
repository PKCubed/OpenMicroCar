import socket
import threading
import sys
import time
from queue import Queue

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
SAFE_ZONE_TIMEOUT = 1 # seconds
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
                    print(f"[GAME STATE] Car {car_id} ({TEAMS[car.team_id]}) is now in its safe zone.")
                else:
                    print(f"[GAME STATE] Car {car_id} ({TEAMS[car.team_id]}) has left its safe zone.")

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
        print(f"[NEW CONNECTION] {self.addr} connected. Starting new thread.")

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
                    print(f"[{ip}] [ERROR] Unknown IP address. Closing connection.")
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
                    print(f"[{ip}] [ERROR] Invalid message format: {received_message}.")

        except (ConnectionResetError, ConnectionAbortedError):
            print(f"[ABRUPT DISCONNECTION] {self.addr} unplugged.")
        finally:
            if self.device:
                print(f"[CLEANUP] Device {self.device.id} at {self.addr} is disconnecting.")
                message_queue.put(('DEVICE_DISCONNECT', self.device.id, self.addr[0]))
            self.conn.close()
            self.is_connected = False
            with active_clients_lock:
                if self.addr[0] in active_clients: del active_clients[self.addr[0]]
            print(f"[STATUS] {self.addr} thread finished. Active connections: {len(active_clients)}")

    def send_data(self, data):
        try:
            if self.is_connected:
                self.conn.sendall(data.encode('utf-8'))
                print(f"[{self.addr}] Sent: {data.strip()}")
        except Exception as e:
            print(f"[{self.addr}] [ERROR] Failed to send data: {e}")

class ServerThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.is_running = True
    def run(self):
        try:
            self.socket.bind((HOST, PORT))
        except OSError as e:
            print(f"Error binding to port {PORT}: {e}")
            self.is_running = False
            sys.exit()
        self.socket.listen()
        print(f"Server is listening on {HOST}:{PORT} in a separate thread.")
        while self.is_running:
            try:
                self.socket.settimeout(1.0)
                conn, addr = self.socket.accept()
                new_client_thread = ClientThread(conn, addr)
                new_client_thread.daemon = True
                new_client_thread.start()
            except socket.timeout: continue
            except Exception as e:
                print(f"An unexpected error occurred in ServerThread: {e}")
                self.is_running = False; break
    def stop(self):
        self.is_running = False
        self.socket.close()

def main_game_loop():
    print("Main program thread is free and running the game loop.")
    game_state = GameState()
    server = ServerThread()
    server.daemon = True
    server.start()
    
    # --- NEW: Variable to track the last time we printed the status ---
    last_print_time = time.time()
    
    try:
        while True:
            current_time = time.time()
            
            # Check for expired penalties and re-enable cars
            for car in game_state.cars.values():
                if car.is_disabled and current_time >= car.disabled_until_time:
                    car.is_disabled = False
                    car.disabled_until_time = 0
                    print(f"[GAME LOGIC] CAR {car.id} is no longer disabled and can now resume playing.")
                    car.send_command(0x80, 0x02)

                # Check if the safe zone timeout has expired
                if car.is_safe and (current_time - car.last_seen_safe_time) > SAFE_ZONE_TIMEOUT:
                    game_state.update_car_safety(car.id, False)

            if not message_queue.empty():
                event = message_queue.get()
                event_type = event[0]
                
                if event_type == 'DEVICE_CONNECT':
                    _, device_obj = event
                    if device_obj.device_type == 'car':
                        game_state.add_car(device_obj)
                        print(f"[DEVICE] Identified CAR {device_obj.id} on {TEAMS[device_obj.team_id]} at {device_obj.ip}")
                    elif device_obj.device_type == 'base_station':
                        game_state.add_base_station(device_obj)
                        print(f"[DEVICE] Identified BASE STATION {device_obj.id} for {TEAMS[device_obj.team_id]} at {device_obj.ip}")
                
                elif event_type == 'CAR_SEEN':
                    _, shooter_id, target_id = event
                    shooter = game_state.get_car_by_id(shooter_id)
                    target = game_state.get_car_by_id(target_id)
                    if shooter and target and shooter.team_id != target.team_id and not target.is_safe and not target.is_disabled and not shooter.is_disabled:
                        target.is_disabled = True
                        target.disabled_until_time = current_time + PENALTY_DURATION
                        print(f"[GAME LOGIC] CAR {shooter.id} ({TEAMS[shooter.team_id]}) shot CAR {target.id} ({TEAMS[target.team_id]}). It is now disabled for {PENALTY_DURATION}s.")
                        target.send_command(0x80, 0x01)

                elif event_type == 'BS_SEEN':
                    _, bs_id, car_id = event
                    base_station = game_state.get_base_station_by_id(bs_id)
                    car = game_state.get_car_by_id(car_id)
                    if base_station and car:
                        is_safe = (base_station.team_id == car.team_id) # Is this car on the same team as the base station?
                        
                        if is_safe:
                            car.last_seen_safe_time = current_time
                        
                        game_state.update_car_safety(car_id, is_safe)
                        
                        if not is_safe and car.has_flag and not car.is_disabled:
                            print(f"[GAME LOGIC] CAR {car.id} ({TEAMS[car.team_id]}) captured the flag!")
                            game_state.flags[car.team_id] = None
                            car.has_flag = False
                
                elif event_type == 'DEVICE_DISCONNECT':
                    _, device_id, ip = event
                    print(f"[GAME LOGIC] Device {device_id} at {ip} disconnected.")
                    if device_id in game_state.cars: del game_state.cars[device_id]
                    if device_id in game_state.base_stations: del game_state.base_stations[device_id]
            
            # --- NEW: Print status every second, but don't block the loop ---
            if (current_time - last_print_time) >= 1.0:
                #print(f"Game is running... Active devices: {len(active_clients)}")
                last_print_time = current_time

    except KeyboardInterrupt:
        print("\nShutting down main program and server.")
    finally:
        server.stop()
        print("Server thread stopped.")
        sys.exit(0)

if __name__ == "__main__":
    main_game_loop()