#!/usr/bin/python3

import argparse
import base64
import datetime
import hashlib
import http.cookiejar
import os
import random
import string
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fake_useragent import UserAgent
from rich import print
from rich.console import Console

from medihunter_notifiers import gotify_notify, pushbullet_notify, pushover_notify, telegram_notify, xmpp_notify

console = Console()

# Load environment variables
load_dotenv()


COOKIE_DIR = Path("/data")


class Authenticator:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.cookie_file = COOKIE_DIR / f"{username}_cookies"
        self.session = requests.Session()
        self.load_cookies()
        self.headers = {
            "User-Agent": UserAgent().random,
            "Accept": "application/json",
            "Authorization": None
        }
        self.tokenA = None

    def load_cookies(self):
        jar = http.cookiejar.MozillaCookieJar(str(self.cookie_file))
        if self.cookie_file.exists():
            try:
                jar.load(ignore_discard=True, ignore_expires=True)
                console.print(f"[dim]Loaded {len(jar)} cookies for MEDICOVER_USER[/dim]")
            except Exception as e:
                console.print(f"[yellow]Warning: could not load cookies: {e}[/yellow]")
        self.session.cookies = jar

    def save_cookies(self):
        try:
            self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
            self.session.cookies.save(ignore_discard=True, ignore_expires=True)
            console.print(f"[dim]Saved cookies for MEDICOVER_USER[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning: could not save cookies: {e}[/yellow]")

    def get_device_id(self):
        device_file = self.cookie_file.with_suffix(".device_id")
        if device_file.exists():
            return device_file.read_text().strip()
        device_id = str(uuid.uuid4())
        device_file.parent.mkdir(parents=True, exist_ok=True)
        device_file.write_text(device_id)
        console.print(f"[dim]Generated new device_id: {device_id}[/dim]")
        return device_id

    def generate_code_challenge(self, input):
        sha256 = hashlib.sha256(input.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(sha256).decode("utf-8").rstrip("=")

    def exchange_code(self, login_url, redirect_uri, code, code_verifier):
        token_data = {
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
            "code_verifier": code_verifier,
            "client_id": "web",
        }
        response = self.session.post(f"{login_url}/connect/token", data=token_data, headers=self.headers)
        tokens = response.json()
        self.tokenA = tokens["access_token"]
        self.headers["Authorization"] = f"Bearer {self.tokenA}"
        self.save_cookies()

    def handle_mfa(self, response, mfa_url, login_url, auth_params):
        soup = BeautifulSoup(response.content, "html.parser")
        # Check for errors on the MFA page before proceeding
        error_div = soup.find("div", class_="alert-error")
        if error_div:
            error_msg = error_div.get_text(strip=True)
            console.print(f"[bold red]MFA error: {error_msg}[/bold red]")
            raise ValueError(f"MFA error: {error_msg}")

        # Collect all hidden fields (CSRF token, return URL, etc.)
        form = soup.find("form")
        if not form:
            console.print(f"[bold red]MFA page has no form.[/bold red]\n{response.text[:1000]}")
            raise ValueError("Could not find MFA form on the page")

        form_action = form.get("action", "")
        post_url = f"{login_url}{form_action}" if form_action.startswith("/") else (form_action or mfa_url)

        form_data = {}
        for hidden in form.find_all("input", {"type": "hidden"}):
            name = hidden.get("name")
            if name:
                form_data[name] = hidden.get("value", "")

        # Prompt for 2FA code
        console.print(f"[bold yellow]2FA code required (channel: {form_data.get('Input.Channel', 'unknown')})[/bold yellow]")
        code = input("Enter your 2FA code: ").strip()
        if not code:
            raise ValueError("No 2FA code provided")

        # Set the combined code into the hidden field and mark device as trusted
        form_data["Input.MfaCode"] = code
        form_data["Input.IsTrustedDevice"] = "true"
        form_data["Input.DeviceName"] = "Chrome"
        form_data["Input.Button"] = "confirm"

        response = self.session.post(post_url, data=form_data, headers=self.headers, allow_redirects=False)

        if response.status_code not in {301, 302, 303, 307, 308}:
            # Dump the response page to understand the error
            error_soup = BeautifulSoup(response.content, "html.parser")
            errors = error_soup.find_all(class_=lambda c: c and ("error" in c.lower() or "validation" in c.lower() or "alert" in c.lower())) if error_soup else []
            console.print(f"[bold red]MFA verification failed ({response.status_code})[/bold red]")
            for e in errors:
                console.print(f"[red]{e.get_text(strip=True)}[/red]")
            raise ValueError(f"MFA verification failed with status {response.status_code}")

        console.print("[green]2FA verified successfully[/green]")
        return response.headers.get("Location")

    def login(self):
        state = "".join(random.choices(string.ascii_lowercase + string.digits, k=32))
        device_id = self.get_device_id()
        code_verifier = "".join(uuid.uuid4().hex for _ in range(3))
        code_challenge = self.generate_code_challenge(code_verifier)
        epoch_time = int(time.time()) * 1000

        login_url = "https://login-online24.medicover.pl"
        oidc_redirect = "https://online24.medicover.pl/signin-oidc"
        auth_params = (
            f"?client_id=web&redirect_uri={oidc_redirect}&response_type=code"
            f"&scope=openid+offline_access+profile&state={state}&code_challenge={code_challenge}"
            f"&code_challenge_method=S256&response_mode=query&ui_locales=pl&app_version=3.4.0-beta.1.0"
            f"&previous_app_version=3.4.0-beta.1.0&device_id={device_id}&device_name=Chrome&ts={epoch_time}"
        )

        # Step 1: Initialize login
        response = self.session.get(f"{login_url}/connect/authorize{auth_params}", headers=self.headers, allow_redirects=False)
        next_url = response.headers.get("Location")

        # Check if step 1 already returned an auth code (session still valid via cookies)
        if next_url and "code=" in next_url:
            console.print("[green]Already authenticated via saved session[/green]")
            code = parse_qs(urlparse(next_url).query)["code"][0]
            self.exchange_code(login_url, oidc_redirect, code, code_verifier)
            return

        # Step 2: Extract CSRF token
        response = self.session.get(next_url, headers=self.headers, allow_redirects=False)
        soup = BeautifulSoup(response.content, "html.parser")
        csrf_input = soup.find("input", {"name": "__RequestVerificationToken"})
        if csrf_input:
            csrf_token = csrf_input.get("value")
        else:
            raise ValueError("CSRF token not found in the login page.")

        # Step 3: Submit login form
        login_data = {
            "Input.ReturnUrl": f"/connect/authorize/callback{auth_params}",
            "Input.LoginType": "FullLogin",
            "Input.Username": self.username,
            "Input.Password": self.password,
            "Input.Button": "login",
            "__RequestVerificationToken": csrf_token,
        }
        response = self.session.post(next_url, data=login_data, headers=self.headers, allow_redirects=False)
        next_url = response.headers.get("Location")
        # Step 3.5: Handle MFA
        if next_url and "/Mfa" in next_url:
            mfa_url = f"{login_url}{next_url}" if next_url.startswith("/") else next_url
            response = self.session.get(mfa_url, headers=self.headers, allow_redirects=False)

            # If the server already trusts this device, it redirects immediately
            if response.status_code in {301, 302, 303, 307, 308}:
                console.print("[green]Device is trusted — MFA skipped[/green]")
                next_url = response.headers.get("Location")
            else:
                next_url = self.handle_mfa(response, mfa_url, login_url, auth_params)

        # Step 4: Fetch authorization code
        step4_url = f"{login_url}{next_url}" if next_url and next_url.startswith("/") else next_url
        response = self.session.get(step4_url, headers=self.headers, allow_redirects=False)
        next_url = response.headers.get("Location")
        code = parse_qs(urlparse(next_url).query)["code"][0]

        # Step 5: Exchange code for tokens
        self.exchange_code(login_url, oidc_redirect, code, code_verifier)


class AppointmentFinder:
    def __init__(self, session, headers):
        self.session = session
        self.headers = headers

    def http_get(self, url, params):
        response = self.session.get(url, headers=self.headers, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            console.print(
                f"[bold red]Error {response.status_code}[/bold red]: {response.text}"
            )
            return {}

    def find_appointments(self, search_type, region, specialty, clinic, start_date, end_date, language, doctor=None):
        today = datetime.date.today()
        if start_date < today:
            start_date = today
        appointment_url = "https://api-gateway-online24.medicover.pl/appointments/api/search-appointments/slots"
        params = {
            "RegionIds": region,
            "SpecialtyIds": specialty,
            "ClinicIds": clinic,
            "Page": 1,
            "PageSize": 5000,
            "StartTime": start_date.isoformat(),
            "SlotSearchType": search_type,
            "VisitType": "Center",
        }

        if language:
            params["DoctorLanguageIds"] = language

        if doctor:
            params["DoctorIds"] = doctor

        response = self.http_get(appointment_url, params)

        items = response.get("items", [])

        if end_date:
            items = [x for x in items if datetime.datetime.fromisoformat(x["appointmentDate"]).date() <= end_date]

        return items

    def find_filters(self, region=None, specialty=None):
        filters_url = "https://api-gateway-online24.medicover.pl/appointments/api/search-appointments/filters"

        params = {"SlotSearchType": 0}
        if region:
            params["RegionIds"] = region
        if specialty:
            params["SpecialtyIds"] = specialty

        response = self.http_get(filters_url, params)
        return response


class Notifier:
    @staticmethod
    def format_appointments(appointments):
        """Format appointments into a human-readable string."""
        if not appointments:
            return "No appointments found."

        messages = []
        for appointment in appointments:
            date = appointment.get("appointmentDate", "N/A")
            clinic = appointment.get("clinic", {}).get("name", "N/A")
            doctor = appointment.get("doctor", {}).get("name", "N/A")
            specialty = appointment.get("specialty", {}).get("name", "N/A")
            doctor_languages = appointment.get("doctorLanguages", [])
            languages = ", ".join([lang.get("name", "N/A") for lang in doctor_languages]) if doctor_languages else "N/A"
            message = (
                    f"Date: {date}\n"
                    f"Clinic: {clinic}\n"
                    f"Doctor: {doctor}\n"
                    f"Languages: {languages}\n" +
                    f"Specialty: {specialty}\n" + "-" * 50
            )
            messages.append(message)
        return "\n".join(messages)

    @staticmethod
    def send_notification(appointments, notifier, title):
        """Send a notification with formatted appointments."""
        message = Notifier.format_appointments(appointments)
        if notifier == "pushbullet":
            pushbullet_notify(message, title)
        elif notifier == "pushover":
            pushover_notify(message, title)
        elif notifier == "telegram":
            telegram_notify(message, title)
        elif notifier == "xmpp":
            xmpp_notify(message)
        elif notifier == "gotify":
            gotify_notify(message, title)


def display_appointments(appointments):
    console.print()
    console.print("-" * 50)
    if not appointments:
        console.print("No new appointments found.")
    else:
        console.print("New appointments found:")
        console.print("-" * 50)
        for appointment in appointments:
            date = appointment.get("appointmentDate", "N/A")
            clinic = appointment.get("clinic", {}).get("name", "N/A")
            doctor = appointment.get("doctor", {}).get("name", "N/A")
            specialty = appointment.get("specialty", {}).get("name", "N/A")
            doctor_languages = appointment.get("doctorLanguages", [])
            languages = ", ".join([lang.get("name", "N/A") for lang in doctor_languages]) if doctor_languages else "N/A"
            console.print(f"Date: {date}")
            console.print(f"  Clinic: {clinic}")
            console.print(f"  Doctor: {doctor}")
            console.print(f"  Specialty: {specialty}")
            console.print(f"  Languages: {languages}")
            console.print("-" * 50)


def main():
    parser = argparse.ArgumentParser(description="Find appointment slots.")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Command to execute")

    find_appointment = subparsers.add_parser("find-appointment", help="Find appointment")
    find_appointment.add_argument("--search-type", required=False, default="0", type=str, help="Search type")
    find_appointment.add_argument("-r", "--region", required=True, type=int, help="Region ID")
    find_appointment.add_argument("-s", "--specialty", required=True, type=int, action="extend", nargs="+", help="Specialty ID",)
    find_appointment.add_argument("-c", "--clinic", required=False, type=int, help="Clinic ID")
    find_appointment.add_argument("-d", "--doctor", required=False, type=int, help="Doctor ID")
    find_appointment.add_argument("-f", "--date", type=datetime.date.fromisoformat, default=datetime.date.today(), help="Start date in YYYY-MM-DD format")
    find_appointment.add_argument("-e", "--enddate", type=datetime.date.fromisoformat, help="End date in YYYY-MM-DD format")
    find_appointment.add_argument("-n", "--notification", required=False, help="Notification method")
    find_appointment.add_argument("-t", "--title", required=False, help="Notification title")
    find_appointment.add_argument("-l", "--language", required=False, type=int, help="4=Polski, 6=Angielski, 60=Ukraiński")
    find_appointment.add_argument("-i", "--interval", required=False, type=int, help="Repeat interval in minutes")

    list_filters = subparsers.add_parser("list-filters", help="List filters")
    list_filters_subparsers = list_filters.add_subparsers(dest="filter_type", required=True, help="Type of filter to list")

    regions = list_filters_subparsers.add_parser("regions", help="List available regions")
    specialties = list_filters_subparsers.add_parser("specialties", help="List available specialties")
    doctors = list_filters_subparsers.add_parser("doctors", help="List available doctors")
    doctors.add_argument("-r", "--region", required=True, type=int, help="Region ID")
    doctors.add_argument("-s", "--specialty", required=True, type=int, help="Specialty ID")
    clinics = list_filters_subparsers.add_parser("clinics", help="List available clinics")
    clinics.add_argument("-r", "--region", required=True, type=int, help="Region ID")
    clinics.add_argument("-s", "--specialty", required=True, type=int, nargs="+", help="Specialty ID(s)")

    args = parser.parse_args()

    username = os.environ.get("MEDICOVER_USER")
    password = os.environ.get("MEDICOVER_PASS")

    if not username or not password:
        console.print("[bold red]Error:[/bold red] MEDICOVER_USER and MEDICOVER_PASS environment variables must be set.")
        exit(1)

    previous_appointments = []

    while True:
        # Authenticate
        auth = Authenticator(username, password)
        auth.login()

        finder = AppointmentFinder(auth.session, auth.headers)

        if args.command == "find-appointment":
            # Find appointments
            appointments = finder.find_appointments(args.search_type, args.region, args.specialty, args.clinic, args.date, args.enddate, args.language, args.doctor)

            # Find new appointments
            if previous_appointments:
                new_appointments = [x for x in appointments if x not in previous_appointments]
            else:
                new_appointments = appointments

            previous_appointments = appointments

            # Display appointments
            display_appointments(new_appointments)

            # Send notification if appointments are found
            if new_appointments:
                Notifier.send_notification(new_appointments, args.notification, args.title)

            if args.interval:
                # Sleep and repeat
                time.sleep(args.interval * 60)
                continue

        elif args.command == "list-filters":

            if args.filter_type in ("doctors", "clinics"):
                filters = finder.find_filters(args.region, args.specialty)
            else:
                filters = finder.find_filters()

            for r in filters[args.filter_type]:
                print(f"{r['id']} - {r['value']}")

        break


if __name__ == "__main__":
    main()
