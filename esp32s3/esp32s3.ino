/*  ╔══════════════════════════════════════════════════════════════╗
    ║         Robot Arm - ESP32-S3  ·  WiFi TCP Server             ║
    ║  Receives a movement index (0-4) over TCP and drives servos  ║
    ╚══════════════════════════════════════════════════════════════╝
    Cableado I2C:
      SDA → GPIO 11
      SCL → GPIO 12
*/

#include <WiFi.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ── WiFi credentials ───────────────────────────────────────────────────────
#define USE_AP_MODE
const char* AP_SSID     = "RobotArm";
const char* AP_PASSWORD = "robot1234";

const uint16_t TCP_PORT = 8080;

// ── Hardware ───────────────────────────────────────────────────────────────
Adafruit_PWMServoDriver servos = Adafruit_PWMServoDriver(0x40);

const int servosNumber = 10;
const int I2C_SDA = 11;
const int I2C_SCL = 12;

int inputMov = 0;
int lastMov  = -1;
int logico   = 0;
int real_ang = 0;


int movementTable[5][10] = {
  { 0,   0,   0,   0,   0,   20,  15, 15, 20,  90},  // 0 – basal
  {150, 150, 165, 150, 100,  20,  15, 15, 20,   0},  // 1 – cilíndrico
  {40,  40,  55,  40,  100,  20,  15, 20, 25,   0},  // 2 – esférico
  {180, 170, 150,  100,  125, 20,  15, 15, 25,  95},  // 3 – llave      
  {180, 180, 140, 90,  130, 20,  15, 15, 15,  45}   // 4 – pinza      
};

const bool servoInvertido[servosNumber] = {
  true, true, false, false, true, false, false, false, false, false
};

// ── TCP server ─────────────────────────────────────────────────────────────
WiFiServer server(TCP_PORT);
WiFiClient connectedClient;

// ── Helpers ────────────────────────────────────────────────────────────────
int anguloFisico(int servo, int anguloLogico) {
  return servoInvertido[servo] ? 180 - anguloLogico : anguloLogico;
}

void setServo(uint8_t n_servo, int angulo) {
  int duty = map(angulo, 0, 180, 75, 562);
  servos.setPWM(n_servo, 0, duty);
}

void setPosition(int mov) {
  if (mov < 0 || mov > 4) {
    Serial.println("Movimiento inválido");
    return;
  }
  const char* nombres[] = {
    "Basal", "Agarre cilíndrico", "Agarre esférico", "Agarre llave", "Pinza de dos dedos"
  };
  Serial.printf("Ejecutando mov %d: %s\n", mov, nombres[mov]);

  for (int i = 0; i < servosNumber; i++) {
    logico   = movementTable[mov][i];
    real_ang = anguloFisico(i, logico);
    setServo(i, real_ang);
  }
}

void sendStatus(WiFiClient& client, int mov, bool ok) {
  const char* nombres[] = {
    "basal", "cilindrico", "esferico", "llave", "pinza"
  };
  char buf[128];

  String ip = (WiFi.getMode() == WIFI_AP)
             ? WiFi.softAPIP().toString()
              : WiFi.localIP().toString();

  snprintf(buf, sizeof(buf),
    "{\"status\":\"%s\",\"mov\":%d,\"name\":\"%s\",\"ip\":\"%s\"}\n",
    ok ? "ok" : "error",
    mov,
    (mov >= 0 && mov <= 4) ? nombres[mov] : "unknown",
    ip.c_str()
  );
  client.print(buf);
}

// ── Setup ──────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== Robot Arm - WiFi TCP Server ===");

  // I2C + PCA9685
  Wire.begin(I2C_SDA, I2C_SCL);
  servos.begin();
  servos.setPWMFreq(50);
  setPosition(0);  

  // WiFi
#ifdef USE_AP_MODE
  WiFi.softAP(AP_SSID, AP_PASSWORD);
  Serial.printf("AP activo  →  SSID: %s   IP: %s\n",
                AP_SSID, WiFi.softAPIP().toString().c_str());
#else
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Conectando a ");
  Serial.print(WIFI_SSID);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nConectado  →  IP: %s\n", WiFi.localIP().toString().c_str());
#endif

  server.begin();
  Serial.printf("TCP server escuchando en puerto %d\n", TCP_PORT);
}

// ── Loop ───────────────────────────────────────────────────────────────────
void loop() {
  // ── Aceptar nuevas conexiones ──────────────────────────────────────────
  if (!connectedClient || !connectedClient.connected()) {
    connectedClient = server.accept();
    if (connectedClient) {
      Serial.printf("Cliente conectado: %s\n",
                    connectedClient.remoteIP().toString().c_str());
      connectedClient.setTimeout(200);  

      sendStatus(connectedClient, lastMov, true);
    }
  }

  // ── Leer datos del cliente ─────────────────────────────────────────────
  if (connectedClient && connectedClient.connected() && connectedClient.available()) {
    String line = connectedClient.readStringUntil('\n');
    line.trim();

    if (line.length() == 0) {
      return;  
    }

    int mov = line.toInt();
    Serial.printf("Recibido: \"%s\"  →  mov = %d\n", line.c_str(), mov);

    if (mov >= 0 && mov <= 4) {
      inputMov = mov;
      if (inputMov != lastMov) {
        lastMov = inputMov;
        setPosition(inputMov);
        sendStatus(connectedClient, inputMov, true);
      } else {
        sendStatus(connectedClient, inputMov, true);
      }
    } else {
      Serial.println("Índice de movimiento fuera de rango (0-4)");
      sendStatus(connectedClient, mov, false);
    }
  }

  // ── Keepalive: reconexión automática WiFi ──────────────────────────────
#ifndef USE_AP_MODE
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi caído, reconectando...");
    WiFi.reconnect();
    delay(1000);
  }
#endif
}
