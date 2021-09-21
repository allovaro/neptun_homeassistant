import socket


class NeptunTcp:
    def __init__(self, _ip):
        self.ip = _ip
        self.port = 6350
        self.data = None
        self.valves = 'off'
        self.dry_flag = 'off'
        self.alarm = 'off'
        self.counter_1 = 0
        self.counter_2 = 0
        self.counter_3 = 0
        self.counter_4 = 0
        self.sensor_1 = 'off'
        self.sensor_2 = 'off'
        self.sensor_3 = 'off'
        self.sensor_4 = 'off'

    def get_state(self):
        """
        Send single buffer `payload` and receive a single buffer.
        """
        online = False
        payload = bytes.fromhex('0254515200002a45')

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.settimeout(3)
        try:
            s.connect((self.ip, self.port))
            s.send(payload)
            self.data = s.recv(100)
            s.close()
            online = True
        except socket.gaierror:
            s.close()
            online = False
        except socket.error:
            s.close()
            online = False
        return online

    def set_state(self, _valves, _dry):
        """
        Send command to open/close valves and change dry mode
        """
        command = None
        if _dry:
            command = '025451570007530004010100037b35'
        elif _valves:
            command = '025451570007530004010000034c05'
        elif not _valves:
            command = '025451570007530004000000033ab1'
        elif not _dry:
            command = '025451570007530004000000033ab1'
        else:
            command = '025451570007530004000000033ab1'

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.settimeout(3)
        try:
            s.connect((self.ip, self.port))
            payload = bytes.fromhex(command)
            s.send(payload)
            data = s.recv(8)
            s.close()
        except socket.gaierror:
            s.close()
        except socket.error:
            s.close()

        if bytes.hex(data) == '025441000000014с':
            return True
        return False

    def is_exist(self):
        return True

    def parse_state(self, state):
        if state == '01':
            return 'on'
        else:
            return 'off'

    def get_sensor_state(self, num):
        """
        Encode leak sensors state from buffer
        """
        return self.parse_state(bytes.hex(self.data[53 + num:54 + num]))

    def get_valve_state(self):
        """
        Encode water valves state from buffer
        """
        return self.parse_state(bytes.hex(self.data[41:42]))

    def get_dry_flag_state(self):
        """
        Encode dry mode state from buffer
        """
        return self.parse_state(bytes.hex(self.data[44:45]))

    def get_alarm_state(self):
        """
        Encode alarm state from buffer
        """
        if bytes.hex(self.data[47:48]) != '00':
            return 'on'
        else:
            return 'off'

    def get_counter_value(self, num=1):
        """
        Get desired counter number value from buffer
        """
        start = 61 + (num - 1) * 5
        end = 65 + (num - 1) * 5
        val = bytes.hex(self.data[start:end])
        val = int(val, 16)

        if self.data[65 + (num - 1) * 5] != 0:
            return float(val) / (1000 / self.data[65 + (num - 1) * 5])
        else:
            return float(val)

    def parse_data(self):
        #  Fill sensors
        return dict([('sensor_1', self.get_sensor_state(1)),
                     ('sensor_2', self.get_sensor_state(2)),
                     ('sensor_3', self.get_sensor_state(3)),
                     ('sensor_4', self.get_sensor_state(4)),
                     ('valves', self.get_valve_state()),
                     ('dry', self.get_dry_flag_state()),
                     ('alarm', self.get_alarm_state()),
                     ('counter_1', self.get_counter_value(1)),
                     ('counter_2', self.get_counter_value(2)),
                     ('counter_3', self.get_counter_value(3)),
                     ('counter_4', self.get_counter_value(4)),
                     ])

    def update_data(self):
        """
        Update neptun data
        """
        self.get_state()
        self.parse_data()
        return True
