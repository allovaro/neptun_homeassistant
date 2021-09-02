import socket

HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 6350        # Port to listen on (non-privileged ports are > 1023)

valve = '00'
dry = '00'

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen()
    while True:
        conn, addr = s.accept()
        with conn:
            print('Connected by', addr)
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                print(len(bytes.hex(data)))
                if len(bytes.hex(data)) == 16:
                    data = bytes.fromhex(f'02544152005c4900054e333232304d001136303a43353a41383a37353a35313a333541000100530007{valve}0000{dry}0003017300004c000400000100430014000084c60a00001c760a0000000000000000000044000a3136303538313637313657000104f0e1')
                else:
                    if bytes.hex(data) == '025451570007530004010000034c05':
                        valve = '01'
                    elif bytes.hex(data) == '025451570007530004010100037b35':
                        valve = '01'
                        dry = '01'
                    elif bytes.hex(data) == '025451570007530004000000033ab1':
                        valve = '00'
                        dry = '00'

                    data = bytes.fromhex('025441000000014c')
                conn.sendall(data)
            print('Connection closed')
        print('Socket closed')

