import requests
import re
import random
import string
from socketIO_client import SocketIO, BaseNamespace
import time, rstr
from faker import Faker
from mongoengine import *


class PredecessorCredentials(Document):
    round = IntField()
    team = IntField()
    username = StringField()
    password = StringField()
    idd = IntField()
    flag = StringField()


class Config(object):
    flask_port = 5000
    sockets_port = 5001
    timeout = 4


def generate_flags(pattern):
    return [rstr.xeger(pattern) for a in range(1)]


class ChatNamespace(BaseNamespace):
    def on_connect(self):
        pass
        # print('connected!')

    def on_message_response(self, *args):
        pass
        # print('response', args)


class Checker:
    def __init__(self, q, round_number, team_number, config, flag):
        self.index = 0
        self.queue = q
        self.idd = -1
        self.password = None
        self.flag = flag[0]
        self.round = round_number
        self.team_number = team_number
        self.cfg = config
        self.integrity = 0

        old_creds = PredecessorCredentials.objects(team=self.team_number).order_by('-round').first()
        if old_creds:
            self.old_flag = old_creds.flag
            self.old_idd = old_creds.idd
            self.old_username = old_creds.username
            self.old_password = old_creds.password
        else:
            self.old_flag = ''
            self.old_idd = ''
            self.old_username = ''
            self.old_password = ''

        self.errors = []
        self.s = requests.Session()
        self.ip = config.IP_PATTERN.format(team_number=self.team_number)
        self.sockets_port = Config.sockets_port
        self.flask_port = Config.flask_port

        self.fake = Faker('ru_RU')
        self.fake.seed(time.time())

        self.username = self.fake.profile()['username']
        self.email = self.fake.email()

    def check(self):
        try:
            index = self.s.get('http://{}:{}/'.format(self.ip, self.flask_port), timeout=Config.timeout)
        except:
            self.errors.append('Host is down')
            self.put_status()
            return
        self.integrity += 5

        try:
            res = self.s.post('http://{}:{}/register'.format(self.ip, self.flask_port),
                              data={'email': self.email, 'login': self.username, 'about': self.flag},
                              timeout=Config.timeout)
        except:
            self.errors.append('Registration is unavailable')
            self.put_status()
            return
        self.integrity += 5

        try:
            self.password = re.findall(r'\<p class="flow-text center-align"\>(.+?)\</p\>', res.text)[0].strip()
            self.idd = re.findall(r'Уже зарегистрировано\: (\d+?) \</p\>', res.text)[0].strip()
        except Exception as e:
            self.errors.append("Can't reach my password or id")
            self.put_status()
        self.integrity += 10
        self.put_status()
        self.save_credentials()

        try:
            login = self.s.post('http://{}:{}/login'.format(self.ip, self.flask_port),
                                data={'login': self.username, 'pass': self.password}, timeout=Config.timeout)
            if 'Выйти' not in login.text:
                self.errors.append("Can't log in")
                self.put_status()
        except:
            self.errors.append("Can't log in")
            self.put_status()

        try:
            profile = self.s.get('http://{}:{}/user/{}'.format(self.ip, self.flask_port, self.idd),
                                 timeout=Config.timeout)
            if self.flag not in profile.text:
                self.errors.append('Flag is unavailable')
                self.put_status()
            else:
                self.integrity += 30
                self.put_status()
        except:
            self.errors.append('Flag is unavailable')
            self.put_status()

        possible = string.ascii_letters + string.digits + ' '
        msg = ''.join([random.choice(possible) for i in range(random.randint(10, 15))])
        # print('sending {} to chat'.format(msg))

        try:
            socketIO = SocketIO(self.ip, self.sockets_port)
            chat_namespace = socketIO.define(ChatNamespace, '/chat')
            data = dict(data=dict(message=msg, author=self.username))
            chat_namespace.emit('message', data)
            socketIO.wait_for_callbacks(seconds=1)
            chat = self.s.get('http://{}:{}/chat'.format(self.ip, self.flask_port), timeout=Config.timeout)
            if str(msg) not in chat.text:
                self.errors.append("Can't send messages to chat")
                self.put_status()
            else:
                self.integrity += 15
                self.put_status()
        except:
            self.errors.append("Can't send messages to chat")
            self.put_status()

        if round != 1:
            s = requests.Session()

            try:
                login = s.post('http://{}:{}/login'.format(self.ip, self.flask_port),
                               data={'login': self.old_username, 'pass': self.old_password},
                               timeout=Config.timeout)
                if 'Выйти' not in login.text:
                    self.errors.append("Previous account is unavailable")
                    self.put_status()
                old_profile = s.get('http://{}:{}/user/{}'.format(self.ip, self.flask_port, self.old_idd),
                                    timeout=Config.timeout)
                if self.old_flag not in old_profile.text:
                    self.errors.append('Previous flag is unavailable')
                    self.put_status()
                else:
                    self.errors.append("Checked")
                    self.integrity += 35
                    self.put_status()
            except:
                self.errors.append('Previous flag is unavailable')
                self.put_status()
        else:
            self.errors.append("Checked")
            self.integrity += 35
            self.put_status()

    def save_credentials(self):
        creds = PredecessorCredentials(round=self.round, team=self.team_number,
                                       username=self.username, password=self.password,
                                       idd=self.idd, flag=self.flag)
        creds.save()

    def put_status(self):
        self.index += 1
        self.queue.put(
            dict(index=self.index, service="PredecessorChecker.py", team=self.team_number, status=self.integrity,
                 message=self.errors))
