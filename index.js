// Required modules
const express = require("express");
const http = require("http");
const socketio = require("socket.io");

// Initialize app and server
const app = express();
const server = http.createServer(app);
const io = socketio(server);

// DATA STRUCTURES
const activeHosts = {}; // table of active hosts (save socket connection id)
const dataPointerTable = {}; // 2 layered data pointer table (client id -> Data filename -> [host_id])

// Handle host connectiongit 
io.on("connection", (socket) => {
  console.log(`Entity connected: ${socket.id}`);
  // Check if connection has entityType and entityId query parameters
  const { entityType, entityId } = socket.handshake.query;
  if (entityType === "client" && entityId) {
    console.log(`Client connected with ID ${entityId}`);
  } else if (entityType === "host" && entityId) {
    console.log(`Host connected with ID ${entityId}`);
  } else {
    // Send a message to the entity before closing the connection
    socket.emit("error", "Invalid connection parameters");
    socket.disconnect();
  }
});

// Start server
const port = process.env.PORT || 3000;
server.listen(port, () => {
  console.log(`Server listening on port ${port}`);
});
