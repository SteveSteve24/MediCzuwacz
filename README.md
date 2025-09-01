# MediCzuwacz

Easily track when your Medicover doctor has open appointments.

- Automatically logs in to your Medicover account
- Checks for new available visits with selected doctors, clinics, or specialties
- Sends instant notifications (Gotify, Telegram, and more)
- Simple to set up and automate using Docker

![MediCzuwacz](https://raw.githubusercontent.com/SteveSteve24/MediCzuwacz/refs/heads/main/mediczuwacz.png)
 
---

## Configuration (One-Time Setup)
1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
2. Fill in the `.env` file with your credentials.
3. Run the following command to build the Docker image:
    ```bash
    docker build --rm -t mediczuwacz .
    ```

---

## Usage

### Run with Parameters
#### Example 1: Search for an Appointment
For a pediatrician (`Pediatra`) in Warsaw:
```bash
docker run --rm --env-file=.env mediczuwacz find-appointment -r 204 -s 132 -f "2024-12-11"
```

#### Example 2: Search and Send Notifications
To search and send notifications via Gotify:
```bash
docker run --rm --env-file=.env mediczuwacz find-appointment -r 204 -s 132 -f "2024-12-11" -n gotify -t "Pediatra"
```

#### Example 3: Search for an Appointment in particular Clinic (Łukiska - 49284)
To search and send notifications via Gotify:
```bash
docker run --rm --env-file=.env mediczuwacz find-appointment -r 204 -s 132 -f "2024-12-11" -c 49284 -n gotify -t "Pediatra"
```

#### Example 4: Search for a Specific Doctor and set End date
Use `-d` param:
```bash
docker run --rm --env-file=.env mediczuwacz find-appointment -r 204 -s 132 -d 394 -f "2024-12-16" -e "2024-12-19"
```

#### Example 5: Search for a Dental Hygienist who speaks ukrainian
Use `-l` param:
```bash
docker run --rm --env-file=.env mediczuwacz find-appointment -r 204 -s 112 -l 60
```

#### Example 6: start once and check for new Appointments every 10 minutes
```bash
docker run --rm --env-file=.env mediczuwacz find-appointment -r 204 -s 112 -i 10
```

#### Example 7: Search for an examination / diagnostic procedure (USG jamy brzusznej - 521)
Use `--search-type` param to search for appointments for a diagnostic procedure:
```bash
docker run --rm --env-file=.env mediczuwacz find-appointment -r 204 -s 521 --search-type DiagnosticProcedure
```
Note that some examinations may be classified the same as regular doctor appointments (e.g. blood tests).

The known search types are (`0` is used when `--search-type` is not specified):

- `Standard` / `0` - consultations and dentistry
- `DiagnosticProcedure` / `2` - examinations

Search types have a numeric and text values. The current web UI uses the text values.
When trying to use the numeric values instead, the UI wrongfully shows the visits as paid even when they're included in your medical care package. This seems to be the only difference between numeric and text value - they appear to return the same appointments.

---

## How to Know IDs?
In commands, you use different IDs (e.g., `204` for Warsaw). How do you find other values?

Run the following commands:

- To list available regions:
  ```bash
  docker run --rm --env-file=.env mediczuwacz list-filters regions
  ```

- To list available specialties:
  ```bash
  docker run --rm --env-file=.env mediczuwacz list-filters specialties
  ```

- To list clinics for a specific region and specialty:
  ```bash
  docker run --rm --env-file=.env mediczuwacz list-filters clinics -r 204 -s 132
  ```

- To list doctors for a specific region and specialty:
  ```bash
  docker run --rm --env-file=.env mediczuwacz list-filters doctors -r 204 -s 132
  ```

---

## Telegram Notifications
Use the Telegram app to send notifications to your channel by following these steps:

### Step 1: Create a Telegram Bot
Follow this guide to create a Telegram Bot: [Create Telegram Bot](https://gist.github.com/nafiesl/4ad622f344cd1dc3bb1ecbe468ff9f8a).

### Step 2: Update `.env`
Add the following lines to your `.env` file:
```bash
NOTIFIERS_TELEGRAM_CHAT_ID=111222333
NOTIFIERS_TELEGRAM_TOKEN=mySecretToken
```

### Step 3: Run the Command
Run the following command to send Telegram notifications:
```bash
docker run --rm --env-file=.env mediczuwacz find-appointment -r 204 -s 132 -f "2024-12-11" -n telegram -t "Pediatra"
```

---

## Automating the Script with CRON
### Step 1: Create a Bash Script
Create a script named `run_mediczuwacz.sh`:
```bash
#!/bin/bash
cd /home/projects/
docker run --rm --env-file=.env mediczuwacz find-appointment -r 204 -s 132 -f "2024-12-11" -n gotify -t "Pediatra"
```
Make the script executable:
```bash
chmod +x run_mediczuwacz.sh
```

### Step 2: Configure CRON
Set up a CRON job to check appointments every 10 minutes:
1. Edit the crontab:
   ```bash
   crontab -e
   ```
2. Add the following line:
   ```bash
   */10 * * * * /home/projects/mediczuwacz/run_mediczuwacz.sh >> /home/projects/mediczuwacz/cron_log.txt 2>&1
   ```

---

## Cron-like Monitoring on Windows

Create a new file, e.g., `check_appointments_windows.bat`, to run the Docker command every 600 seconds (10 minutes). Example:

```batch
@echo off
:loop
docker run --rm --env-file=.env mediczuwacz find-appointment -r 204 -s 132
timeout 600
goto loop
```

### Running the Script
1. Open **Command Prompt** (cmd).
2. Run the script:
   ```cmd
   check_appointments_windows.bat
   ```

### Stopping the Script
Press `CTRL+C` in the Command Prompt and confirm by typing `y`.

---

## Run docker with interval

This command starts a container that checks for new appointments every 25 minutes. It will display either new appointment details or "No new appointments found."

Use the `-i` parameter to set the interval (in minutes):

```bash
docker run --rm --env-file=.env mediczuwacz find-appointment -r 204 -s 112 -i 25
```


---

## Local development

Leverage the `-v` Docker flag to mount local files, allowing you to modify the Python script without needing to rebuild the Docker container. You can make changes to the script, run it via Docker, and see the updates immediately!

Example: 

Windows
```
docker run --rm -v %cd%/mediczuwacz.py:/app/mediczuwacz.py --env-file=.env mediczuwacz find-appointment -r 204 -s 132
```

Linux
```
docker run --rm -v $(pwd)/mediczuwacz.py:/app/mediczuwacz.py --env-file=.env mediczuwacz find-appointment -r 204 -s 132
```

---

## Changelog

### v0.1 - 2024-12-11
- Repository initialized; created because the old Medihunter stopped working due to incompatibility with the new authentication system.

### v0.2 - 2024-12-13
- Added the `list-filters` command (by areqq).

### v0.3 - 2025-02-22
- Fixed {epoch_time} auth bug (thanks pogarek & Odnoklubov).

### v0.4 - 2025-03-07
- Added `interval` and `enddate` parameters, docker file optimization (by vitgorbunov).

### v0.5 - 2025-04-23
- Added `list-filters clinics` support.

---

## Acknowledgements
Special thanks to the following projects for their inspiration:
- [apqlzm/medihunter](https://github.com/apqlzm/medihunter)
- [atais/medibot](https://github.com/atais/medibot)


