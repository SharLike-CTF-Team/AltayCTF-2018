import requests
import json
import random, time
import rstr
from faker import Faker
from mongoengine import *


class JobSearchCredentials(Document):
    team = IntField()
    round = IntField()
    employer_email = StringField()
    employer_password = StringField()
    applicant_email = StringField()
    applicant_password = StringField()
    resume_flag = StringField()
    vacancy_flag = StringField()


def generate_flags(pattern):
    return [rstr.xeger(pattern) for a in range(2)]


class Config(object):
    api_port = 3000
    client_port = 8088
    timeout = 6


class Checker:
    def __init__(self, q, round_number, team_number, config, flags):
        self.index = 0
        self.queue = q
        self.round = round_number
        self.team = team_number
        self.cfg = config
        self.integrity = 0

        self.api_port = Config.api_port
        self.client_port = Config.client_port

        self.resume_flag = flags[0]
        self.vacancy_flag = flags[1]

        old_creds = JobSearchCredentials.objects(team=self.team).order_by('-round').first()
        if old_creds:
            self.old_em_email = old_creds.employer_email
            self.old_em_password = old_creds.employer_password
            self.old_app_email = old_creds.applicant_email
            self.old_app_pass = old_creds.applicant_password
            self.old_vac_flag = old_creds.vacancy_flag
            self.old_res_flag = old_creds.resume_flag
        else:
            self.old_em_email = ''
            self.old_em_password = ''
            self.old_app_email = ''
            self.old_app_pass = ''
            self.old_vac_flag = ''
            self.old_res_flag = ''

        self.errors = []
        self.ip = config.IP_PATTERN.format(team_number=self.team)

        self.fake = Faker('ru_RU')
        self.fake.seed(time.time())

        self.em_email = self.fake.email()
        self.em_pass = self.fake.password()
        self.app_email = self.fake.email()
        self.app_pass = self.fake.password()

        self.save_credentials()

    def check(self):
        self.integrity += self.is_client_available()

        api_integrity = self.is_api_available()
        if api_integrity > 0:
            self.put_status()
            self.integrity += api_integrity
            signup_integrity, credentials = self.check_signup('employer')

            if signup_integrity > 0:
                self.integrity += signup_integrity
                self.put_status()
                signin_integrity, token = self.check_signin(credentials)

                if signin_integrity > 0:
                    self.integrity += signin_integrity
                    self.put_status()
                    self.integrity += self.check_vacancy_creation(token)

            signup_integrity, credentials = self.check_signup('applicant')
            if signup_integrity > 0:
                self.integrity += signup_integrity
                self.put_status()
                signin_integrity, token = self.check_signin(credentials)

                if signin_integrity > 0:
                    self.integrity += signin_integrity
                    self.put_status()
                    self.integrity += self.check_resume_creation(token)

            employer_credentials = {
                'email': self.old_em_email,
                'password': self.old_em_password
            }

            signin_integrity, token = self.check_signin(employer_credentials)
            if signin_integrity > 0:
                self.integrity += signin_integrity
                self.put_status()
                self.integrity += self.check_old_vacancy_flag(token)

            applicant_credentials = {
                'email': self.old_app_email,
                'password': self.old_app_pass
            }

            signin_integrity, token = self.check_signin(applicant_credentials)
            if signin_integrity > 0:
                self.integrity += signin_integrity
                self.put_status()
                self.integrity += self.check_old_resume_flag(token)
                self.errors.append("Checked")
                self.put_status()

    def is_api_available(self):
        try:
            with requests.get('http://{}:{}/api/signup'.format(self.ip, self.api_port),
                              timeout=Config.timeout) as response:
                if response.status_code == 404:
                    return 15
                else:
                    self.errors.append("Api unavailable")
                    self.put_status()
                    return 0
        except:
            self.errors.append("Api unavailable")
            self.put_status()
            return 0

    def is_client_available(self):
        try:
            with requests.get('http://{}:{}'.format(self.ip, self.client_port), timeout=Config.timeout) as response:
                if response.status_code == 200:
                    return 15
                else:
                    self.errors.append("Client unavailable")
                    self.put_status()
                    return 0
        except:
            self.errors.append("Client unavailable")
            self.put_status()
            return 0

    def check_signup(self, user_type):
        try:
            if user_type == 'employer':
                credentials = {
                    'email': self.em_email,
                    'password': self.em_pass,
                }
            else:
                credentials = {
                    'email': self.app_email,
                    'password': self.app_pass,
                }
            headers = {
                'Content-type': 'application/json'
            }
            data = {
                'user': {
                    'email': credentials.get('email'),
                    'password': credentials.get('password'),
                    'type': user_type,
                    'name': self.fake.profile()['username'],
                    'phone': self.fake.phone_number()
                }
            }

            with requests.put('http://{}:{}/api/signup'.format(self.ip, self.api_port), data=json.dumps(data),
                              headers=headers, timeout=Config.timeout) as response:
                result = json.loads(response.text)
                if result.get('success'):
                    return 5, credentials
                else:
                    self.errors.append("Can't sign up as employer")
                    self.put_status()
                    return 0, False

        except Exception as err:
            print(err)
            self.errors.append("Can't sign up as employer")
            self.put_status()
            return 0, False

    def check_signin(self, credentials):
        headers = {
            'Content-type': 'application/json'
        }
        data = {
            'user': {
                'email': credentials.get('email'),
                'password': credentials.get('password')
            }
        }
        with requests.post('http://{}:{}/api/signin'.format(self.ip, self.api_port), data=json.dumps(data),
                           headers=headers, timeout=Config.timeout) as response:
            result = json.loads(response.text)
            if result.get('success'):
                if 'token' in result.get('user').keys():
                    return 5, result.get('user').get('token')
                else:
                    self.errors.append("Can't find auth token")
                    self.put_status()
                    return 0, False
            else:
                self.errors.append("Failed to login")
                self.put_status()
                return 0, False

    def check_resume_creation(self, token):
        headers = {
            'Content-type': 'application/json',
            'Authorization': 'Token {}'.format(token)
        }
        data = {
            'position': self.fake.job(),
            'salary': random.randint(1000, 3000),
            'experience': self.resume_flag,
            'skills': self.fake.job(),
            'education': self.fake.company(),
            'about_me': self.fake.sentence(),
            'access': 'premium'
        }

        with requests.put('http://{}:{}/api/resumes/create'.format(self.ip, self.api_port), data=json.dumps(data),
                          headers=headers, timeout=Config.timeout) as response:
            result = json.loads(response.text)
            if result.get('success'):
                return 10
            else:
                self.errors.append("Failed to create resume")
                self.put_status()
                return 0

    def check_vacancy_creation(self, token):
        headers = {
            'Content-type': 'application/json',
            'Authorization': 'Token {}'.format(token)
        }
        data = {
            'title': 'Senior CTFer',
            'description': self.vacancy_flag,
            'skills': self.fake.job(),
            'archived': True
        }

        with requests.put('http://{}:{}/api/vacancies/create'.format(self.ip, self.api_port), data=json.dumps(data),
                          headers=headers, timeout=Config.timeout) as response:
            result = json.loads(response.text)
            if result.get('success'):
                return 10
            else:
                self.errors.append("Failed to create vacancy")
                self.put_status()
                return 0

    def check_old_resume_flag(self, token):
        headers = {
            'Content-type': 'application/json',
            'Authorization': 'Token {}'.format(token)
        }
        with requests.get('http://{}:{}/api/resumes/list/my'.format(self.ip, self.api_port),
                          headers=headers, timeout=Config.timeout) as response:
            result = json.loads(response.text)
            if result.get('success'):
                resumes = result.get('data')
                for resume in resumes:
                    if self.old_res_flag == resume.get('experience'):
                        return 10
                self.errors.append("Cannot find old flag")
                self.put_status()
                return 0
            else:
                self.errors.append("Failed to find any resumes")
                self.put_status()
                return 0

    def check_old_vacancy_flag(self, token):
        headers = {
            'Content-type': 'application/json',
            'Authorization': 'Token {}'.format(token)
        }
        with requests.get('http://{}:{}/api/vacancies/list/my'.format(self.ip, self.api_port),
                          headers=headers, timeout=Config.timeout) as response:
            result = json.loads(response.text)
            if result.get('success'):
                vacancies = result.get('data')
                for vacancy in vacancies:
                    if self.old_vac_flag == vacancy.get('description'):
                        return 10
                self.errors.append("Cannot find old flag")
                self.put_status()
                return 0
            else:
                self.errors.append("Failed to find any vacancies")
                self.put_status()
                return 0

    def save_credentials(self):
        creds = JobSearchCredentials(round=self.round, team=self.team,
                                     employer_email=self.em_email, employer_password=self.em_pass,
                                     applicant_email=self.app_email, applicant_password=self.app_pass,
                                     resume_flag=self.resume_flag, vacancy_flag=self.vacancy_flag)
        creds.save()

    def put_status(self):
        self.index += 1
        self.queue.put(dict(index=self.index, service="JobSearchChecker.py",
                            team=self.team, status=self.integrity, message=self.errors))
