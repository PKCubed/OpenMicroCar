import socket
import threading
import sys
import time

# Define the host and port
HOST = '0.0.0.0'
PORT = 5000

IP_SUBNET = (192, 168, 77, 0)

BASE_1_IP = 11
BASE_2_IP = 12

CAR_STARTING_IP = 21

# A list to keep track of all active client threads
active_clients = []

class Car:
    def __init__(self, conn, addr):
        self.conn = conn
        self.ip = addr
        self.safe = False

def handle_client(conn, addr):
    """
    Handles all communication with a single client in its own thread.
    """
    print(f"[NEW CONNECTION] {addr} connected.")

    ip_address = addr.split(".")
    for i in range(len(ip_address)):
        ip_address[i] = int(i)

    # Check if this is an IP address within range of our game subnet
    valid_subnet = True
    if i in range(3):
        if ip_address[i] != IP_SUBNET[i]:
            # This IP Address is not within the game subnet.
            valid_subnet = False

    # Add this client connection to the global list
    if valid_subnet:
        active_clients.append(conn)
    else:
        conn.close()
        return # If the client's IP address is not within the game subnet, we will not accept the connection

    # Check if this client's IP address is in the car region
    car = None
    if ip_address[3] > CAR_STARTING_IP:
        car = Car(ip_address)
        cars[ip_address[3]-CAR_STARTING_IP] = car
        print(f"Car {ip_address[3]-CAR_STARTING_IP} has connected")
    

    try:
        while True:
            # The recv() function returns an empty bytes object if the client
            # closes the connection gracefully (or with a FIN packet).
            data = conn.recv(1024)
            if not data:
                print(f"[DISCONNECTION] {addr} disconnected gracefully.")
                break
            
            # Decode the received data and strip whitespace
            received_message = data.decode('utf-8').strip()
            message = received_message.split(":")
            message_type = message[0]
            message_data = message[1]
            print(f"[MESSAGE from {addr}] {received_message}")
            
            # --- Your existing message processing logic goes here ---
            if message_type == "IR":
                try:
                    address_str = message_data[:2]
                    command_str = message_data[2:]

                    address = int(address_str, 16)
                    command = int(command_str, 16)

                    print(f"  - Decoded Address: 0x{address:02X} (Decimal: {address})")
                    print(f"  - Decoded Command: 0x{command:02X} (Decimal: {command})")
                    
                    # Add your specific logic here (e.g., control a device)
                    # if address == 0x01 and command == 0x23:
                    #   # Do something

                    if addr == IP_SUBNET+"."+str(BASE_1_IP): # This is team 1's base station
                        print("This is base 1")

                    
                except ValueError:
                    print(f"  - [ERROR] Could not parse hex code from {received_message}.")
            else:
                print(f"  - [ERROR] Invalid message length from {received_message}.")
                
    except (ConnectionResetError, ConnectionAbortedError):
        # This exception is raised when the client loses power or unplugs
        # This is how you detect the "unplug" scenario
        print(f"[ABRUPT DISCONNECTION] {addr} unplugged.")
        
    finally:
        # This block ensures the connection is closed and the client is removed
        # from our list, regardless of how it disconnected.
        conn.close()
        if conn in active_clients:
            active_clients.remove(conn)
        print(f"[STATUS] Active connections: {len(active_clients)}")

cars = {}

def start_server():
    """
    Main function to start the server and listen for new clients.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, PORT))
        except OSError as e:
            print(f"Error binding to port {PORT}: {e}")
            print("Is another program already using this port?")
            sys.exit()

        s.listen()
        print(f"Server is listening on {HOST}:{PORT}")
        print("Waiting for clients...")

        while True:
            try:
                # This line blocks, waiting for a new connection
                conn, addr = s.accept()
                
                # Create a new thread to handle this new client
                client_thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                client_thread.start()
                
            except KeyboardInterrupt:
                print("\nServer is shutting down.")
                break

if __name__ == "__main__":
    start_server()