import asyncio
import websockets
import uuid
import json
import os
import base64
import queue
from collections import defaultdict


dir = "files"

# utility functions

# find key if value exists in a a dict


def find_key_by_value(d, value):
    return [k for k, v in d.items() if v == value]

# get json obj


def get_json_obj(message):
    msg_obj = json.loads(message)
    return msg_obj


def remove_element(q, x):
    new_q = queue.Queue()
    while not q.empty():
        item = q.get()
        if item != x:
            new_q.put(item)
    return new_q


def get_choice(hosts_list, q):
    for host in hosts_list:
        if host not in q.queue:
            q.put(host)
    lru_item = q.get()
    q.put(lru_item)
    return lru_item


class WebSocketServer:
    # websocket constructor
    def __init__(self, host, port):
        self.host = host
        self.port = port
        # set of all connections
        self.connections = set()
        # dict of the client username mapped to session id
        self.client_username_to_session_id = dict()
        self.host_username_to_session_id = dict()
        self.active_hosts = set()
        self.client_data_host = defaultdict(dict)
        self.socket_id_to_socket = dict()
        self.retrieval_queue = dict()  # Host:filename -> client
        self.lru = queue.Queue()

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
            username = msg_obj["username"]
            self.client_username_to_session_id[username] = websocket.id
            if username not in self.client_data_host:
                self.client_data_host[username] = dict()
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
            self.host_username_to_session_id[msg_obj["username"]
                                             ] = websocket.id
            self.active_hosts.add(msg_obj["username"])
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

    async def redistribute_files(self, websocket, json_obj):
        username = find_key_by_value(
            self.host_username_to_session_id, websocket.id)[0]
        print(">> Redistributing File request from host: " + username)
        filenames = json_obj['filenames']
        if len(self.active_hosts) >= 2:
            for filename in filenames:
                print(">> Requesting body for file: " + filename)
                req = {
                    "requestType": "FreeFile",
                    "filename": filename
                }
                await websocket.send(json.dumps(req))
            print(">> Removing host from active hosts: " + username)
            self.active_hosts.remove(username)
            resp = {
                "requestType": "RedistributeFiles",
                "status": "Failure",
                "filename": ""
            }
            await websocket.send(json.dumps(resp))

    async def free_file(self, websocket, json_obj):
        filename = json_obj['filename']
        data = json_obj["body"]
        print(">> Freeing File: " + filename)
        if self.active_hosts:
            available_hosts = list(self.active_hosts)

            self.lru = remove_element(self.lru, find_key_by_value(
                self.host_username_to_session_id, websocket.id)[0])
            print(">> Queue before: ")
            print(list(self.lru.queue))
            available_host_username = get_choice(available_hosts, self.lru)
            print(">> Queue after: ")
            print(list(self.lru.queue))
            print(">> New Node: " + filename)
            available_host_id = self.host_username_to_session_id[available_host_username]
            print(">> Host available with username " +
                  available_host_username + " id " + available_host_id)
            available_host_socket = self.socket_id_to_socket[available_host_id]

            req = {
                "requestType": "SaveFile",
                "filename": filename,
                "body": data
            }

            print(">> Changing the client_file_host ds")
            old_username = find_key_by_value(
                self.host_username_to_session_id, websocket.id)[0]
            new_username = find_key_by_value(
                self.host_username_to_session_id, available_host_id)[0]
            for client in self.client_data_host:
                if filename in self.client_data_host[client]:
                    if self.client_data_host[client][filename] == old_username:
                        self.client_data_host[client][filename] = new_username
            print(">> " + str(self.client_data_host))
            await available_host_socket.send(json.dumps(req))

    async def send_file_to_host(self, websocket, msg_obj):
        print(">> Finding available host")
        if self.active_hosts:
            # every time a new saveFile request is made
            # I will check all hosts in my queue, and chose the
            #  one that is not present in the queue
            # if all are in queue, I will pop the top of the queue and insert it
            # backwards
            # available_host_username = next(
            #     iter(self.active_host_username_to_session_id))
            # available_host_id = self.active_host_username_to_session_id[available_host_username]
            available_hosts = list(self.active_hosts)
            print(">> Available Hosts")
            print(available_hosts)
            available_host_username = get_choice(available_hosts, self.lru)
            print(">> Available Host Username")
            print(available_host_username)
            available_host_id = self.host_username_to_session_id[available_host_username]
            print(">> Available Host ID")
            print(available_host_id)
            print(">> Host available with username " +
                  available_host_username + " id " + available_host_id)
            available_host_socket = self.socket_id_to_socket[available_host_id]
            # available =host socket is the socket of the host I will request a file from
            # Open the file in binary mode and read its contents
            filename = msg_obj["filename"]
            file_path = os.path.join(dir, filename)
            with open(file_path, "rb") as file:
                file_contents = file.read()
            print(">> Matching file found: " + filename)
            base64_str = base64.b64encode(file_contents).decode("utf-8")
            # Encode the file contents as a base64 string
            req = {
                "requestType": "SaveFile",
                "filename": filename,
                "body": base64_str
            }

            # delete file
            os.remove(file_path)
            print(">> Deleting file with path " +
                  file_path + " from server")

            self.client_data_host[msg_obj["username"]
                                  ][filename] = available_host_username
            print(">> Sending file with filename " + filename)

            await available_host_socket.send(json.dumps(req))
        else:
            print("ERROR: Host username registration failed!")
            # this is the client websocket the error will be sent to
            raise Exception("No available host")

    async def client_save_file(self, websocket, msg_obj):
        username = find_key_by_value(
            self.client_username_to_session_id, websocket.id)
        print(">> Client Save file initializing")
        if username:
            username = username[0]
            print(">> Matching username found ")
            print(username)
            filename = msg_obj["filename"]
            base64_str = msg_obj["body"]
            base64_bytes = base64.b64decode(base64_str)
            # write bytes to file
            file_path = os.path.join(dir, filename)
            if not os.path.exists(dir):
                os.makedirs(dir)
            with open(file_path, "wb") as f:
                f.write(base64_bytes)
            suc_msg = "File created with name: " + filename
            print(">> " + suc_msg)
            try:
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
            except Exception as e:
                # handle the exception here
                print("ERROR: " + str(e))
                resp = {
                    "status": "Failure",
                    "message": "No active hosts",
                    "requestType": "SaveFile"
                }
                # delete file
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(">> Delecting file with path " +
                          file_path + " from server")
                await websocket.send(json.dumps(resp))

        else:
            print("ERROR: Client not initialized properly")
            resp = {
                "status": "Failure",
                "message": "Client not initialized properly",
                "requestType": "SaveFile"
            }
            await websocket.send(json.dumps(resp))

    async def host_retrieve_file(self, websocket, username, msg_obj):
        filename = msg_obj["filename"]
        print(">> Data Retrieval started from host")
        client_data_dict = self.client_data_host[username]
        host_username = client_data_dict[filename]
        if host_username:
            host_id = self.host_username_to_session_id[host_username]
            host_socket = self.socket_id_to_socket[host_id]
            print(">> Host socket " + host_id + " has the data")
            if find_key_by_value(self.host_username_to_session_id, host_id):
                print(">> Required host is online")
                req = {
                    "requestType": "RetrieveFile",
                    "filename": filename
                }
                retrieval_key = host_id + ":" + filename
                self.retrieval_queue[retrieval_key] = websocket.id
                await host_socket.send(json.dumps(req))
            else:
                print("ERROR: Required host is offline")
                resp = {
                    "status": "Failure",
                    "message": "Required host is offline",
                    "requestType": "RetrieveFile"
                }
                await websocket.send(json.dumps(resp))
        else:
            print("ERROR: Invalid file provided, file assigned to no host")
            resp = {
                "status": "Failure",
                "message": "Invalid file",
                "requestType": "RetrieveFile"
            }
            await websocket.send(json.dumps(resp))

    async def file_host_to_client(self, websocket, msg_obj):
        print(">> Rcving file from host")
        filename = msg_obj["filename"]
        retrieval_key = websocket.id + ":" + filename
        client_socket_id = self.retrieval_queue[retrieval_key]
        client_socket = self.socket_id_to_socket[client_socket_id]
        if client_socket_id:
            print(">> Forwarding client found with id: " + client_socket_id)
            resp = {
                "requestType": "RetrieveFile",
                "status": "Success",
                "message": "",
                "filename": filename,
                "body": msg_obj["body"]
            }
            await client_socket.send(json.dumps(resp))
            print(">> Sending file to client" + client_socket_id)
        else:
            print("ERROR: No matching client found in retrieval queue")
            resp = {
                "requestType": "RetrieveFile",
                "status": "Failure",
                "message": "ERROR: No matching client found in retrieval queue"
            }
            await client_socket.send(json.dumps(resp))

    async def client_retrieve_file(self, websocket, msg_obj):
        username = find_key_by_value(
            self.client_username_to_session_id, websocket.id)
        print(">> Client Retrieve file initializing")
        if username:
            username = username[0]
            print(">> Matching username found: " + username)
            # Open the file in binary mode and read its contents
            print(">> Finding host ")
            await self.host_retrieve_file(websocket, username, msg_obj)
        else:
            print("ERROR: Client not initialized properly")
            resp = {
                "status": "Failure",
                "message": "Client not initialized properly",
                "requestType": "RetrieveFile"
            }
            await websocket.send(json.dumps(resp))

    async def fetch_all_files(self, websocket, json_obj):
        username = find_key_by_value(
            self.client_username_to_session_id, websocket.id)
        if username:
            username = username[0]
            print(">> Fetching files for client: " + username)
            list_of_files = list(self.client_data_host[username].keys())
            if list_of_files:
                resp = {
                    "requestType": "FetchAllFiles",
                    "message": {
                        "files": list_of_files
                    },
                    "status": "Success"
                }
                print(">> Files sent to client: " + username)
                await websocket.send(json.dumps(resp))
            else:
                resp = {
                    "requestType": "FetchAllFiles",
                    "message": "No files found",
                    "status": "Failure"
                }
                print("ERROR: No files found")
                await websocket.send(json.dumps(resp))
        else:
            resp = {
                "requestType": "FetchAllFiles",
                "message": "Client socket inactive",
                "status": "Failure"
            }
            print("ERROR: Client socket inactive")
            await websocket.send(json.dumps(resp))

    async def handle_disconnect(self, websocket):
        session_id = websocket.id

        self.connections.remove(session_id)

        client = find_key_by_value(
            self.client_username_to_session_id, session_id)
        host = find_key_by_value(
            self.host_username_to_session_id, session_id)
        if client:
            self.client_username_to_session_id[client[0]] = None
        if host:
            self.host_username_to_session_id[host[0]] = None
            self.active_hosts.remove(host[0])
            self.lru = remove_element(self.lru, host[0])

        if session_id in self.socket_id_to_socket:
            del self.socket_id_to_socket[session_id]

        print(self.client_data_host)
        print(f"{session_id} disconnected")

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

                elif request_type == "RetrieveFile":
                    if entity_type == "Client":
                        await self.client_retrieve_file(websocket, json_obj)
                    if entity_type == "Host":
                        await self.file_host_to_client(websocket, json_obj)

                elif request_type == "FetchAllFiles":
                    await self.fetch_all_files(websocket, json_obj)

                elif request_type == "RedistributeFiles":
                    await self.redistribute_files(websocket, json_obj)

                elif request_type == "FreeFile":
                    await self.free_file(websocket, json_obj)
                else:
                    # if you reach here the request is invalid
                    print("ERROR: Invalid request made")
                    resp = {
                        "status": "Failure",
                        "message": "Invalid Request type",
                        "requestType": "RetrieveFile"
                    }
                    await websocket.send(json.dumps(resp))
        except websockets.exceptions.ConnectionClosed:
            pass

        await self.handle_disconnect(websocket)

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
