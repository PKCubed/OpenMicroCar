#define M1C1 18
#define M1C2 19
#define M1PWM 4

void setup() {
  Serial.begin(115200);
  pinMode(M1C1, OUTPUT); 
  pinMode(M1C2, OUTPUT); 
  pinMode(M1PWM, OUTPUT);

  digitalWrite(M1C1, HIGH);
  digitalWrite(M1C2, LOW);
}

void loop() {
  Serial.println("On");
  analogWrite(M1PWM, 254);
  delay(1000);
  Serial.println("Off");
  analogWrite(M1PWM, 1);
  delay(1000);
}
