#include <WiFi.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <IRutils.h>

#define FL_PIN 26
#define BL_PIN 14
#define FR_PIN 12
#define BR_PIN 13
#define SH_PIN 25

// --- WiFi Configuration ---
const char* ssid = "OpenMicroCar";
const char* password = "vroomvroom";
const char* serverIp = "192.168.77.2"; 
const int serverPort = 5000;

// --- Static IP Configuration ---
// Adjust these values for your specific network
IPAddress staticIP(192, 168, 77, 51);
IPAddress gateway(192, 168, 77, 1);
IPAddress subnet(255, 255, 255, 0);

WiFiClient client;

// --- Car and IR Configuration ---
const long CAR_IR_ADDRESS = 0x01; 

const int IR_EMITTER_PIN = 4;   // Pin connected to the IR LED
const int IR_RECEIVER_PIN = 27; // Pin connected to the IR receiver's OUT pin

IRsend irsend(IR_EMITTER_PIN);
IRrecv irrecv(IR_RECEIVER_PIN);
decode_results results;

// --- Game State Variables ---
bool is_disabled = false;
unsigned long lastIrBroadcast = 0;
const int IR_BROADCAST_INTERVAL = 500; // milliseconds

int shoot_timer = 0;

// --- Functions ---
void connectToServer() {
  if (client.connect(serverIp, serverPort)) {
    Serial.println("Connected to server!");
  } else {
    Serial.println("Connection failed. Retrying in 5 seconds...");
    delay(5000);
  }
}

void sendData(String data) {
  if (client.connected()) {
    client.print(data);
  } else {
    Serial.println("Client not connected. Data not sent.");
    connectToServer(); // Try to reconnect
  }
}

void handleServerCommands() {
  if (client.available()) {
    String server_command = client.readStringUntil('\n');
    Serial.print("Received server command: ");
    Serial.println(server_command);

    if (server_command.length() == 4) {
      long command_address = strtol(server_command.substring(0, 2).c_str(), NULL, 16);
      long command_value = strtol(server_command.substring(2, 4).c_str(), NULL, 16);

      if (command_address == 0x80) { 
        if (command_value == 0x01) {
          is_disabled = true;
          Serial.println("SERVER COMMAND: Car has been disabled!");
        } else if (command_value == 0x02) {
          is_disabled = false;
          Serial.println("SERVER COMMAND: Car has been re-enabled!");
        }
      } else if (command_address == 0x02) {
        if (command_value == 0x01) {
          digitalWrite(FL_PIN, 1);
          digitalWrite(FR_PIN, 1);
          digitalWrite(BL_PIN, 0);
          digitalWrite(BR_PIN, 0);
        } else if (command_value == 0x02) {
          digitalWrite(FL_PIN, 0);
          digitalWrite(FR_PIN, 0);
          digitalWrite(BL_PIN, 1);
          digitalWrite(BR_PIN, 1);
        } else if (command_value == 0x03) {
          digitalWrite(FL_PIN, 0);
          digitalWrite(FR_PIN, 1);
          digitalWrite(BL_PIN, 1);
          digitalWrite(BR_PIN, 0);
        } else if (command_value == 0x04) {
          digitalWrite(FL_PIN, 1);
          digitalWrite(FR_PIN, 0);
          digitalWrite(BL_PIN, 0);
          digitalWrite(BR_PIN, 1);
        } else if (command_value == 0x05) {
          digitalWrite(FL_PIN, 0);
          digitalWrite(FR_PIN, 0);
          digitalWrite(BL_PIN, 0);
          digitalWrite(BR_PIN, 0);
        }
      } else if (command_address == 0x03) {
        if (command_value == 0x01) {
          shoot_timer = millis();
        }
      }
    }
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(FL_PIN, OUTPUT);
  pinMode(FR_PIN, OUTPUT);
  pinMode(BL_PIN, OUTPUT);
  pinMode(BR_PIN, OUTPUT);
  pinMode(SH_PIN, OUTPUT);

  randomSeed(analogRead(0));

  WiFi.config(staticIP, gateway, subnet);

  delay(100);

  // Connect to WiFi
  Serial.println("Connecting to WiFi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected to WiFi!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  // Initialize the IR receiver and sender using the IRremoteESP8266 API
  irrecv.enableIRIn(); // This is the old API, but it's used for this library
  irsend.begin();
  Serial.println("IR system enabled.");

  connectToServer();
}

uint32_t NECCode(uint8_t address, uint8_t command) {
  uint32_t necCode = 0;

  // Find the bitwise NOT of the address and command
  uint8_t address_inv = ~address; 
  uint8_t command_inv = ~command;
  necCode |= (uint32_t)address << 24;
  necCode |= (uint32_t)address_inv << 16;
  necCode |= (uint32_t)command << 8;
  necCode |= (uint32_t)command_inv << 0;

  return necCode;
}

void loop() {
  unsigned long currentTime = millis();

  if (shoot_timer + 100 > millis()) {
    digitalWrite(SH_PIN, 1);
  } else {
    digitalWrite(SH_PIN, 0);
  }

  // --- Task 1: Broadcast our own IR address ---
  if (currentTime - lastIrBroadcast > IR_BROADCAST_INTERVAL + random(0,100) && !is_disabled) { // The random function adds up to a 100ms jitter to hopefully prevent IR collisions. Each transmission will take about 70 ms, so collisions are very probable.
    irsend.send(NEC, NECCode(CAR_IR_ADDRESS,0), 32);
    lastIrBroadcast = currentTime;
  }

  // --- Task 2: Listen for and process incoming IR signals ---
  if (irrecv.decode(&results)) {
    // The IRremoteESP8266 library returns protocol types slightly differently
    if (results.decode_type == NEC) {
      long seenIrAddress = results.value;
      Serial.print("Received NEC Address: ");
      Serial.println(seenIrAddress, HEX);

      char hex_buffer[3];
      sprintf(hex_buffer, "%02X", seenIrAddress);
      
      String message = "CAR_SEEN:";
      message += hex_buffer;
      message += "\n";
      
      sendData(message);
    }
    irrecv.resume();
  }
  
  // --- Task 3: Handle commands from the server ---
  handleServerCommands();

  // --- Main Car Logic ---
  if (!is_disabled) {
    // Car is enabled, run motors, etc.
  } else {
    // Car is disabled, stop motors, etc.
  }
  
  if (!client.connected()) {
    connectToServer();
  }
}