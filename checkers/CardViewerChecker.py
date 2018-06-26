import requests
import random
import string
import re, time, rstr
from mongoengine import *
from faker import Faker


def generate_flags(pattern):
    return [rstr.xeger(pattern) for a in range(1)]


class Config(object):
    port = 80
    timeout = 5


class CardViewerCredentials(Document):
    round = IntField()
    team = IntField()
    login = StringField()
    password = StringField()
    description = StringField()
    flag = StringField()
    idd = IntField()


class Checker:
    def __init__(self, q, round_number, team_number, config, flag):
        self.index = 0
        self.idd = 0
        self.flag = flag[0]
        self.queue = q
        self.round = round_number
        self.team_number = team_number
        self.cfg = config
        self.completeness = 0

        old_creds = CardViewerCredentials.objects(team=self.team_number).order_by('-round').first()
        if old_creds:
            self.old_flag = old_creds.flag
            self.old_uid = old_creds.idd
            self.old_login = old_creds.login
            self.old_password = old_creds.password
        else:
            self.old_flag = ''
            self.old_uid = -1
            self.old_login = ''
            self.old_password = ''

        self.errors = []
        self.s = requests.Session()
        self.ip = config.IP_PATTERN.format(team_number=self.team_number)
        self.service_port = Config.port
        self.can_put = True


        fake = Faker()
        fake.seed(time.time())

        self.username1 = fake.profile()['username']
        self.password1 = fake.password()
        self.description1 = fake.sentence()

        self.username2 = fake.profile()['username']
        self.password2 = fake.password()
        self.description2 = fake.sentence()

    def check(self):
        if self.check_index():
            self.register()
            self.save_creds()
            self.auth()
            self.change_info()
            self.check_old_flag()
            if self.can_put:
                self.put()

    def check_index(self):
        try:
            index = self.s.get('http://{}:{}/'.format(self.ip, self.service_port), timeout=Config.timeout)
        except:
            self.errors.append('Host is down')
            self.put_status()
            self.can_put = False
            return False
        self.completeness += 10
        self.put_status()
        return True

    def register(self):
        try:
            res = self.s.post('http://{}:{}/register'.format(self.ip, self.service_port),
                         data={'RegisterForm[login]': self.username1, 'RegisterForm[password]': self.password1,
                               'RegisterForm[password_repeat]': self.password1,
                               'RegisterForm[selfdescription]': self.description1}, timeout=Config.timeout)
            if res.status_code != requests.codes.ok:
                raise Exception
            elif 'Аккаунт {}'.format(self.username1) not in res.text:
                self.can_put = False
                raise Exception

            s2 = requests.Session()
            res = s2.post('http://{}:{}/register'.format(self.ip, self.service_port),
                          data={'RegisterForm[login]': self.username2, 'RegisterForm[password]': self.password2,
                                'RegisterForm[password_repeat]': self.password2,
                                'RegisterForm[selfdescription]': self.description2}, timeout=Config.timeout)
            if res.status_code != requests.codes.ok:
                raise Exception
            elif 'Аккаунт {}'.format(self.username2) not in res.text:
                self.can_put = False
                raise Exception

            else:
                try:
                    self.idd = re.findall(r'a href\=\"\/user\/(\d+?)"\> Профиль', res.text)[0]
                except:
                    self.can_put = False
        except:
            self.errors.append('Registration is unavailable')
            self.put_status()
            return
        self.completeness += 20
        self.put_status()

    def auth(self):
        try:
            s = requests.Session()
            res = s.post('http://{}:{}/login'.format(self.ip, self.service_port),
                         data={'LoginForm[login]': self.username1, 'LoginForm[password]': self.password1}, timeout=Config.timeout)
            if self.username1 not in res.text:
                raise Exception
        except:
            self.errors.append('Login is unavailable')
            self.put_status()
            self.can_put = False
            return
        self.completeness += 10
        self.put_status()

    def change_info(self):
        try:
            acc = self.s.get('http://{}:{}/you/account'.format(self.ip, self.service_port), timeout=Config.timeout)

            possible = string.ascii_letters + string.digits + ' '

            msg = ''.join([random.choice(possible) for i in range(random.randint(10, 15))])

            changed = self.s.post('http://{}:{}/you/account'.format(self.ip, self.service_port),
                             data={'AccountForm[login]': self.username1, 'AccountForm[selfdescription]': msg}, timeout=Config.timeout)

            if msg not in changed.text:
                raise Exception
        except:
            self.errors.append('Account update is unavailable')
            self.put_status()
            return
        else:
            self.completeness += 10
            self.put_status()

    def check_old_flag(self):
        if self.old_flag:
            try:
                old_sess = requests.Session()

                try:
                    res = old_sess.post('http://{}:{}/login'.format(self.ip, self.service_port),
                                        data={'LoginForm[login]': self.old_login, 'LoginForm[password]': self.old_password},
                                        timeout=Config.timeout)
                    if self.old_login not in res.text:
                        raise Exception
                except Exception as e:
                    self.errors.append('Old login is unavailable')
                    self.put_status()

                userprofile = old_sess.get('http://{}:{}/user/{}'.format(self.ip, self.service_port, self.old_uid), timeout=Config.timeout)

                if self.old_flag not in userprofile.text:
                    raise Exception
                else:
                    self.completeness += 25
                    self.put_status()
            except:
                self.errors.append('Old flag is unavailable')
                self.put_status()
                return
        else:
            self.completeness += 25
            self.put_status()

    def put(self):
        try:
            added = self.s.post('http://{}:{}/user/{}'.format(self.ip, self.service_port, self.idd), data={'NotesForm[text]': self.flag}, timeout=Config.timeout)
            if self.flag in added.text:
                self.errors.append("Checked")
                self.completeness += 25
                self.put_status()
            else:
                raise Exception
        except:
            self.errors.append("Can't add a new flag")
            self.put_status()
            return

    def save_creds(self):
        creds = CardViewerCredentials(round=self.round, team=self.team_number,
                                      login=self.username1, password=self.password1,
                                      description=self.description1, flag=self.flag, idd=self.idd)
        creds.save()

    def put_status(self):
        self.index += 1
        self.queue.put(dict(index=self.index, team=self.team_number, service="CardViewerChecker.py", status=self.completeness, message=self.errors))
