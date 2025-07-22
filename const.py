"""Constants for the ICE HA Server integration."""

DOMAIN = "ice_ha"
WEBSOCKET_PORT = 8765  # Default port for the WebSocket server
HEARTBEAT_TIMEOUT = 5 # Seconds without a heartbeat before marking PC offline

# Config Flow Keys
CONF_PC_IP = "pc_ip"
CONF_PC_NAME = "pc_name"