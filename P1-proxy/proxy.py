#!/usr/bin/python3

import socket
import threading
import sys
import datetime
import re
import os
import uuid
import json

class ClientHandler(threading.Thread):
    RECEIVE_SIZE = 4096

    def __init__(self, _client_socket, log):
        threading.Thread.__init__(self)
        self._client_socket = _client_socket
        self._log = log

    def run(self):
        """Read the header from the client and forward it to the server"""
        data = self._client_socket.recv(self.RECEIVE_SIZE).decode('utf-8', 'ignore')
        lines = data.splitlines()
        is_firstline = True
        new_header = ''
        command = ''
        server_host = ''
        server_port = 80 # default port is 80
        for line in lines:
            if is_firstline:
                is_firstline = False
                # print the first line
                print(datetime.datetime.now().strftime('%d %b %X') + ' - >>> ' + str(line))
                l = line.split(' ')
                command = l[0].strip()
                # convert the http version into 1.0
                line = re.sub('[0-9][.][0-9]', '1.0', line, 1)
                if l[1].strip().lower().startswith('htpps://'):
                    server_port = 443
            elif line.startswith('Host:'):
                l = line.split(':')
                server_host = l[1].strip()
                if len(l) == 3:
                    server_port = int(l[2])
            if 'keep-alive' in line:
                line = line.replace('keep-alive', 'close')
            new_header += line + '\r\n'
        new_header += '\r\n'
        if command == 'CONNECT':
            self._connect_request(server_host, server_port, data)
            return
        self._nonconnect_request(server_host, server_port, data, new_header)


    def _connect_request(self, server_host, server_port, original_header):
        """Connect request"""
        # create a socket to interact with the server
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        response_bytes = ''
        try:
            s.connect((server_host, server_port))
            # if it succeeds, returns a succeed message to the client
            response_bytes = 'HTTP/1.0 200 OK\r\n\r\n'.encode('utf-8')
            self._client_socket.send(response_bytes)
            if self._log:
                self._logging(
                    server_host, 
                    original_header, 
                    None, 
                    response_bytes.decode('utf-8', 'ignore'),
                    True
                )
        except socket.error:
            # if it fails, returns a failure message to the client
            response_bytes = 'HTTP/1.0 502 Bad Gateway\r\n\r\n'.encode('utf-8')
            self._client_socket.send(response_bytes)
            if self._log:
                self._logging(
                    server_host, 
                    original_header, 
                    None, 
                    response_bytes.decode('utf-8', 'ignore'),
                    True
                )
            # since connection fails, close the socket and return immediately
            s.close()
            return
        self._client_socket.settimeout(0.5)
        s.settimeout(0.5)
        from_client = True
        while True:
            if from_client:
                try:
                    message_bytes = self._client_socket.recv(self.RECEIVE_SIZE)
                    s.send(message_bytes)
                except socket.timeout:
                    from_client = not from_client
                    continue
                except:
                    continue
                else:
                    if len(message_bytes) == 0:
                        self._client_socket.close()
                        s.close()
                        break
            else:
                try:
                    response_bytes = s.recv(self.RECEIVE_SIZE)
                    self._client_socket.send(response_bytes)
                except socket.timeout:
                    from_client = not from_client
                    continue
                except:
                    continue
                else:
                    if len(response_bytes) == 0: 
                        self._client_socket.close()
                        s.close()
                        break


    def _nonconnect_request(self, server_host, server_port, original_header, modified_header):
        """Non-connect request"""
        # create a socket to interact with the server
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((server_host, server_port))
        sock.sendall(modified_header.encode('utf-8'))
        # receive from the server and forward the message to the client
        response_bytes = sock.recv(self.RECEIVE_SIZE)
        if self._log:
            self._logging(
                server_host, 
                original_header, 
                modified_header, 
                response_bytes.decode('utf-8', 'ignore'),
                False
            )
        lines = response_bytes.decode('utf-8', 'ignore').splitlines()
        content_length = 0
        for line in lines:
            if line.startswith('Content-Length:'):
                l = line.split(' ')
                content_length = int(l[1])
        while content_length > 0:
            self._client_socket.send(response_bytes)
            response_bytes = sock.recv(self.RECEIVE_SIZE)
            content_length -= self.RECEIVE_SIZE
            if self._log:
                self._logging(
                    server_host, 
                    original_header, 
                    modified_header, 
                    response_bytes.decode('utf-8', 'ignore'),
                    False
                )
        if not response_bytes == None:
            self._client_socket.send(response_bytes)
        sock.close()

    def _logging(self, server_host, original_header, modified_header, response, connect):
        """Log messages from client/server on a newly created json file"""
        try:
            os.mkdir('./Log/' + server_host)
        except FileExistsError:
            pass
        file_name = server_host + str(uuid.uuid1()) + '.json'
        file_loc = './Log/' + server_host
        file_path = os.path.join(file_loc, file_name)
        if connect:
            json_data = {
                "Incoming header" : original_header, 
                "Proxy response sent" : response 
            }
        else:
            json_data = {
                "Incoming header" : original_header, 
                "Modified header" : modified_header,
                "Server response received" : response 
            }
        with open(file_path, 'w') as json_file:
            json.dump(json_data, json_file)


if __name__ == '__main__':
    log = False
    if len(sys.argv) == 3 and sys.argv[2] == 'Log':
        try:
            os.mkdir('Log')
        except FileExistsError:
            pass
        log = True
    connect_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connect_socket.bind(('0.0.0.0', int(sys.argv[1])))
    connect_socket.listen(100)
    while True:
        try:
            # get a new socket object for new client and get the client addr
            conn, addr = connect_socket.accept()
            client_handler = ClientHandler(conn, log)
            client_handler.daemon = True
            client_handler.start()
        except KeyboardInterrupt or EOFError:
            connect_socket.close()
            sys.exit()