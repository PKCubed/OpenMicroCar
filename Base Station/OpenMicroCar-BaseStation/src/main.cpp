#include <Arduino.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRutils.h>
#include <ESP8266WiFi.h>

// Initialize Wifi Stuff
  const char* ssid = "OpenMicroCar";
  const char* password = "vroomvroom";

  // Set your static IP address
  IPAddress staticIP(192, 168, 77, 11); // For example: 192.168.1.100
  IPAddress gateway(192, 168, 0, 1);    // For example: 192.168.1.1 (your router's IP)
  IPAddress subnet(255, 255, 0, 0);   // Subnet mask
  IPAddress dns1(8, 8, 8, 8);           // Google's primary DNS server
  IPAddress dns2(8, 8, 4, 4);           // Google's secondary DNS server
  WiFiClient client;

  // Server details
  const char* serverIp = "192.168.77.2"; // <-- Change this to your computer's IP address
  const int serverPort = 5000;          // <-- The port your Python server will listen on



// Initialize IR Stuff
  const int RECV_PIN = 2;  // Define the pin connected to the IR receiver signal line
  IRrecv irrecv(RECV_PIN);
  decode_results results;
  struct NecCodeData {
    uint8_t address;
    uint8_t command;
  };

  NecCodeData received_data;

NecCodeData decodeNecCode(uint32_t necCode) { // Convert the Nec encoded address and data to integers
  NecCodeData decodedData;
  decodedData.address = (necCode >> 24) & 0xFF;
  decodedData.command = (necCode >> 8) & 0xFF;
  return decodedData;
}

void setup() {
  Serial.begin(115200);  // Initialize the serial console

  // Print initial message
  Serial.println();
  Serial.println("Connecting to WiFi with static IP...");

  // Configure WiFi with static IP
  WiFi.config(staticIP, gateway, subnet, dns1, dns2);
  
  // Connect to the WiFi network
  WiFi.begin(ssid, password);

  // Wait for connection
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  // Connection successful
  Serial.println("");
  Serial.println("WiFi connected!");
  Serial.print("Assigned IP Address: ");
  Serial.println(WiFi.localIP());

  irrecv.enableIRIn();   // Start the IR receiver
  Serial.println("IR receiver enabled. Listening for NEC protocol signals...");
}

void loop() {
  if (client.connected()) { // If we are connected to the server
    if (irrecv.decode(&results)) {
      // Check if the decoded protocol is NEC
      if (results.decode_type == NEC) {
        received_data = decodeNecCode(results.value);
        
        client.printf("BS_SEEN:%02X\n", received_data.address);
        Serial.printf("Received: %02X%02X\n", received_data.address, received_data.command);
      } else {
        // If it's not NEC, you can print a message to the console
        Serial.println("X");
      }
      // Resume receiving the next IR signal
      irrecv.resume();
    }
  } else { // If we are not connected to the server
    Serial.print("Connecting to server at ");
    Serial.print(serverIp);
    Serial.print(":");
    Serial.println(serverPort);

    // Try to connect to the server
    if (client.connect(serverIp, serverPort)) {
      Serial.println("Connected to server!");
    } else {
      Serial.println("Connection failed. Retrying in 1 seconds...");
      // Wait before retrying
      delay(1000);
      return;
    }
  }
}