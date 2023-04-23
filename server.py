import asyncio
import websockets
import uuid
import json
import os
import base64
from collections import defaultdict

# utility functions

# find key if value exists in a a dict


def find_key_by_value(d, value):
    return [k for k, v in d.items() if v == value]

# get json obj


def get_json_obj(message):
    msg_obj = json.loads(message)
    return msg_obj


class WebSocketServer:
    # websocket constructor
    def __init__(self, host, port):
        self.host = host
        self.port = port
        # set of all connections
        self.connections = set()
        # dict of the client username mapped to session id
        self.client_username_to_session_id = dict()
        self.active_host_username_to_session_id = dict()
        self.client_data_host = defaultdict(dict)
        self.socket_id_to_socket = dict()

    # This method handles a new connection and adds it to a set
    # of all connections
    async def handle_new_connection(self, websocket):
        print(">> New incoming connection!")
        session_id = str(uuid.uuid4())
        websocket.id = session_id
        self.connections.add(session_id)
        self.socket_id_to_socket[websocket.id] = websocket
        print(">> Connection ID: " + session_id)

    async def init_client(self, websocket, msg_obj):
        print(f">> Client {websocket.id} initializing!")
        if websocket.id in self.connections:
            self.client_username_to_session_id[msg_obj["username"]
                                               ] = websocket.id
            self.client_data_host[msg_obj["username"]] = dict()
            resp = {
                "status": "Success",
                "message": msg_obj["username"],
                "requestType": "Init"
            }
            await websocket.send(json.dumps(resp))
            print(f">> Client {websocket.id} username: " + msg_obj["username"])
        else:
            err_msg = "Connection with id: " + websocket.id + " does not exist"
            print("ERROR: " + err_msg)
            print(">> Active Connections: " + self.connections)
            resp = {
                "status": "Failure",
                "message": err_msg,
                "requestType": "Init"
            }
            print("ERROR: Client username registration failed!")
            await websocket.send(json.dumps(resp))
    # This method handles client messages

    async def init_host(self, websocket, msg_obj):
        print(f">> Host {websocket.id} initializing!")
        if websocket.id in self.connections:
            self.active_host_username_to_session_id[msg_obj["username"]
                                                    ] = websocket.id
            resp = {
                "status": "Success",
                "message": msg_obj["username"],
                "requestType": "Init"
            }
            await websocket.send(json.dumps(resp))
            print(
                f">> Host {websocket.id} online with username: " + msg_obj["username"])
        else:
            err_msg = "Connection with id: " + websocket.id + " does not exist"
            print("ERROR: " + err_msg)
            print(">> Active Connections: " + self.connections)
            resp = {
                "status": "Failure",
                "message": err_msg,
                "requestType": "Init"
            }
            print("ERROR: Host username registration failed!")
            await websocket.send(json.dumps(resp))

    async def send_file_to_host(self, websocket, msg_obj):
        print(">> Finding availablke host")
        try:
            available_host_username = next(
                iter(self.active_host_username_to_session_id))
            available_host_id = self.active_host_username_to_session_id[available_host_username]
            print(">> Host available with username " +
                  available_host_username + " id " + available_host_id)
            available_host_socket = self.socket_id_to_socket[available_host_id]
            # available =host socket is the socket of the host I will request a file from
            # Open the file in binary mode and read its contents
            filename = msg_obj["filename"]
            with open(filename, "rb") as file:
                file_contents = file.read()
            print(">> Matching file found: " + filename)
            # Encode the file contents as a base64 string
            b64_string = base64.b64encode(file_contents).decode('utf-8')
            req = {
                "requestType": "SaveFile",
                "filename": filename,
                "body": b64_string
            }

            self.client_data_host[msg_obj["username"]
                                  ][filename] = available_host_id
            print(">> Sending file with filename " + filename)

            await available_host_socket.send(json.dumps(req))
        except StopIteration as e:
            resp = {
                "status": "Failure",
                "message": "No available host at the moment",
                "requestType": "SaveFile"
            }
            print("ERROR: Host username registration failed!")
            # this is the client websocket the error will be sent to
            await websocket.send(json.dumps(resp))

    async def client_save_file(self, websocket, msg_obj):
        username = find_key_by_value(
            self.client_username_to_session_id, websocket.id)
        print(">> Client Save file initializing")
        if username:
            print(">> Matching username found ")
            print(username)
            filename = msg_obj["filename"]
            data = msg_obj["message"]

            # decode base64 string to bytes
            decoded_bytes = base64.b64decode(data)
            # write bytes to file
            with open(filename, "wb") as f:
                f.write(decoded_bytes)
            suc_msg = "File created with name: " + filename + \
                " with size: " + str(os.stat(filename).st_size)
            print(">> " + suc_msg)
            await self.send_file_to_host(websocket, msg_obj)
            resp = {
                "status": "Success",
                "message": suc_msg,
                "requestType": "SaveFile"
            }
            print(">> Dict in client " +
                  msg_obj["username"] + " : ")
            print(self.client_data_host[msg_obj["username"]])
            await websocket.send(json.dumps(resp))
        else:
            print("ERROR: Client not initialized properly")
            resp = {
                "status": "Failure",
                "message": "Client not initialized properly",
                "requestType": "SaveFile"
            }
            await websocket.send(json.dumps(resp))

    async def client_retrieve_file(self, websocket, msg_obj):
        username = find_key_by_value(
            self.client_username_to_session_id, websocket.id)
        print(">> Client Retrieve file initializing")
        if username:
            print(">> Matching username found ")
            print(username)
            filename = msg_obj["filename"]
            # Open the file in binary mode and read its contents
            with open(filename, "rb") as file:
                file_contents = file.read()
            print(">> Matching file found: " + filename)
            # Encode the file contents as a base64 string
            b64_string = base64.b64encode(file_contents).decode('utf-8')
            resp = {
                "status": "Success",
                "message": filename,
                "body": b64_string,
                "requestType": "RetrieveFile"
            }
            await websocket.send(json.dumps(resp))
            print(">> File retrieved: " + filename)
        else:
            print("ERROR: Client not initialized properly")
            resp = {
                "status": "Failure",
                "message": "Client not initialized properly",
                "requestType": "RetrieveFile"
            }
            await websocket.send(json.dumps(resp))

    # async def handle_client_message(self, websocket, message):
    #     username = find_key_by_value(
    #         self.client_username_to_session_id, websocket.id)
    #     if username:
    #         print(
    #             f"Received message: {message} from client {username} with id {websocket.id}")
    #         resp = {
    #             "status": "Success",
    #             "message": message,
    #             "requestType": "RetrieveFile"
    #         }
    #         await websocket.send(json.dumps(resp))
    #     else:
    #         resp = {
    #             "status": "Fail",
    #             "message": "Connection not initialized properly"
    #         }
    #         await websocket.send(json.dumps(resp))

    async def handle_disconnect(self, websocket):
        print(f"{websocket.id} disconnected")

        self.clients.remove(websocket)

    async def server(self, websocket, path):
        await self.handle_new_connection(websocket)
        try:
            async for message in websocket:
                json_obj = get_json_obj(message)
                request_type = json_obj["requestType"]
                entity_type = json_obj["entityType"]
                if request_type == "Init":
                    if entity_type == "Client":
                        await self.init_client(websocket, json_obj)
                    elif entity_type == "Host":
                        await self.init_host(websocket, json_obj)
                elif request_type == "SaveFile":
                    if entity_type == "Client":
                        await self.client_save_file(websocket, json_obj)
                    elif entity_type == "Host":
                        # await self.client_save_file(websocket, json_obj)
                        pass

                elif request_type == "RetrieveFile":
                    if entity_type == "Client":
                        await self.client_retrieve_file(websocket, json_obj)
                else:
                    # await self.handle_client_message(websocket, message)
                    pass
                # elif request_type == "saveFile":
                #     # saveFile()
                #     pass
                # elif request_type == "retrieveFile":
                #     # retrieveFile()
                #     pass
        except websockets.exceptions.ConnectionClosed:
            pass

        await self.handle_client_disconnect(websocket)

    async def start_server(self):
        self.server = await websockets.serve(self.server, self.host, self.port)
        print(f"WebSocket server listening on {self.host}:{self.port}")
        await self.server.wait_closed()

    async def stop_server(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None


if __name__ == "__main__":
    server = WebSocketServer("localhost", 3000)
    asyncio.run(server.start_server())
