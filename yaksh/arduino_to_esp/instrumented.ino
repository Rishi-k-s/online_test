void setup() {
  pinMode(10, OUTPUT        // Set pin 13 as output
  ESP_LOGI(TAG, "PIN 10, HIGH");;    // Turn ON LED on pin 13

  Serial.begin(9600);        // Start serial communication
  Serial.println("Hello World");
}

void loop() {
  // Nothing to repeat
}