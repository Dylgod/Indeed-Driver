"""
This is a script to automate Indeed. This script is a part of a larger automation framework
and not meant for public use. I am not responsible for any misuse of this script.
This is strictly a showcase piece.

What it does/has:
- Signs in to Indeed and stores cookies
- Searches for jobs relevant to given profile
- Applies for jobs using built-in Question-Answer bank
- Self trains unknown questions using Supabase API
- Built-in captcha detection and solving (recaptcha V3, V2, hcaptcha, CF Turnstile)
- Requires Google Chrome and downloads it if unavailable
- Downloads and/or updates chromedriver when needed
- local db logging system for easy debugging
"""

from seleniumbase import Driver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException
from selenium.common.exceptions import ElementNotInteractableException
from selenium.common.exceptions import NoSuchWindowException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import Select
from urllib.request import urlretrieve
from urllib.error import ContentTooShortError
from tkinter import *
import secrets
import random
import uuid as cap_uuid
import requests
import tempfile
import subprocess
import platform
# from pydub import AudioSegment # <- Enable after ffmpeg update
import time
import json
import re
import os, sys
import datetime
import argparse
import psutil
from psutil import NoSuchProcess, AccessDenied
import sqlite3
from supabase import create_client, Client
from twocaptcha import TwoCaptcha

# Prevent duplicate scripts
dupe_check = []
for proc in psutil.process_iter():
    if 'shy_drivers' in proc.name():
        dupe_check.append(proc.name())

if len(dupe_check)>2:
    sys.exit()

# True for PROD, False for TEST
WE_ARE_SUBMITTING = False

# final print statement -> gets changed throughout and prints this if no error occurs
finalprint = "Finished! Check your email"

# For Logging
logslist = []

# dont touch this
supa_retry_VAR = 0

class OSType(object):
    LINUX = "linux"
    MAC = "mac"
    WIN = "win"

class ChromeType(object):
    GOOGLE = "google-chrome"
    MSEDGE = "edge"

# These are for various questions and the edge case that there are profile sections missing,
# they will be made with these dates.
todaysdate = datetime.datetime.now().strftime("%m/%d/%Y")
todaysmonth = datetime.datetime.now().strftime("%B")
todaysyear = datetime.datetime.now().strftime("%Y")
lastyear = int(todaysyear) - 1
fouryearsago = int(todaysyear) - 4
eightyearsago = int(todaysyear) - 8

if WE_ARE_SUBMITTING:
    parser = argparse.ArgumentParser(prog='automate_linkedin.py', description="Enter id of profile w/ path to db")
    parser.add_argument('--uuid', type=str, help='Supabase uuid', required=True)
    parser.add_argument('--id', type=int, help='SQLlite id', required=True)
    parser.add_argument('--path', type=str, help='Path to database', required=True)
    parser.add_argument('--jobs', type=int, help='Number of jobs', required=False, default=15)

    args = parser.parse_args()
    uuid = args.uuid

def os_name():
    if "linux" in sys.platform:
        return OSType.LINUX
    elif "darwin" in sys.platform:
        return OSType.MAC
    elif "win32" in sys.platform:
        return OSType.WIN
    else:
        raise Exception("Could not determine the OS type!")

# Change current working directory for proper storage of local db on MacOS
if os_name() == 'mac':
    os.chdir(os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'shy-apply'))

def send_question_post(answer_type=None, question_text=None, platform=None):
    """
    Sends never before seen question to supabase log.
    answer_type: str, (radio, checkbox, ...)
    platform: str, (Indeed, Linkedin, ...)
    """
    if answer_type is None:
        a_type = 'Unknown'
    else:
        a_type = answer_type
    if question_text == '' or question_text == " " or question_text is None:
        question = 'None'
    else:
        question = question_text
    if platform is None:
        plat = 'Unknown'
    else:
        plat = platform

    questiondict = {'questions' : []}
    questiondict['questions'].append({"type":a_type, "question":question, "platform":plat})

    try:
        package = json.dumps(questiondict)
    except Exception:
        raise Exception

    try:
        x = requests.post(url='https://www.shyapply.com/api/questions', data=package, headers={"Content-Type": "application/json"})
        if x.status_code != 200:
            raise Exception
    except Exception:
        raise Exception

def errlog(severity=1, location=None, element="no_element", description=None, log=None):
    """
    Builds SQL query for db. Logs are collected and written in finally block at cleanup time.
    """
    global logslist
    try:
        location = web.current_url
    except Exception:
        location = None
    error_log = "INSERT INTO logs (log_date, log_severity, log_location, log_action, log_description, log_notes) VALUES ('{}', {}, '{}', '{}', '{}', '{}')".format(str(int(time.time())), severity, location, element, type(description).__name__, log)
    logslist.append(error_log)

def log_then_exit():
    """
    Writes current collection of logs to db in the event of a critical error.
    """
    if len(logslist) != 0:
        try:
            if WE_ARE_SUBMITTING:
                db = sqlite3.connect(r'{}'.format(args.path))
            else:
                db = sqlite3.connect(os.path.join(profile_dict['shy_dir'], 'shyapply.db'))
            db.row_factory = sqlite3.Row
            db_cursor = db.cursor()
            for log in logslist:
                db_cursor.execute(log)
                db.commit()
            db.close()
        except Exception:
            pass

    sys.exit()

def frontend_top_msg(String):

    if WE_ARE_SUBMITTING:
        try:
            db = sqlite3.connect(r'{}'.format(args.path))
        except Exception:
            try:
                db = sqlite3.connect(os.path.join(profile_dict['shy_dir'], 'shyapply.db'))
            except Exception:
                return

        update_top_msg = f'UPDATE messages SET mes_top = "{str(String)}" WHERE mes_id = 1'
        db.row_factory = sqlite3.Row
        db_cursor = db.cursor()
        db_cursor.execute(update_top_msg)
        db.commit()
        db.close()
    else:
        print(String)

def frontend_bot_msg(String):

    if WE_ARE_SUBMITTING:
        try:
            db = sqlite3.connect(r'{}'.format(args.path))
        except Exception:
            try:
                db = sqlite3.connect(os.path.join(profile_dict['shy_dir'], 'shyapply.db'))
            except Exception:
                return

        update_bot_msg = f'UPDATE messages SET mes_bottom = "{str(String)}" WHERE mes_id = 1'
        db.row_factory = sqlite3.Row
        db_cursor = db.cursor()
        db_cursor.execute(update_bot_msg)
        db.commit()
        db.close()
    else:
        print(String)

def application_success_log(jobtext):
    try:
        if len(jobtext) > 30:
            truncated_text = jobtext[:30] + "..."
            errlog(severity=0,element="SUCCESS",log=str(truncated_text))
        else:
            errlog(severity=0,element="SUCCESS",log=str(jobtext))
    except Exception:
        errlog(severity=0,element="SUCCESS",log="Application submitted")

def bot_typer(WebElement, string):
    """
    Types the string into the given WebElement if possible.
    Does not type if the WebElement's value matches the string.
    Clears the value before entering if the value does not equal the string.

    Types char by char at varying speeds at avg 65 wpm.
    """
    try:
        if WebElement.get_attribute('value') == string:
            pass
        else:
            WebElement.send_keys(Keys.BACKSPACE)

            if os_name() == 'mac':
                WebElement.send_keys(Keys.COMMAND + "a")
            elif os_name() == 'win':
                WebElement.send_keys(Keys.CONTROL + "a")

            WebElement.send_keys(Keys.DELETE)
            for char in str(string):
                WebElement.send_keys(char)
                delay = secrets.randbelow(1)
                delay2 = random.uniform(0.05, 0.25)
                time.sleep(delay + delay2)
    except Exception:
        WebElement.send_keys(Keys.BACKSPACE)

        if os_name() == 'mac':
            WebElement.send_keys(Keys.COMMAND + "a")
        elif os_name() == 'win':
            WebElement.send_keys(Keys.CONTROL + "a")

        WebElement.send_keys(Keys.DELETE)
        for char in str(string):
            WebElement.send_keys(char)
            delay = secrets.randbelow(1)
            delay2 = random.uniform(0.05, 0.25)
            time.sleep(delay + delay2)

def isnumbersonly(number: str | int):
    """
    Does not account for numbers represented by letters.
    example: qqqqqq returns true.
    """
    acceptable_numbers = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
    if str(number) == "":
      return False
    else:
      for digit in str(number):
         if digit in acceptable_numbers:
            continue
         else:
            return False

    return True

def confirm_window_handle(web):

    if web.current_window_handle == anchor_handle:
        errlog(element='anchor_handle', description='anchor_handle', log='driver was on wrong tab')
        tabs = web.window_handles
        for o in tabs:
            web.switch_to.window(o)
            if web.current_window_handle != anchor_handle:
                break
    else:
        return

def resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath("..")

    return os.path.join(base_path, relative_path)

def supa_retry(ping):
    """
    In the event of an outage, tries to reconnect every 3 minutes.
    timeout = 5 tries
    """
    global supa_retry_VAR
    global tokens
    global finalprint

    if ping == "ping":
        try:
            response = supabase.table('subs').select('tokens').eq("id", uuid).execute()
            response_dict = response.model_dump()
            tokens = response_dict['data'][0]['tokens']
            supa_retry_VAR = 0
            if tokens <= 0:
                finalprint = "Not enough tokens!"
                frontend_top_msg("Shy Apply stopped.")
                frontend_bot_msg("Not enough tokens!")
                try:
                    sys.exit()
                except Exception:
                    try:
                        web.quit()
                    except Exception:
                        pass
        except Exception:
            supa_retry_VAR += 1
            if supa_retry_VAR < 5:
                barrens_chat(String='Could not connect to Shy Apply servers. Retrying in 3 minutes', seconds=180)
                supa_retry("ping")
            else:
                finalprint = "Could not connect to Shy Apply"
                frontend_top_msg("Shy Apply stopped.")
                frontend_bot_msg("Could not connect to Shy Apply")
                error_log = "INSERT INTO logs (log_date, log_severity, log_location, log_action, log_description, log_notes) VALUES ({}, 1, supa_retry(ping), 'response', 'no description' ,supa_retry_VAR = 5)".format(str(int(time.time())))
                logslist.append(error_log)
                try:
                    log_then_exit()
                except Exception:
                    try:
                        web.quit()
                    except Exception:
                        pass

    if ping == "update":
        # updates tokens
        try:
            tokens_minus_one = tokens - 1
        except NameError:
            supa_retry("ping")
            tokens_minus_one = tokens - 1
        try:
            supabase.table('subs').update({'tokens': tokens_minus_one}).eq("id", uuid).execute()
            supa_retry_VAR = 0
        except Exception:
            supa_retry_VAR += 1
            if supa_retry_VAR < 5:
                barrens_chat(String='Could not connect to Shy Apply servers. Retrying in 3 minutes', seconds=180)
                supa_retry("update")
            else:
                finalprint = "Could not connect to Shy Apply"
                frontend_top_msg("Shy Apply stopped.")
                frontend_bot_msg("Could not connect to Shy Apply")
                error_log = "INSERT INTO logs (log_date, log_severity, log_location, log_action, log_description, log_notes) VALUES ({}, 1, supa_retry(update), 'response', 'no description' ,supa_retry_VAR = 5)".format(str(int(time.time())))
                logslist.append(error_log)
                try:
                    log_then_exit()
                except Exception:
                    try:
                        web.quit()
                    except Exception:
                        pass

    if ping != "ping" and ping != "update":
        finalprint = "update token error"
        frontend_top_msg("Shy Apply stopped.")
        frontend_bot_msg("update token error")
        try:
            sys.exit()
        except Exception:
            try:
                web.quit()
            except Exception:
                pass

def cf_manual_solver(web, error=None) -> None:
    """
    Attempts to find cloudflare challenge iframe and clicks the checkbox if found.
    """
    captcha_frame_regex = re.compile(r'cf-chl-widget-.{3,6}')
    try:
        # Usually it's item with index 0
        matching_elements = web.find_elements(By.XPATH, "//*[contains(@id, 'cf-chl-widget-')]")
        # print(f'Matches found: {matching_elements}')
        for element in matching_elements:
            element_id = element.get_attribute("id")
            if captcha_frame_regex.match(element_id) and 'Cloudflare security challenge' in element.accessible_name:
                # print(f"Matched Element ID: {element_id} - {element.accessible_name}")
                cf_captcha_frame = element
                break

        try:
            # Switch to captcha iframe
            WebDriverWait(web, 15.0).until(EC.frame_to_be_available_and_switch_to_it(cf_captcha_frame))
            captcha_checkbox = web.find_element(By.CLASS_NAME, 'ctp-checkbox-label')
            captcha_checkbox.uc_click()
            # Back to default content
            web.switch_to.default_content()
            time.sleep(1)
        except Exception as err:
            if error is not None:
                raise NoSuchElementException
    except Exception as e:
        errlog(element="captcha_frame_regex", description=e)
        if error is not None:
            raise NoSuchElementException

def captcha_checkbox_and_solve(web, error=None):
    """
    Clicks reCAPTCHA V3 chkbox and if detected, solves it using 2captcha service.
    """
    try:
        recaptcha_iframe = web.find_element(By.XPATH, '//iframe[contains(@title, "reCAPTCHA")]')
        web.switch_to.frame(recaptcha_iframe)
    except Exception as e:
        errlog(element='recaptcha_iframe', description=e, log="Possibly no captcha present.")
        if error is not None:
            raise NoSuchElementException
        else:
            return

    try:
        checkbox = web.find_element(By.ID, "recaptcha-anchor")
        checkbox.uc_click()
        time.sleep(2)
    except Exception as e:
        errlog(element='checkbox', description=e)

    try:
        ischecked = WebDriverWait(web, 5).until(EC.presence_of_element_located((By.XPATH, "//*[contains(@class, 'checkbox-checked')]")))
        web.switch_to.default_content()
        return
    except Exception:
        pass

    web.switch_to.default_content()

    try:
        recaptchaV3_iframe = web.find_element(By.XPATH, '//iframe[contains(@title, "recaptcha challenge")]')
        web.switch_to.frame(recaptchaV3_iframe)
    except Exception as e:
        errlog(element='recaptchaV3_iframe', description=e)
        if error is not None:
            raise NoSuchElementException
        else:
            return

    if error is not None:
        solve_audio_capcha(web, error='error')
    else:
        solve_audio_capcha(web)

    try:
        web.find_element(By.XPATH, '//div[normalize-space()="Multiple correct solutions required - please solve more."]')
        solve_audio_capcha(web)
    except Exception:
        pass

    web.switch_to.default_content()

def clean_temp(temp_files):
    """
    Used with solve_audio_capcha to clean temporary files involving downloaded mp3 files.
    """
    for path in temp_files:
        if os.path.exists(path):
            os.remove(path)

def solve_audio_capcha(web, error=None) -> None:
    """
    Called if reCAPTCHA V3 is detected.
    Downloads audio challenge and solves with 2captcha service.
    """

    try:
        # Geberate capcha downlaod -> the headset btn
        headset_captcha_btn = web.find_element(By.XPATH, '//*[@id="recaptcha-audio-button"]')
        headset_captcha_btn.uc_click()
        time.sleep(1.5)
    except Exception as e:
        errlog(element="headset_captcha_btn",description=e)
        if error is not None:
            raise NoSuchElementException
        else:
            return

    try:
        # Locate audio challenge download link
        download_link = web.find_element(By.CLASS_NAME, 'rc-audiochallenge-tdownload-link')
    except Exception as e:
        errlog(element="download_link", description=e, log="Failed to download audio file")
        if error is not None:
            raise NoSuchElementException
        else:
            return

    # Create temporary directory and temporary files
    tmp_dir = tempfile.gettempdir()

    id_ = cap_uuid.uuid4().hex

    mp3_file, wav_file = os.path.join(tmp_dir, f'{id_}_tmp.mp3'), os.path.join(tmp_dir, f'{id_}_tmp.wav')

    tmp_files = {mp3_file, wav_file}

    with open(mp3_file, 'wb') as f:
        link = download_link.get_attribute('href')
        audio_download = requests.get(url=link, allow_redirects=True)
        f.write(audio_download.content)
        f.close()

    # DELETE THIS AFTER FFMPEG INTEGRATION!
    if os.path.exists(wav_file):
        clean_temp(tmp_files)
        errlog(element="solve_audio_capcha", log="captcha given in wav format. update ffmpeg!")
        return

    # DOES NOT WORK UNTIL FFMPEG INTEGRATION --UPDATE
    # Convert WAV to MP3 format for compatibility with speech recognizer APIs
    # if os.path.exists(wav_file):
    #     try:
    #         AudioSegment.from_wav(wav_file).export(mp3_file, format='mp3')
    #     except Exception as e:
    #         errlog(element="AudioSegment", description=e, log="Failed to convert wav into mp3")
    #         clean_temp(tmp_files)
    #         if error is not None:
    #             raise NoSuchElementException
    #         else:
    #             return

    # Use 2Captcha's sudio service to get text from file
    try:
        solver = TwoCaptcha('4db1a5f4e11e2ba041312b7cf6f07310')
        result = solver.audio(mp3_file, lang = 'en')
    except Exception as e:
        # invalid parameters passed
        errlog(element="result", description=e, log="Failed to solve audio")
        clean_temp(tmp_files)
        if error is not None:
            raise NoSuchElementException
        else:
            return

    # Clean up all temporary files
    clean_temp(tmp_files)

    # Write transcribed text to iframe's input box
    try:
        response_textbox = web.find_element(By.ID, 'audio-response')
        bot_typer(response_textbox, str(result['code']))
        time.sleep(1.448)
        try:
            verify_btn1 = web.find_element(By.ID, 'recaptcha-verify-button')
            verify_btn1.uc_click()
        except Exception:
            try:
                verify_btn2 = web.find_element(By.XPATH, '//button[contains(text(), "Verify")]')
                verify_btn2.uc_click()
            except Exception as error:
                errlog(element="verify_btn2", description=error, log="No Verify Btn")
    except Exception as e:
        errlog(element="response_textbox", description=e, log="captcha failed")

def captcha_still_there_check(web, timeoutVAR):
    """
    Verifies the existence of a captcha after solve attempt.
    """
    bot_typer_str = '"' + profile_dict['job_title'] + '"'

    if timeoutVAR < 3:
        try:
            still_there = web.find_elements(By.XPATH, '//*[contains(text(), "Verify you are human")]')
            if len(still_there) >= 1:
                errlog(log="captcha detected in whatwhere")
                try:
                    cf_manual_solver(web, error='error')
                except Exception:
                    captcha_checkbox_and_solve(web)
            else:
                return
        except Exception:
            return

        retryVAR = timeoutVAR + 1
        captcha_still_there_check(web, retryVAR)

    elif timeoutVAR == 3:
        beforeURL = web.current_url
        if bot_typer_str in beforeURL:
            newURL = str(beforeURL).replace(bot_typer_str, profile_dict['job_title'])
            web.get(newURL)
        else:
            errlog(log="could not bypass captcha in whatwhere")

def get_dependencies():
    """
    Checks if Google Chrome is installed and if not, attempts to silently install.
    Completely silent on windows and prompts the user for creds on MacOS.
    """

    PATTERN = {
        ChromeType.GOOGLE: r"\d+\.\d+\.\d+",
        ChromeType.MSEDGE: r"\d+\.\d+\.\d+",
    }

    def os_architecture():
        if platform.machine().endswith("64"):
            return 64
        else:
            return 32

    def os_type():
        return "%s%s" % (os_name(), os_architecture())

    def linux_browser_apps_to_cmd(*apps):
        """Create 'browser --version' command from browser app names."""
        ignore_errors_cmd_part = " 2>/dev/null" if os.getenv(
            "WDM_LOG_LEVEL") == "0" else ""
        return " || ".join(
            "%s --version%s" % (i, ignore_errors_cmd_part) for i in apps
        )

    def windows_browser_apps_to_cmd(*apps):
        """Create analogue of browser --version command for windows."""
        powershell = determine_powershell()
        first_hit_template = "$tmp = {expression}; if ($tmp) {{echo $tmp; Exit;}};"
        script = "$ErrorActionPreference='silentlycontinue'; " + " ".join(
            first_hit_template.format(expression=e) for e in apps
        )
        return '%s -NoProfile "%s"' % (powershell, script)

    def get_latest_chrome():
        global finalprint

        if os_name() == 'win':
            if os.path.exists(profile_dict['shy_dir']):
                download_link = r"https://dl.google.com/chrome/install/latest/chrome_installer.exe"

                dl_destination = os.path.join(profile_dict['shy_dir'], 'chrome_installer.exe')

                install_chrome = f""" {dl_destination} /silent /install"""

                try:
                    frontend_top_msg("Setting up...")
                    frontend_bot_msg('Installing dependencies - 5 percent')
                    get_chrome = urlretrieve(download_link, dl_destination)
                    frontend_bot_msg('Installing dependencies - 15 percent')
                except ContentTooShortError as e:
                    finalprint = "Error - Please install Google Chrome."
                    frontend_top_msg("Dependencies not found")
                    frontend_bot_msg("Error - Please install Google Chrome.")
                    errlog(element='get_chrome', description=e, log='Download interupted.')
                    log_then_exit()
                except Exception as e:
                    finalprint = "Error - Please install Google Chrome."
                    frontend_top_msg("Dependencies not found")
                    frontend_bot_msg("Error - Please install Google Chrome.")
                    errlog(element='get_chrome', description=e, log='Tried to download google chrome but couldnt')
                    log_then_exit()

                if os.path.exists(dl_destination):
                    frontend_bot_msg('Installing dependencies - 30 percent')
                    try:
                        subprocess.run(["powershell","& {" + install_chrome + "}"])
                        frontend_bot_msg('Installing dependencies - 45 percent')
                        percentage_count = 49
                        try:
                            fail_stack = 1
                            while fail_stack < 12:
                                time.sleep(5)
                                if get_browser_version_from_os("google-chrome") is None:
                                    frontend_bot_msg(f'Installing dependencies - {str(percentage_count)} percent')
                                    fail_stack += 1
                                    percentage_count += 5
                                else:
                                    frontend_top_msg("Booting up Shy Apply")
                                    frontend_bot_msg("Dependencies found! Starting...")
                                    break

                                if fail_stack == 12:
                                    errlog(element='fail_stack', log='fail_stack = 5. Download Failed')
                                    finalprint = "Error - Please install Google Chrome."
                                    frontend_top_msg("Dependencies not found")
                                    frontend_bot_msg("Error - Please install Google Chrome.")
                                    log_then_exit()

                        except Exception as e:
                            errlog(element='fail_stack', description=e, log='Failure in while loop')

                    except Exception as e:
                        errlog(element='install_chrome', description=e, log='Tried to install google chrome but couldnt')
                        finalprint = "Error - Please install Google Chrome."
                        frontend_top_msg("Dependencies not found")
                        frontend_bot_msg("Error - Please install Google Chrome.")
                        log_then_exit()

                    try:
                        os.unlink(dl_destination)
                    except PermissionError:
                        errlog(element='dl_destination', description=e, log='could not uninstall due to PermissionError')
                    except FileNotFoundError:
                        pass
                    except Exception as e:
                        errlog(element='install_chrome', description=e, log='could not uninstall due to unknown error')

        elif os_name() == 'mac':
            frontend_top_msg("Missing Dependencies")
            frontend_bot_msg("Need Google Chrome")
            log_then_exit()

    def get_browser_version_from_os(browser_type):
        """Return installed browser version."""
        cmd_mapping = {
            ChromeType.GOOGLE: {
                OSType.LINUX: linux_browser_apps_to_cmd(
                    "google-chrome",
                    "google-chrome-stable",
                    "chrome",
                    "chromium",
                    "chromium-browser",
                    "google-chrome-beta",
                    "google-chrome-dev",
                    "google-chrome-unstable",
                ),
                OSType.MAC: r"/Applications/Google\ Chrome.app"
                            r"/Contents/MacOS/Google\ Chrome --version",
                OSType.WIN: windows_browser_apps_to_cmd(
                    r'(Get-Item -Path "$env:PROGRAMFILES\Google\Chrome'
                    r'\Application\chrome.exe").VersionInfo.FileVersion',
                    r'(Get-Item -Path "$env:PROGRAMFILES (x86)\Google\Chrome'
                    r'\Application\chrome.exe").VersionInfo.FileVersion',
                    r'(Get-Item -Path "$env:LOCALAPPDATA\Google\Chrome'
                    r'\Application\chrome.exe").VersionInfo.FileVersion',
                    r'(Get-ItemProperty -Path Registry::"HKCU\SOFTWARE'
                    r'\Google\Chrome\BLBeacon").version',
                    r'(Get-ItemProperty -Path Registry::"HKLM\SOFTWARE'
                    r'\Wow6432Node\Microsoft\Windows'
                    r'\CurrentVersion\Uninstall\Google Chrome").version',
                ),
            },
            ChromeType.MSEDGE: {
                OSType.LINUX: linux_browser_apps_to_cmd(
                    "microsoft-edge",
                    "microsoft-edge-stable",
                    "microsoft-edge-beta",
                    "microsoft-edge-dev",
                ),
                OSType.MAC: r"/Applications/Microsoft\ Edge.app"
                            r"/Contents/MacOS/Microsoft\ Edge --version",
                OSType.WIN: windows_browser_apps_to_cmd(
                    # stable edge
                    r'(Get-Item -Path "$env:PROGRAMFILES\Microsoft\Edge'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-Item -Path "$env:PROGRAMFILES (x86)\Microsoft'
                    r'\Edge\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-ItemProperty -Path Registry::"HKCU\SOFTWARE'
                    r'\Microsoft\Edge\BLBeacon").version',
                    r'(Get-ItemProperty -Path Registry::"HKLM\SOFTWARE'
                    r'\Microsoft\EdgeUpdate\Clients'
                    r'\{56EB18F8-8008-4CBD-B6D2-8C97FE7E9062}").pv',
                    # beta edge
                    r'(Get-Item -Path "$env:LOCALAPPDATA\Microsoft\Edge Beta'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-Item -Path "$env:PROGRAMFILES\Microsoft\Edge Beta'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-Item -Path "$env:PROGRAMFILES (x86)\Microsoft\Edge Beta'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-ItemProperty -Path Registry::"HKCU\SOFTWARE\Microsoft'
                    r'\Edge Beta\BLBeacon").version',
                    # dev edge
                    r'(Get-Item -Path "$env:LOCALAPPDATA\Microsoft\Edge Dev'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-Item -Path "$env:PROGRAMFILES\Microsoft\Edge Dev'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-Item -Path "$env:PROGRAMFILES (x86)\Microsoft\Edge Dev'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-ItemProperty -Path Registry::"HKCU\SOFTWARE\Microsoft'
                    r'\Edge Dev\BLBeacon").version',
                    # canary edge
                    r'(Get-Item -Path "$env:LOCALAPPDATA\Microsoft\Edge SxS'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-ItemProperty -Path Registry::"HKCU\SOFTWARE'
                    r'\Microsoft\Edge SxS\BLBeacon").version',
                    # highest edge
                    r"(Get-Item (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft"
                    r"\Windows\CurrentVersion\App Paths\msedge.exe')."
                    r"'(Default)').VersionInfo.ProductVersion",
                    r"[System.Diagnostics.FileVersionInfo]::GetVersionInfo(("
                    r"Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows"
                    r"\CurrentVersion\App Paths\msedge.exe')."
                    r"'(Default)').ProductVersion",
                    r"Get-AppxPackage -Name *MicrosoftEdge.* | Foreach Version",
                    r'(Get-ItemProperty -Path Registry::"HKLM\SOFTWARE\Wow6432Node'
                    r'\Microsoft\Windows\CurrentVersion\Uninstall'
                    r'\Microsoft Edge").version',
                ),
            },
        }
        try:
            cmd_mapping = cmd_mapping[browser_type][os_name()]
            pattern = PATTERN[browser_type]
            quad_pattern = r"\d+\.\d+\.\d+\.\d+"
            quad_version = read_version_from_cmd(cmd_mapping, quad_pattern)
            if quad_version and len(str(quad_version)) >= 9:  # Eg. 115.0.0.0
                return quad_version
            version = read_version_from_cmd(cmd_mapping, pattern)
            return version
        except Exception:
            # get_latest_chrome()
            pass

    def read_version_from_cmd(cmd, pattern):
        with subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                shell=True,
        ) as stream:
            stdout = stream.communicate()[0].decode()
            version = re.search(pattern, stdout)
            version = version.group(0) if version else None
        return version

    def determine_powershell():
        """Returns "True" if runs in Powershell and "False" if another console."""
        cmd = "(dir 2>&1 *`|echo CMD);&<# rem #>echo powershell"
        with subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                shell=True,
        ) as stream:
            stdout = stream.communicate()[0].decode()
        return "" if stdout == "powershell" else "powershell"

    def set_shell_env_WINDOWS(str ,path): # Key: SHYAPPLY_FFMPEG
        ffmpeg_set_env = os.getenv(str)
        if ffmpeg_set_env is None:
            os.environ[str] = path
            print(os.environ.get(str))

    def set_zshell_env_MACOS(path): # Key: SHYAPPLY_FFMPEG
        set_env_PATH = """
        (echo; echo 'eval "$({0})"') >> {1}/.zprofile
        eval "$({0})"
        """.format(path,os.path.expanduser("~"))

        with open(os.path.join(os.path.expanduser("~"),".zprofile")) as file:
            f = file.read()
            if path not in f:
                subprocess.run(set_env_PATH, shell=True)


    try:
        if get_browser_version_from_os("google-chrome") is None:
            get_latest_chrome()
        else:
            frontend_top_msg("Booting up Shy Apply")
            frontend_bot_msg("Dependencies found! Starting...")
    except Exception as e:
        frontend_top_msg("Dependencies not found")
        errlog(log=e)
        frontend_bot_msg("Failed to install dependencies")

def check_if_captcha_redirect(web):
    """
    Checks for a webpage redirect to a captcha screen.
    This can occur after searching in job search screen.
    """
    try:
        iframe_check = web.find_elements(By.XPATH, '//iframe')
        if len(iframe_check) > 0:
            cf_manual_solver(web)
    except Exception:
        pass

    try:
        recaptcha_iframe = web.find_element(By.XPATH, '//iframe[contains(@title, "reCAPTCHA")]')
        captcha_checkbox_and_solve(web)
    except Exception:
        pass

def is_process_stopped():
    """
    Checks 'ai_running' in db and returns true if 1, false 0.
    return value sent to 'check_if_running'
    """

    ai_table = {

        'ai':
            [
                'ai_id',
                'ai_running',
                'ai_last_run'
            ]
    }

    if WE_ARE_SUBMITTING:
        db = sqlite3.connect(r'{}'.format(args.path))
    else:
        db = sqlite3.connect(os.path.join(profile_dict['shy_dir'], 'shyapply.db'))
    db.row_factory = sqlite3.Row
    db_cursor = db.cursor()
    # db_cursor.execute('SELECT * from {} WHERE {} = {}'.format(table, __id, args.id))
    db_cursor.execute('SELECT * from ai WHERE ai_id = 1')
    logs_result = db_cursor.fetchall()
    db.close()

    ai_result = []

    try:
        for row in logs_result:
            logs_dict = {item: row[item].strip() if isinstance(row[item], str) else row[item] for item in ai_table['ai']}
            ai_result.append(logs_dict)
    except Exception as e:
        errlog(description=e,log='Potential issue with is_process_stopped')

    if ai_result[0]['ai_running'] == 0:
        frontend_top_msg("Shy Apply stopped.")
        frontend_bot_msg('Free time taken back!')
        return True
    else:
        return False

def check_if_running():
    """
    evaluates bool from 'is_process_stopped' and if 0, terminates script.
    A value of 1 means the frontend is still running.
    a value of 0 means stop button was pressed or the session terminated.
    """
    try:
        proc_list = []
        for proc in psutil.process_iter():
            if platform_proc_name in proc.name().lower():
                proc_list.append("shyapply")
                break
        if len(proc_list) == 0:
            errlog(element="proc.name()", log='Application terminated by user.')
            frontend_bot_msg('Application closed...')
            log_then_exit()
        elif len(proc_list) > 0:
            if is_process_stopped() == True:
                errlog(element="Stop button", log='Stop button pressed by user.')
                frontend_top_msg('Ready To Search')
                finalprint = "Click 'Start' to automate your job search"
                frontend_bot_msg("Click 'Start' to automate your job search")
                log_then_exit()
    except Exception as e:
        errlog(description=e ,element="psutil", log="error in reading process list")
        finalprint = "Error in reading process list"
        log_then_exit()

def start_warning(seconds=15, proc_interval = 3):
    """
    A user indecisiveness check. Displays a countdown visible to the user.
    'proc_interval' is how often the script calls 'check_if_running'.
    'Seconds' must be divisible by 'proc_interval' to get a process check at 0 seconds.
    """
    timer = seconds
    proc_int = proc_interval

    frontend_top_msg("Preparing to launch")

    while timer > 0:

        if timer >= 60:
            mins_left = round(timer // 60, 1)
            if mins_left == 1:
                mins_left_string = str(round(timer // 60, 1)) + " minute"
            elif mins_left > 1:
                mins_left_string = str(round(timer // 60, 1)) + " minutes"

            secs_left = timer - (round(timer // 60, 1) * 60)
            if secs_left == 1:
                secs_left_string = str(timer - (round(timer // 60, 1) * 60)) + " second"
            elif secs_left > 1:
                secs_left_string = str(timer - (round(timer // 60, 1) * 60)) + " seconds"
            elif secs_left == 0:
                secs_left_string = '' # Convert this into None if adding any string after
        elif timer < 60:
            mins_left_string = None
            if timer == 1:
                secs_left_string = str(timer) + " second"
            elif timer > 1:
                secs_left_string = str(timer) + " seconds"

        if mins_left_string is None:
            time_left = f"Starting in {secs_left_string}"
        else:
            time_left = f"Starting in {mins_left_string} {secs_left_string}"

        frontend_bot_msg(time_left)
        time.sleep(1)
        timer -= 1

        if proc_int == 0:
            check_if_running()
            proc_int = proc_interval
        else:
            proc_int -= 1

def barrens_chat(String, seconds, proc_interval = 60):
    """
    A timeout to speed cap script to dodge certain bot detection methods.
    980 seconds roughly equateds to 3 applications per hour.
    """
    timer = seconds
    proc_int = proc_interval

    frontend_bot_msg(String)

    while timer > 0:
        time.sleep(3)
        timer -= 3

        if proc_int == 0:
            check_if_running()
            proc_int = proc_interval
        else:
            proc_int -= 1


# Allows for seamless testing on Windows and MacOS with no changes.
possible_proc_names = ['shy apply', 'shy-apply', 'shyapply', 'odetodionysus']
if os_name() == 'mac':
    for proc in psutil.process_iter():
        if any(word in proc.name().lower() for word in possible_proc_names):
            platform_proc_name = proc.name().lower()
            break

elif os_name() == 'win':
    for proc in psutil.process_iter():
        if any(word in proc.name().lower() for word in possible_proc_names):
            platform_proc_name = proc.name().lower()
            break

# Indecisivness Check for users.
if WE_ARE_SUBMITTING:
    start_warning()

# --------------------------------------------TURN OFF----------------------------------------------------------
if not WE_ARE_SUBMITTING:
    # This test profile has login info removed.
    # To test be sure to add your own information.

    # Test Profile 1
    profile_dict = {
        'consent_background_check': 1,
        'degree': 'CCAC',
        'edu_level': 4,
        'email_notifications': 1,
        'end_year': 2012,
        'first_name': 'Dylan',
        'indeed': 1,
        'indeed_pass': 'INDEED_PASSWORD_GOES_HERE',
        'indeed_user': 'INDEED_USERNAME/EMAIL_GOES_HERE',
        'job_city': 'Las Vegas',
        'job_remote': 1,
        'job_salary': 115000,
        'job_state_iso': 'NV',
        'job_state_long': 'Nevada',
        'job_title': 'Software Engineer',
        'last_name': 'Taylor',
        'linkedin': 1,
        'linkedin_url': 'www.linkedin.com/in/dylan-taylor-11b5b32ba',
        'linkedin_pass': 'LINKEDIN_PASSWORD_GOES_HERE',
        'linkedin_user': 'LINKEDIN_USERNAME/EMAIL_GOES_HERE',
        'major': 'Computer Science',
        'no_sponsorship': 1,
        'personal_address': '2420 Enchantment Cir',
        'personal_city': 'Las Vegas',
        'personal_email': 'dylan@dylgod.com',
        'personal_phone': 1231231231,
        'personal_state_iso': 'NV',
        'personal_state_long': 'Nevada',
        'personal_zip': '89074',
        'previous_work_job_title': 'Software Engineer',
        'previous_work_company': 'Shy Apply',
        'resume_file': 'Dylan Taylor 2024.pdf',
        'resume_path': r"C:\Users\USERNAME\path\to\resume",
        'school': 'NV Cyber Charter School',
        'shy_dir': r'C:\Users\USERNAME\AppData\Local\shy-apply',
        'sms_notifications': 1,
        'work_legal': 1,
        'ziprecruiter': 0,
        'ziprecruiter_pass': 'ZIPRECRUITER_PASSWORD_GOES_HERE',
        'ziprecruiter_user': 'ZIPRECRUITER_PASSWORD_GOES_HERE',
        'glassdoor': 0,
        'glassdoor_pass': 'GLASSDOOR_PASSWORD_GOES_HERE',
        'glassdoor_user': 'GLASSDOOR_PASSWORD_GOES_HERE',
        'yearsofexp': '5'
    }

    # Required for Test mode on MacOS
    if os_name() == 'mac':
        profile_dict.update({'shy_dir': os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'shy-apply')})

# --------------------------------------------TURN ON-----------------------------------------------------------
if WE_ARE_SUBMITTING:
    url: str = os.environ["SUPABASE_URL"]
    key: str = os.environ["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)

    try:
        response = supabase.table('subs').select('tokens').eq("id",uuid).execute()
    except Exception:
        supa_retry("ping")

    response_dict = response.model_dump()
    tokens = response_dict['data'][0]['tokens']
    if tokens <= 0:
        finalprint = "Not enough tokens!"
        frontend_top_msg("Shy Apply stopped.")
        frontend_bot_msg("Not enough tokens!")
        log_then_exit()

    def set_last_run():
        """
        After significant progress in script's runtime, writes current time into ai_last_run db row.
        This is a measure to help non-technical users avoid bans and/or contamination of their ip through
        many repeated consecutive uses.

        Limits script usage to once per hour.

        """
        global finalprint

        fields = {

            'ai' :
                [
                    'ai_id',
                    'ai_running',
                    'ai_last_run'
                ]
            ,
            'auth' :
                [
                    'auth_id',
                    'auth_linkedin_username',
                    'auth_linkedin_pass',
                    'auth_indeed_username',
                    'auth_indeed_pass',
                    'auth_ziprecruiter_username',
                    'auth_ziprecruiter_pass',
                    'auth_glassdoor_username',
                    'auth_glassdoor_pass'
                ]
            ,
            'education' :
                [
                    'edu_id',
                    'edu_level',
                    'edu_high_school',
                    'edu_high_school_start',
                    'edu_high_school_end',
                    'edu_high_school_achievements',
                    'edu_university_achievements',
                    'edu_college',
                    'edu_certifications'
                ]
            ,
            'experience' :
                [
                    'exp_id',
                    'exp_jobs'
                ]
            ,
            'logs' :
                [
                    'log_id',
                    'log_date',
                    'log_severity',
                    'log_location',
                    'log_action',
                    'log_description',
                    'log_notes',
                    'log_created'
                ]
            ,
            'personal' :
                [
                    "per_consent_background",
                    "per_allow_email",
                    "per_first_name",
                    "per_last_name",
                    "per_linkedin_url",
                    "per_no_sponsorship",
                    "per_address",
                    "per_city",
                    "per_email",
                    "per_phone",
                    "per_state_iso",
                    "per_state",
                    "per_zip",
                    "per_resume_path",
                    "per_allow_sms",
                    "per_work_legal",
                ]
            ,
            'platforms' :
                [
                    'plat_id',
                    'plat_linkedin',
                    'plat_linkedin_use_google',
                    'plat_linkedin_use_apple',
                    'plat_indeed',
                    'plat_indeed_use_google',
                    'plat_indeed_use_apple',
                    'plat_ziprecruiter',
                    'plat_ziprecruiter_use_google',
                    'plat_glassdoor',
                    'plat_glassdoor_use_google',
                    'plat_glassdoor_use_facebook'
                ]
            ,
            'profiles' :
                [
                    'pro_id',
                    'pro_created',
                    'pro_last_edited',
                    'pro_complete'
                ]
            ,
            'system' :
                [
                    'sys_id',
                    'sys_database_version',
                    'sys_local_appdata',
                    'sys_roaming_appdata',
                    'sys_os',
                    'sys_arch',
                    'sys_shy_directory',
                    'sys_home_directory',
                    'sys_last_ran'
                ]
            ,
            'work' :
                [
                    'work_id',
                    'work_city',
                    'work_state',
                    'work_state_iso',
                    'work_country',
                    'work_country_iso',
                    'work_title',
                    'work_annual_salary',
                    'work_monthly_salary',
                    'work_hourly_wage',
                    'work_remote',
                    'work_years_of_experience'
                ]
        }

        def sql_query_ai(table):
            """
            Port of sql_query_table function.
            Only queries ai table for logging the last time the script was run.
            """
            logslist = []
            __id = 'ai_id' # first 3 letters in id_list entries are all different

            db = sqlite3.connect(r'{}'.format(args.path))
            db.row_factory = sqlite3.Row
            db_cursor = db.cursor()
            if table == 'ai' or table == 'system':
                db_cursor.execute('SELECT * from {} WHERE {} = 1'.format(table, __id))
            else:
                db_cursor.execute('SELECT * from {} WHERE {} = {}'.format(table, __id, args.id))
            logs_result = db_cursor.fetchall()
            db.close()

            try:
                for row in logs_result:
                    logs_dict = {item: row[item].strip() if isinstance(row[item], str) else row[item] for item in fields[table]}
                    logslist.append(logs_dict)
            except NameError:
                frontend_top_msg("Shy Apply stopped.")
                frontend_bot_msg("Failed to query SQL table")
                sys.exit()

            return logslist

        ai = sql_query_ai('ai')

        if ai[0]['ai_last_run'] is not None:
            epoch_timenow = int(time.time())
            time_last_run = int(ai[0]['ai_last_run'])

            try:
                if epoch_timenow - time_last_run < 3600:
                    pass
                elif epoch_timenow - time_last_run >= 3600:
                    update_time = f'UPDATE ai SET ai_last_run = {str(int(time.time()))} WHERE ai_id = 1'
                    try:
                        db = sqlite3.connect(r'{}'.format(args.path))
                        db.row_factory = sqlite3.Row
                        db_cursor = db.cursor()
                        db_cursor.execute(update_time)
                        db.commit()
                        db.close()
                    except Exception as err:
                        errlog(element='update_time + db', description=err, log='something went wrong with db write. (wrong path, read-write same time, db not present)')
            except Exception as e:
                errlog(severity=12, element="ai_last_run", description=e, log='something went wrong with time comparison')

        elif ai[0]['ai_last_run'] is None:
            update_time = f'UPDATE ai SET ai_last_run = {str(int(time.time()))} WHERE ai_id = 1'
            try:
                db = sqlite3.connect(r'{}'.format(args.path))
                db.row_factory = sqlite3.Row
                db_cursor = db.cursor()
                db_cursor.execute(update_time)
                db.commit()
                db.close()
            except Exception as e:
                errlog(element='update_time + db', description=e, log='something went wrong with db write. (wrong path, read-write same time, db not present)')

    def generate_profile_dict():
        global finalprint

        # Local db structure
        fields = {

            'ai' :
                [
                    'ai_id',
                    'ai_running',
                    'ai_last_run'
                ]
            ,
            'auth' :
                [
                    'auth_id',
                    'auth_linkedin_username',
                    'auth_linkedin_pass',
                    'auth_indeed_username',
                    'auth_indeed_pass',
                    'auth_ziprecruiter_username',
                    'auth_ziprecruiter_pass',
                    'auth_glassdoor_username',
                    'auth_glassdoor_pass'
                ]
            ,
            'education' :
                [
                    'edu_id',
                    'edu_level',
                    'edu_high_school',
                    'edu_high_school_start',
                    'edu_high_school_end',
                    'edu_high_school_achievements',
                    'edu_university_achievements',
                    'edu_college',
                    'edu_certifications'
                ]
            ,
            'experience' :
                [
                    'exp_id',
                    'exp_jobs'
                ]
            ,
            'logs' :
                [
                    'log_id',
                    'log_date',
                    'log_severity',
                    'log_location',
                    'log_action',
                    'log_description',
                    'log_notes',
                    'log_created'
                ]
            ,
            'personal' :
                [
                    "per_consent_background",
                    "per_allow_email",
                    "per_first_name",
                    "per_last_name",
                    "per_linkedin_url",
                    "per_no_sponsorship",
                    "per_address",
                    "per_city",
                    "per_email",
                    "per_phone",
                    "per_state_iso",
                    "per_state",
                    "per_zip",
                    "per_resume_path",
                    "per_allow_sms",
                    "per_work_legal",
                ]
            ,
            'platforms' :
                [
                    'plat_id',
                    'plat_linkedin',
                    'plat_linkedin_use_google',
                    'plat_linkedin_use_apple',
                    'plat_indeed',
                    'plat_indeed_use_google',
                    'plat_indeed_use_apple',
                    'plat_ziprecruiter',
                    'plat_ziprecruiter_use_google',
                    'plat_glassdoor',
                    'plat_glassdoor_use_google',
                    'plat_glassdoor_use_facebook'
                ]
            ,
            'profiles' :
                [
                    'pro_id',
                    'pro_created',
                    'pro_last_edited',
                    'pro_complete'
                ]
            ,
            'system' :
                [
                    'sys_id',
                    'sys_database_version',
                    'sys_local_appdata',
                    'sys_roaming_appdata',
                    'sys_os',
                    'sys_arch',
                    'sys_shy_directory',
                    'sys_home_directory',
                    'sys_last_ran'
                ]
            ,
            'work' :
                [
                    'work_id',
                    'work_city',
                    'work_state',
                    'work_state_iso',
                    'work_country',
                    'work_country_iso',
                    'work_title',
                    'work_annual_salary',
                    'work_monthly_salary',
                    'work_hourly_wage',
                    'work_remote',
                    'work_years_of_experience'
                ]
        }

        def sql_query_table(table):
            """
            Queries local sql db using unique 3 character identifier for tables.
            ai table = ai_
            auth table = aut
            ...
            """
            logslist = []
            id_list = ['ai_id' ,'auth_id', 'edu_id', 'exp_id', 'log_id', 'per_id', 'plat_id', 'pro_id', 'sys_id', 'work_id']
            __id = [i for i in id_list if table[:3] in i][0] # first 3 letters in id_list entries are all different

            db = sqlite3.connect(r'{}'.format(args.path))
            db.row_factory = sqlite3.Row
            db_cursor = db.cursor()
            if table == 'ai' or table == 'system':
                db_cursor.execute('SELECT * from {} WHERE {} = 1'.format(table, __id))
            else:
                db_cursor.execute('SELECT * from {} WHERE {} = {}'.format(table, __id, args.id))
            logs_result = db_cursor.fetchall()
            db.close()

            try:
                for row in logs_result:
                    logs_dict = {item: row[item].strip() if isinstance(row[item], str) else row[item] for item in fields[table]}
                    logslist.append(logs_dict)
            except NameError:
                frontend_top_msg("Shy Apply stopped.")
                frontend_bot_msg("Failed to query SQL table")
                sys.exit()

            return logslist

        ai = sql_query_table('ai')
        auth = sql_query_table('auth')
        education = sql_query_table('education')
        experience = sql_query_table('experience')
        personal = sql_query_table('personal')
        platforms = sql_query_table('platforms')
        system = sql_query_table('system')
        work = sql_query_table('work')

        if ai[0]['ai_last_run'] is not None:
            epoch_timenow = int(time.time())
            time_last_run = int(ai[0]['ai_last_run'])

            try:
                if epoch_timenow - time_last_run < 3600:
                    learn_more_link = r"https://www.shyapply.com/guide"
                    errlog(severity=12, element="ai_last_run", log='Did not wait the hour cooldown before running. This is to prevent getting blocked by bot detection services.')
                    finalprint = f"""Shy Apply needs an hour cooldown before running.\nThis is to prevent getting blocked by bot detection services.\nLearn more here {learn_more_link}"""
                    frontend_top_msg("Shy Apply stopped.")
                    frontend_bot_msg(finalprint)
                    log_then_exit()
                elif epoch_timenow - time_last_run >= 3600:
                    pass
            except Exception as e:
                errlog(severity=12, element="ai_last_run",description=e, log='something went wrong with time comparison')

        elif ai[0]['ai_last_run'] is None:
            pass

        try:
            edu_college = json.loads(education[0]["edu_college"]) # TypeError if they skipped College fields.

            if edu_college[0]['edu_university'] is None:
                edu_degree = "None"
            else:
                edu_degree = edu_college[0]['edu_university']

            if edu_college[0]['edu_university_degree'] is None:
                edu_major = "None"
            else:
                edu_major = edu_college[0]['edu_university_degree']
        except Exception: # TypeError
            edu_degree = 'None'
            edu_major = 'None'

        try:
            if work[0]['work_years_of_experience'] is None:
                yearsofexp = "3"
            else:
                yearsofexp = str(work[0]['work_years_of_experience'])
        except Exception:
            yearsofexp = '3'

        try:
            past_job_dict = json.loads(experience[0]["exp_jobs"]) # TypeError if they skipped Job fields.
            past_work_company = past_job_dict[0]['exp_company']
            past_work_title = past_job_dict[0]['exp_title']
        except Exception: # TypeError
            past_work_company = 'none'
            past_work_title = 'none'

        if education[0]["edu_high_school_end"] is None:
            edu_end_year = fouryearsago
        else:
            edu_end_year = education[0]["edu_high_school_end"]

        if education[0]["edu_high_school"] is None:
            edu_school = "None"
        else:
            edu_school = education[0]["edu_high_school"]

        if auth[0]["auth_linkedin_username"] is None:
            auth_linkedin_username = "none"
        else:
            auth_linkedin_username = auth[0]["auth_linkedin_username"]

        if auth[0]["auth_linkedin_pass"] is None:
            auth_linkedin_pass = "none"
        else:
            auth_linkedin_pass = auth[0]["auth_linkedin_pass"]

        if auth[0]["auth_indeed_username"] is None:
            auth_indeed_username = "none"
        else:
            auth_indeed_username = auth[0]["auth_indeed_username"]

        if auth[0]["auth_indeed_pass"] is None:
            auth_indeed_pass = "none"
        else:
            auth_indeed_pass = auth[0]["auth_indeed_pass"]

        if auth[0]["auth_ziprecruiter_username"] is None:
            auth_ziprecruiter_username = "none"
        else:
            auth_ziprecruiter_username = auth[0]["auth_ziprecruiter_username"]

        if auth[0]["auth_ziprecruiter_pass"] is None:
            auth_ziprecruiter_pass = "none"
        else:
            auth_ziprecruiter_pass = auth[0]["auth_ziprecruiter_pass"]

        if auth[0]["auth_glassdoor_username"] is None:
            auth_glassdoor_username = "none"
        else:
            auth_glassdoor_username = auth[0]["auth_glassdoor_username"]

        if auth[0]["auth_glassdoor_pass"] is None:
            auth_glassdoor_pass = "none"
        else:
            auth_glassdoor_pass = auth[0]["auth_glassdoor_pass"]

        if platforms[0]["plat_indeed"] is None:
            indeed_on = 0
        else:
            indeed_on = platforms[0]["plat_indeed"]

        if platforms[0]["plat_linkedin"] is None:
            linkedin_on = 0
        else:
            linkedin_on = platforms[0]["plat_linkedin"]

        if platforms[0]["plat_ziprecruiter"] is None:
            ziprecruiter_on = 0
        else:
            ziprecruiter_on = platforms[0]["plat_ziprecruiter"]

        if platforms[0]["plat_glassdoor"] is None:
            glassdoor_on = 0
        else:
            glassdoor_on = platforms[0]["plat_glassdoor"]

        resume_file_basename = os.path.basename(personal[0]["per_resume_path"])

        profile_dict = {
            "consent_background_check": personal[0]["per_consent_background"],
            "degree": edu_degree,
            "edu_level" : education[0]["edu_level"],
            "email_notifications": personal[0]["per_allow_email"],
            "end_year" : edu_end_year,
            "first_name": personal[0]["per_first_name"],
            "indeed": indeed_on,
            "indeed_pass": auth_indeed_pass,
            "indeed_user": auth_indeed_username,
            "job_city": work[0]["work_city"],
            "job_remote": work[0]["work_remote"],
            "job_salary": work[0]["work_annual_salary"],
            "job_state_iso": work[0]["work_state_iso"],
            "job_state_long": work[0]["work_state"],
            "job_title": work[0]["work_title"],
            "last_name": personal[0]["per_last_name"],
            "linkedin": linkedin_on,
            "linkedin_pass": auth_linkedin_pass,
            "linkedin_url": personal[0]["per_linkedin_url"],
            "linkedin_user": auth_linkedin_username,
            "major": edu_major,
            "no_sponsorship": personal[0]["per_no_sponsorship"],
            "personal_address": personal[0]["per_address"],
            "personal_city": personal[0]["per_city"],
            "personal_email": personal[0]["per_email"],
            "personal_phone": personal[0]["per_phone"],
            "personal_state_iso": personal[0]["per_state_iso"],
            "personal_state_long": personal[0]["per_state"],
            "personal_zip": personal[0]["per_zip"],
            "previous_work_job_title": past_work_title,
            "previous_work_company": past_work_company,
            'resume_file': resume_file_basename,
            "resume_path": personal[0]["per_resume_path"],
            "school": edu_school,
            "shy_dir": system[0]["sys_shy_directory"],
            "sms_notifications": personal[0]["per_allow_sms"],
            "work_legal": personal[0]["per_work_legal"],
            "ziprecruiter": ziprecruiter_on,
            "ziprecruiter_pass": auth_ziprecruiter_pass,
            "ziprecruiter_user": auth_ziprecruiter_username,
            "glassdoor": glassdoor_on,
            "glassdoor_pass": auth_glassdoor_pass,
            "glassdoor_user": auth_glassdoor_username,
            "yearsofexp": yearsofexp,
        }

        return profile_dict

    try:
        profile_dict = generate_profile_dict()
    except Exception as e:
        finalprint = "Failed to find Profile"
        frontend_bot_msg("Failed to find Profile")
        frontend_top_msg('Failed to find Profile')
        errlog(element="profile_dict", description=e)
        log_then_exit()

    try:
        if profile_dict['job_salary'] < 30000:
            profile_dict.update({'job_salary': 35000})
        elif profile_dict['job_salary'] >= 1000000:
            profile_dict.update({'job_salary': 100000})
    except Exception:
        errlog(element='profile_dict["job_salary"]', log='could not convert salary')

    possible_proc_names = ['shy apply', 'shy-apply', 'shyapply']
    if os_name() == 'mac':
        for proc in psutil.process_iter():
            if any(word in proc.name().lower() for word in possible_proc_names):
                platform_proc_name = proc.name().lower()
                break

    elif os_name() == 'win':
        for proc in psutil.process_iter():
            if any(word in proc.name().lower() for word in possible_proc_names):
                platform_proc_name = proc.name().lower()
                break

    try:
        if WE_ARE_SUBMITTING:
            get_dependencies()
            barrens_chat(String='Starting', seconds=8)
    except Exception as e:
        frontend_top_msg('Failed to start')
        errlog(description=e, log='Failed to start')
        finalprint = 'Failed to install dependencies'
        frontend_bot_msg('Failed to install dependencies')
        log_then_exit()

# -------------------------------------------------------------------------------------------------------------
num_apps_divisor = 1 # Uncomment to change static num_apps to dynamic
if profile_dict["linkedin"] == 1:
    num_apps_divisor +=1
if profile_dict["indeed"] == 1:
    num_apps_divisor +=1
if profile_dict["ziprecruiter"] == 1:
    num_apps_divisor +=1
if profile_dict["glassdoor"] == 1:
    num_apps_divisor +=1

if WE_ARE_SUBMITTING:
    num_apps = int(args.jobs) // (num_apps_divisor - 1)  # Total applications divided by number of websites selected
else:
    num_apps = 3

yourname = profile_dict['first_name'] + " " + profile_dict['last_name']
citystate = profile_dict["job_city"] + ", " + profile_dict["job_state_long"]
citystate_short = profile_dict["job_city"] + ", " + profile_dict["job_state_iso"]
citystatecountry = profile_dict["job_city"] + ", " + profile_dict["job_state_long"] + ", " + "United States"
choice_resumepath = profile_dict['resume_path']
years_experience = profile_dict['yearsofexp']

indeed_yardsale_examples = """A few years ago I hosted a yard sale and I had a customer who was not pleased with her purchase and was quite frustrated. To de-escalate the situation, I offered her a refund and then suggested some similar items that might fit their needs better. She was grateful for my patience and in the end I made a sale. Another example that happened recently, I was out shopping for food and I saw an elderly lady visibly lost in the aisle that I was in. I offered my help and as it turned out, she couldn't reach a box of cake mix. I got it for her and she was elated."""

indeed_cover_letter = f"""Dear Hiring Manager,

I am writing to express my interest in a position at your company. With my experience in problem-solving and leadership, I am confident that I would be an excellent addition to your team.

I have worked in a variety of roles for many years, developing my skills in communication, conflict resolution, and working with diverse teams. In my current role, I have taken the lead on various projects, utilizing my expertise to drive successful results. My experience has given me the skills to be an asset in the position you are offering.

I am eager to bring my enthusiasm and motivation to your company, and I am confident that I have the qualifications that you are seeking.

Thank you for your time and consideration. I look forward to discussing my qualifications with you further.

Sincerely,
{profile_dict['first_name'] + " " + profile_dict['last_name']}"""

indeed_text_check = {
    'In a few sentences, tell us something about you that would help us understand your qualifications and reasons for exploring this career opportunity?': 'With my experience in problem-solving and leadership, I am confident that I would be an excellent addition to your team. I have worked in a variety of roles for many years, developing my skills in communication, conflict resolution, and working with diverse teams.',
    'Why do you think you would particularly enjoy working in a bank? What specific skills would you bring to the team?': 'With my experience in problem-solving and leadership, I am confident that I would be an excellent addition to your team. I have worked in a variety of roles for many years, developing my skills in communication, conflict resolution, and working with diverse teams.',
    'List any foreign language(s) you know and describe your skill level in the following terms': 'see resume',
    'Provide a current or previous supervisor/manager as a reference and contact information.': 'see resume',
    'Please list professional, trade, business or civic associations and any offices held.': 'see resume',
    'Describe your previous cash or transaction handling experience you might have had.': 'Happy to answer all questions in an interview :)',
    'Would you consider a similar position working at another dealership location?': 'I would at a maximum of 50 miles distance away.',
    'Provide your most relevant job title held that compares to this position.': 'see resume',
    'How do you perform in a work environment with processes and routines?': 'Having a work environment with set processes and routines is very reliable and preferred. Understanding the standard work flow streamlines the teambuilding process.',
    "If you were referred by an employee, please list the employee's name:": 'n/a',
    'Give 2 examples of when you have provided excellent customer service': indeed_yardsale_examples,
    'Provide 2 professional references and contact information for both.': 'see resume',
    'Are there currently any hours or days you are unavailable to work?': 'I am fully available',
    'Please provide your compensation expectations for this position.': profile_dict['job_salary'],
    'List any additional information you would like us to consider.': 'see resume',
    'List additional skills, qualifications, and certifications': 'Problem-solving and leadership experience\nCommunication \nConflict Resolution',
    'List special accomplishments, publications, or awards.': 'see resume',
    'If necessary, the best time to call you at home is:': '10am-5pm', "How many times did you play 18 holes of golf": "10.0",
    'Please list 2-3 dates and times or ranges of times': 'I am available Monday through Friday from 10 AM to 5 PM',
    'What is your desired hourly rate or annual salary?': profile_dict['job_salary'],
    'Do you have experience working with Sage Intacct?': 'No', 'If you were referred by a current employee,': 'n/a',
    'If yes, please provide date(s) and details': 'n/a', 'If you were referred by an employee, who?': 'n/a',
    'What is your desired annual compensation?': profile_dict['job_salary'], 'Have you ever been employed here before?': 'No',
    'Disability Questionnaire Answered Date': todaysdate, 'Are you related to anyone working for': 'No',
    'please provide your employee number': 'N/A', 'What are your salary requirements?': profile_dict['job_salary'],
    'If Employee, please provide name': 'n/a', 'Are you willing to work on-site?': 'Yes',
    'Enter Additional Comments Here': 'n/a', 'Have you ever been terminated': 'No', 'What is your desired salary?': profile_dict['job_salary'],
    'Have you ever had clearance?': 'No', 'Will you be able to reliably': 'Yes', 'May we contact you at work?': 'No',
    'Website, blog or portfolio': profile_dict['linkedin_url'], "Reference's Email Address:": 'see resume',
    "Reference's Organization:": 'see resume', 'do you foresee any issues': 'No', "How did you hear about": "Indeed.com", "about opportunities at": "Indeed.com",
    "Reference's Telephone:": 'see resume', 'experience do you have': '3 years of experience','Linkedin Profile':profile_dict['linkedin_url'],'social media profile':profile_dict['linkedin_url'],
    'Minimum Hourly Rate:': '1', 'Electronic Signature': yourname, 'convicted of a crime': 'N/A','Please describe your salary expectations.': profile_dict['job_salary'],
    'Type Your Full Name': yourname, 'Comments(optional)': 'n/a', "Reference's Name:": 'see resume','Current (Most Recent) Employer':'faang','Current (Most Recent) Job Title': profile_dict['job_title'],
    'If yes, explain:': 'n/a', 'Desired Salary': profile_dict['job_salary'], 'Send us a link': 'links in resume',
    'Candidate Name': yourname, 'If so, when?': 'n/a', 'Postal Code': profile_dict["personal_zip"], '(optional)': 'skip',"salary expectations":profile_dict['job_salary'],
    'Your Name:': yourname, 'Zip/Postal': profile_dict["personal_zip"], 'Cell Phone': profile_dict['personal_phone'], 'Address': profile_dict['personal_address'],
    'Amount': profile_dict['job_salary'],'City, State': citystate_short, 'State': profile_dict['job_state_iso'], 'City': profile_dict['job_city'], 'Name': yourname, 'Zip': profile_dict['personal_zip'], 'compensation': '80000', 'What language': 'English',
    "Today's Date": todaysdate, 'Date available for work': todaysdate, 'todays date': todaysdate, "Today’s Date:": todaysdate,"What wage":profile_dict['job_salary']}

indeed_radio_check = {
    'If you are under 18 years of age, can you provide required proof of your eligibility to work?': 'N/A',
    'If you believe you belong to any of the categories of protected veterans listed above': 'I DO NOT WISH TO IDENTIFY AT THIS TIME',
    'By submitting this application: (Please acknowledge acceptance by checking all boxes)': 'I understand',
    'Are you able to perform the essential functions of the job for which you are applying': 'Yes',
    "Has your driver's license ever been suspended, revoked, denied or cancelled?": 'No',
    'This employer is a Government contractor subject to the Vietnam Era': 'I prefer not to answer',
    'Do you have significant irregularities in your financial history': 'No, there are not significant irregularities in my personal finances',
    'By checking this box, you acknowledge and consent to terms of': 'I have read and agree to this statement',
    'I would like to receive updates about my application via SMS.': 'No',
    'How many years of experience do you have in a similar role?': '2-3 Years',
    'How many years of prior banking experience do you possess?': 'One-Three years of experience',
    'Would you like to opt-in to receive email notifications': 'Yes, I would like to receive email notifications about new jobs',
    'How many years of prior sales experience do you posses?': 'One-Three years of experience',
    'Have any past employers taken any disciplinary action': 'No',
    'By submitting your application you hereby certify': 'I have read and accept the above acknowledgement',
    'Do you have a business name and/or an EIN number?': 'Will setup for this position',
    'Have you ever been or are you currently employed': 'No',
    'Select which best describes your right to work in the US?': 'I have permanent work rights',
    'You are considered to have a disability if you': 'Wish To Answer',
    'Are you a current or former Curaleaf employee?': 'New to the Company',
    'How many years of Salesforce Development experience do you have?':'3-6',
    'Are you interested in Part-Time or Full-Time?': 'Full-Time', 'Are you available to work Saturday mornings?': 'Yes',
    'VOLUNTARY SELF-IDENTIFICATION OF DISABILITY': 'Wish To Answer',"ever interviewed with":"No","ever been employed by":"No",
    'Voluntary Self-Identification of Disability': "I don't wish to answer","restricting your ability to work":"No",
    'Do you currently maintain an active license': 'Yes', 'Do you speak English and Spanish fluently?': 'Yes',
    'What type of delivery vehicle do you have?': 'Plan on renting required vehicle',
    'Have you notified your current supervisor': 'I am not a current employee',
    'How many years of experience do you have?': '3-5 years', 'How many years of related job experience': '1-5 years',
    'How did you find out about this listing?': 'Indeed',"terminated from employment":"No", "ever been fired":"No",
    'What us your highest level of education?': "Bachelor's Degree",
    'Please choose one of the options below:': "I Don't Wish To Answer",
    'Are you on layoff or subject to recall?': 'No', 'What is the highest level of education': "Bachelor's",
    'Have you ever worked for this company?': 'No', 'Have you ever been previously employed': 'No',
    'Do you give us permission to text you': 'No', 'Are you able to communicate and write': 'Yes',
    'Have you ever served in the military?': 'No', 'How did you hear about this position': 'Other',
    'VETERANS INVITATION TO SELF-IDENTIFY': "I DON'T WISH TO ANSWER", 'It is okay to send me text messages': 'No',
    'Have you ever been in the Military': 'No','previously gone through the interview process' : 'No',
    'Policy for receiving text messages': 'No, I do not agree to receive text messages',
    'What is your desired service line?': 'Both', 'What is your desired job category?': 'Nursing',
    'Do you require company sponsorship': 'No', 'Do you speak English and Spanish?': 'Yes',
    'Do you have relatives employed by': 'No', 'Are you 21 years of age or older?': 'Yes',
    'Are you able to pass a drug test': 'Yes', 'If you are under 18 years of age': 'I am 18 years of age or older',
    'What is your desired pay range?': '$75,000 - $100,000', 'Have you previously worked for': 'No',
    'Have you ever applied with our': 'No', 'Do you have a criminal record': 'No',
    'Have you ever been discharged': 'No', 'Do you currently live within': 'Yes', 'Have you ever been convicted': 'No',
    'What is your desired salary': 'Annually','Where did you hear about us?': 'Job Site',
    'What Computer/s do you own?': 'Windows Based - Sony/Lenovo/HP/Dell, etc (Newer or top of the line)','What Computers do you own?' : 'Windows Based - Sony/Lenovo/HP/Dell, etc (Newer or top of the line)',
    'Are you over the age of 18?': 'Yes', 'Are you currently employed?': 'No', 'Are you willing to purchase': 'No',"sponsor you for work":"No","previously been employed":"No",
    'been convicted of a crime?': 'No', 'What is your legal status?': 'US Citizen', 'Do you have the following': 'Yes',
    'Are you available to work': 'Yes', 'Have you been employed by': 'No', 'Select Disability Status': 'No',
    'Are you legally eligible': 'Yes', 'Would you be comfortable': 'Yes', 'Have you ever worked for': 'No',
    'Have you ever been fired': 'No', 'Do you understand this?': 'I understand', 'Have you been convicted': 'No',
    'Do you have experience': 'Yes', 'Are you familiar with': 'Yes', 'Do you speak English?': 'Yes',
    'Do you speak Spanish?': 'Yes', 'Do you have the right': 'Yes', 'Do you speak fluent English?' : 'Yes',
    'Select currency type': 'United States Dollar (USD)', 'Were you referred by': 'No', 'require sponsorship': 'No','require employer visa sponsorship': 'No',
    'ever been convicted': 'No', 'Do you have a valid': 'Yes', 'Have you been cited': 'No', 'have you completed': 'Yes',
    'authorized to work': 'Yes', 'are you authorized': 'Yes', 'Can you be on site': 'Yes', 'Have you worked as': 'Yes',
    'employee refer you': 'No', 'Do you understand': 'Yes', '18 years or older': 'Yes', 'Did you Graduate?': 'Yes',
    'Have you read all': 'Yes', 'are you eligible': 'Yes', 'background check': 'Yes', 'reliably commute': 'Yes',
    'are you at least': 'Yes', 'Your Citizenship': 'U.S', 'Will you require': 'No', 'Are you 18 years': 'Yes','sponsorship to work':'No',
    'Are you bound by': 'No', 'What percentage': '100', 'i certify that': 'Yes', 'if necessary': 'Yes','willing to comply':'Yes',
    'Referred by:': 'Indeed', 'School Type:': 'College/Technical', 'at least 21': 'Yes', 'Salary Type': 'Year',"relatives":'No', "related":'No',
    '(optional)': 'skip', 'Frequency': 'yearly', 'over 18': 'Yes', 'over 21': 'Yes', 'Gender': 'I decline to identify',"Country Code":"United States","require visa sponsorship":"No"}

indeed_number_check = {"(optional)": 'skip', "salary requirements": profile_dict['job_salary'], "desired wage": "1", "How many years": years_experience,
                       "Please enter the amount": "1", "On a scale of 1-10": "8", "How many times did you play 18 holes of golf": "10.0",
                       "Reference's Telephone:": "7027386369", "Phone Number": profile_dict['personal_phone'],
                       "What is your desired salary?": profile_dict['job_salary'], "What is your zip code?": profile_dict["personal_zip"],
                       "Please confirm your currently salary or hourly rate": profile_dict['job_salary'],
                       "What is your expected pay?": profile_dict['job_salary']}

indeed_checkbox_check = {
    'What Salesforce credentials do you have?':'Platform App Builder,Platform Developer I,JavaScript Developer I,Marketing Cloud Developer,B2C Commerce Developer',
    'Is there anything in your lifestyle, your past, or your current condition that would keep you from performing the job as specified?': 'NO',
    'Are you interested in applying for any other jobs': 'Only interested in the position I am applying for',
    'Are you authorized to work in the United States?': 'Yes',
    'Which job sites have you been using?': 'Indeed,ZipRecruiter,LinkedIn',
    'Do you have reliable transportation?': 'YES', 'How did you learn of this position?': 'LinkedIn,Indeed',
    'Self Attestation is required.': 'Yes, I agree to sign electronically.','What coding languages do you know?':'JavaScript,Python,C,HTML',
    'Section 503 Disability Status': 'I have read the Voluntary Self-Identification of Disability Form and understand that I have the option to disclose whether or not I am an individual with a disability.',
    'are you available to work': 'Day,Night,Overnight', 'years of professional experience do you have': '3-5',
    'What phone/s do you own?': 'iPhone (older or NOT top of the line),iPhone (recent or Top of the line)', 'How did you hear about': 'Indeed',
    'Data rates may apply': 'receive text messages', 'I certify that': 'Yes', '(optional)': 'skip',
    'Race': 'Prefer not to answer',"CGMA (Chartered Global Management Accountant)":"CPA (Certified Public Accountant)","Do you currently hold any of these designations?":"CPA (Certified Public Accountant)","Are you open to working onsite":"Onsite,Hybrid- Some time onsite and some time offsite,Fully Remote"}

indeed_select_check = {
    'What is the closest annual salary range you would expect for this position?': '$200,000 or Greater',
    'This employer is a Government contractor subject to the Vietnam Era': 'I choose not to self-identify',
    'Provide valid phone numbers to allow Recruiters to contact you': 'United States (+1)',
    'How did you first hear about this opportunity?': 'Indeed.com',
    'Where did you hear about this opportunity?': 'Indeed', 'How did you hear about this position?': 'Indeed',
    'highest level of education completed?': 'Some College', 'How did you hear about this job?': 'Indeed',
    'confirm your veteran status': 'I do not wish to specify at this time',
    'highest educational degree': 'Bachelors Degree', 'Current Compensation': 'USD', 'Desired Compensation': 'USD',
    'Select currency type': 'United States Dollar (USD)','How did you hear about this role?':'LinkedIn',
    'Ethnic Background?': 'I choose not to provide race information.',
    'Ethnic Background': 'I choose not to provide race information.', 'Referral Source:': 'Indeed.com',
    'Ethnicity/Race': 'I decline to identify', 'Race/Ethnicity': 'Decline to Answer', '(optional)': 'skip',
    'State': profile_dict['job_state_long'],"How many years of":"3-4"}

indeed_date_check = {"(optional)": 'skip', "Today’s Date:": todaysdate, "Date:": todaysdate, "Date": todaysdate,
                     "Today's Date": todaysdate, "Date available for work": todaysdate, "todays date": todaysdate}

indeed_skip_check = {"(optional)": 'skip',
                     "Data rates may apply": "skip"}  # ---THE SAME KEY MUST BE IN SKIP AND ITS CORRECT CHECK DICT

def Indeed_Driver(web):

    def indeed_appform_capcha():
        try:
            iframe = web.find_element(By.XPATH, "//iframe[@title='reCAPTCHA']")
            capbtn_x = iframe.location["x"] + (iframe.size["height"]/2)
            capbtn_y = iframe.location["y"]+ (iframe.size["height"]/2)
            capbrain = ActionBuilder(web)
            capbrain.pointer_action.move_to_location(capbtn_x, capbtn_y)
            capbrain.pointer_action.click()
            capbrain.perform()
            time.sleep(2)
        except Exception as e:
            errlog(element="indeed_appform_capcha", description=e)

    def cookiecheck():

        try:
            cookienotice = web.find_element(By.XPATH, "//div[@id='CookiePrivacyNotice']")
        except NoSuchElementException:
            return

        try:
            cookie_okbtn = web.find_element(By.XPATH, '//button[contains(@class, "CookiePrivacy")]')
            cookie_okbtn.click()
        except Exception:
            try:
                cookie_okbtn = web.find_element(By.XPATH, "//div[@id='CookiePrivacyNotice']//descendant::button")
                cookie_okbtn.click()
            except Exception as e:
                errlog(element="cookie_okbtn",description=e)
        time.sleep(1)

    def search_str(file_path, word): # QUESTION LOGGING
        """
        :param file_path:
        :type file_path:
        :param word:
        :type word:
        :return:
        :rtype:
        """

        if os.path.exists(file_path) == False:
            with open(file_path, 'a'): pass

        with open(file_path, 'r') as file:
            # read all content of a file
            content = file.read()
            # check if string present in a file
            if word in content:
                return True
            else:
                return False

    def slow_Scroller():#---------Use if scroll detected
        total_height = int(web.execute_script("return document.body.scrollHeight"))
        for i in range(1, total_height, 5):
            web.execute_script("window.scrollTo(0, {});".format(i))

    def Indeed_Google(web):
        global finalprint
        anchor = web.current_window_handle
        try:
            google_btn = web.find_element(By.ID, "login-google-button")
            google_btn.uc_click()
        except Exception:
            try:
                google_btn = web.find_element(By.ID, "gsuite-login-google-button")
                google_btn.uc_click()
            except Exception as e:
                errlog(element="google_btn", description=e)
        time.sleep(2)

        for handle in web.window_handles:
            web.switch_to.window(handle)
            if handle != anchor:
                break

        try:
            google_email = web.find_element(By.XPATH, '//input[@type="email"]')
            bot_typer(google_email, profile_dict['indeed_user'])
            time.sleep(5.229)
            google_nextbtn = web.find_element(By.XPATH, "//button[@type='button']//child::span[contains(text(), 'Next')]")
            google_nextbtn.uc_click()
            time.sleep(2)
        except Exception as e:
            errlog(element="google_email", description=e)

        try:
            google_password = web.find_element(By.XPATH, "//input[@type='password']")
            bot_typer(google_password, profile_dict['indeed_pass'])
            time.sleep(4.13)
            google_nextbtn2 = web.find_element(By.XPATH, "//button[@type='button']//child::span[contains(text(), 'Next')]")
            google_nextbtn2.uc_click()
            time.sleep(0.4)

            try:
                wrong_google_pw = web.find_element(By.XPATH, "/html/body").text
                if "wrong password" in wrong_google_pw.lower():
                    finalprint = "Indeed wrong password"
                    web.close()
                    web.switch_to.window(anchor)
                else:
                    check_if_captcha_redirect(web)

                    try:
                        google_password = web.find_element(By.XPATH, "//input[@type='password']")
                        bot_typer(google_password, profile_dict['indeed_pass'])
                        time.sleep(4.13)
                        google_nextbtn2 = web.find_element(By.XPATH, "//button[@type='button']//child::span[contains(text(), 'Next')]")
                        google_nextbtn2.uc_click()
                        time.sleep(0.4)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception as e:
            errlog(element="google_password", description=e)

        web.switch_to.window(anchor)
        time.sleep(2)

    def Indeed_Qfill_error():
        global error_catchvar
        try:
            for errormsg in web.find_elements(By.XPATH, '//div[contains(@class, "ia-Questions-item")]//child::div[contains(@id, "errorTextId")]'):
                errorQ_id = errormsg.find_element(By.XPATH, "ancestor::div[contains(@class, 'ia-Questions-item')]").get_attribute("id")

                try:
                    answer = web.find_element(By.XPATH, "//*[@id='{}']//input".format(errorQ_id))
                except NoSuchElementException:
                    try:
                        answer = web.find_element(By.XPATH, "//*[@id='{}']//textarea".format(errorQ_id))
                    except NoSuchElementException:
                        try:
                            answer = web.find_element(By.XPATH, "//*[@id='{}']//select".format(errorQ_id))
                        except NoSuchElementException:
                            continue

                answer_type = answer.get_attribute("type")

                if answer_type == "number":
                    num = re.findall(r'\d+',errormsg.text)
                    try:
                        bot_typer(answer,num[0])
                    except Exception:
                        if "Answer must be a valid number" in errormsg.text:
                            bot_typer(answer,"10")
                if answer_type == "tel":
                    num = re.findall(r'\d+',errormsg.text)
                    try:
                        bot_typer(answer,num[0])
                    except Exception:
                        if "Answer must be a valid number" in errormsg.text:
                            bot_typer(answer,"10")
        except Exception as e:
            errlog(element="Qfill_error",description=e)

    def indeed_GoNext():# webdriverwait here, no displayed just click
        # print("indeed_GoNext called")
        global error_catchvar
        global Indeed_Job_count
        nextcount = 0
        gonext_list = []

        # def Indeedfinder():#----Added bc of an unknown bug at the time. Still could be usefull later.
        #     try:
        #         web.execute_script('window.scrollBy({ top: 700, left: 0, behavior: "smooth",});')
        #         time.sleep(1.114)
        #     except Exception as e:
        #         errlog(element="Indeedfinder",description=e)

        def Indeed_btn_fanhammer(xpathVAR):
            fail_num = 0
            btns = web.find_elements(By.XPATH, xpathVAR)
            if len(btns) == 0:
                errlog(element='btns', log='found no btns after converion to elements')
                raise ElementNotInteractableException

            for btn in btns:
                try:
                    btn.click()
                    break
                except ElementNotInteractableException:
                    time.sleep(0.3)
                    fail_num+=1
                    continue

            if fail_num == len(btns):
                raise ElementNotInteractableException

        try:
            indeed_app_continue = web.find_element(By.XPATH, "//button[contains(@class, 'ia-Question-continue')]//child::span[contains(text(), 'Continue')]")
            if indeed_app_continue:
                cont_btn_xpath = "//button[contains(@class, 'ia-Question-continue')]//child::span[contains(text(), 'Continue')]"
                gonext_list.append("Continue")
        except Exception:
            try:
                indeed_app_continue = web.find_element(By.XPATH, "//button[contains(@class, 'ia-Resume-continue')]//child::span[contains(text(), 'Continue')]")
                if indeed_app_continue:
                    cont_btn_xpath = "//button[contains(@class, 'ia-Resume-continue')]//child::span[contains(text(), 'Continue')]"
                    gonext_list.append("Continue")
            except Exception:
                try:
                    indeed_app_continue = web.find_element(By.XPATH, "//button/span[contains(text(), 'Continue')]")
                    if indeed_app_continue:
                        cont_btn_xpath = "//button/span[contains(text(), 'Continue')]"
                        gonext_list.append("Continue")
                except Exception:
                    try:
                        indeed_app_continue = web.find_element(By.XPATH, "//button[contains(@class, 'ia-continueButton')]//child::span[contains(text(), 'Continue')]")
                        if indeed_app_continue:
                            cont_btn_xpath = "//button[contains(@class, 'ia-continueButton')]//child::span[contains(text(), 'Continue')]"
                            gonext_list.append("Continue")
                    except Exception:
                        try:
                            try:
                                indeed_app_continue = web.find_element(By.XPATH, "//div[contains(@class, 'Resume')]//descendant::span[contains(text(), 'Continue')]")
                                cont_btn_xpath = "//div[contains(@class, 'Resume')]//descendant::span[contains(text(), 'Continue')]"
                                gonext_list.append("Continue")
                            except Exception:
                                indeed_app_continue = web.find_element(By.XPATH, "//div[contains(@class, 'Resume')]//descendant::button/span[contains(text(), 'Continue')]")
                                cont_btn_xpath = "//div[contains(@class, 'Resume')]//descendant::button/span[contains(text(), 'Continue')]"
                                gonext_list.append("Continue")
                        except Exception:
                            try:
                                try:
                                    indeed_app_continue = web.find_element(By.XPATH, "//div[contains(@class, 'Questions')]//descendant::span[contains(text(), 'Continue')]")
                                    cont_btn_xpath = "//div[contains(@class, 'Questions')]//descendant::span[contains(text(), 'Continue')]"
                                    gonext_list.append("Continue")
                                except Exception:
                                    indeed_app_continue = web.find_element(By.XPATH, "//div[contains(@class, 'Questions')]//descendant::button/span[contains(text(), 'Continue')]")
                                    cont_btn_xpath = "//div[contains(@class, 'Questions')]//descendant::button/span[contains(text(), 'Continue')]"
                                    gonext_list.append("Continue")
                            except Exception:
                                nextcount+=1
        try:
            indeed_app_continue = web.find_element(By.XPATH, "//div/button/div[text()='Continue to application']")
            if indeed_app_continue:
                cont_btn_xpath = "//div/button/div[text()='Continue to application']"
                gonext_list.append("Continue")
        except Exception:
            try:
                indeed_app_continue = web.find_element(By.XPATH, "//button[contains(@class, 'ia-continueButton')]//child::span[contains(text(), 'Continue')]")
                if indeed_app_continue:
                    cont_btn_xpath = "//button[contains(@class, 'ia-continueButton')]//child::span[contains(text(), 'Continue')]"
                    gonext_list.append("Continue")
            except Exception:
                try:
                    indeed_app_continue = web.find_element(By.XPATH, "//button/div[text()='Continue to application']")
                    if indeed_app_continue:
                        cont_btn_xpath = "//button/div[text()='Continue to application']"
                        gonext_list.append("Continue")
                except Exception:
                    try:
                        indeed_app_continue = web.find_element(By.XPATH, "//div[contains(@class, 'BasePage-footer')]//descendant::button/span[contains(text(), 'Continue')]")
                        if indeed_app_continue:
                            cont_btn_xpath = "//div[contains(@class, 'BasePage-footer')]//descendant::button/span[contains(text(), 'Continue')]"
                            gonext_list.append("Continue")
                    except Exception:
                        try:
                            indeed_app_continue = web.find_element(By.XPATH, "//button[contains(text(), 'Continue applying')]")
                            if indeed_app_continue:
                                cont_btn_xpath = "//button[contains(text(), 'Continue applying')]"
                                gonext_list.append("Continue")
                        except Exception:
                            nextcount+=1
        try:
            indeed_app_review = web.find_element(By.XPATH, "//button/span[text()='Review your application']")
            if indeed_app_review:
                rev_btn_xpath = "//button/span[text()='Review your application']"
                gonext_list.append("Review")
        except Exception:
            try:
                indeed_app_review = web.find_element(By.XPATH, "//div/button/div[text()='Review your application']")
                if indeed_app_review:
                    rev_btn_xpath = "//div/button/div[text()='Review your application']"
                    gonext_list.append("Review")
            except Exception:
                try:
                    indeed_app_review = web.find_element(By.XPATH, "//button[contains(@class, 'ia-continueButton')]//child::span[contains(text(), 'Review')]")
                    if indeed_app_review:
                        rev_btn_xpath = "//button[contains(@class, 'ia-continueButton')]//child::span[contains(text(), 'Review')]"
                        gonext_list.append("Review")
                except Exception:
                    nextcount+=1
        try:
            indeed_app_submit = web.find_element(By.XPATH, "//button/span[text()='Submit your application']")
            if indeed_app_submit:
                sub_btn_xpath = "//button/span[text()='Submit your application']"
                gonext_list.append("Submit")
        except Exception:
            try:
                indeed_app_submit = web.find_element(By.XPATH, "//button[contains(@class, 'ia-continueButton')]//child::span[contains(text(), 'Submit')]")
                if indeed_app_submit:
                    sub_btn_xpath = "//button[contains(@class, 'ia-continueButton')]//child::span[contains(text(), 'Submit')]"
                    gonext_list.append("Submit")
            except Exception:
                try:
                    indeed_app_submit = web.find_element(By.XPATH, "//div/button/div[text()='Submit your application']")
                    if indeed_app_submit:
                        sub_btn_xpath = "//div/button/div[text()='Submit your application']"
                        gonext_list.append("Submit")
                except Exception:
                    try:
                        indeed_app_submit = web.find_element(By.XPATH, "//div[contains(@class, 'BasePage-footer')]//descendant::button/span[contains(text(), 'Submit your application')]")
                        if indeed_app_submit:
                            sub_btn_xpath = "//div[contains(@class, 'BasePage-footer')]//descendant::button/span[contains(text(), 'Submit your application')]"
                            gonext_list.append("Submit")
                    except Exception:
                        try:
                            indeed_app_submit = web.find_element(By.XPATH, "//div[contains(@class, 'Review')]//descendant::button/span[contains(text(), 'Submit your application')]")
                            if indeed_app_submit:
                                sub_btn_xpath = "//div[contains(@class, 'Review')]//descendant::button/span[contains(text(), 'Submit your application')]"
                                gonext_list.append("Submit")
                        except Exception:
                            nextcount+=1

        if "Continue" in gonext_list:
            try:
                indeed_app_continue.click()
                frontend_bot_msg("Navigating..")
            except ElementNotInteractableException as err:
                try:
                    Indeed_btn_fanhammer(cont_btn_xpath)
                except ElementNotInteractableException:
                    errlog(element="indeed_app_continue",description=err)
                    nextcount = 4
            except ElementClickInterceptedException as e:
                errlog(element="indeed_app_continue",description=e)
                cookiecheck()
                indeed_app_continue.click()
            try:
                WebDriverWait(web, 5).until(EC.visibility_of_element_located((By.XPATH, '//*[starts-with(@id, "q_")]//descendant::div[contains(@id, "error")]')))
                error_catchvar+=1
                if error_catchvar<=4:
                    Indeed_Qfill_error()
                    time.sleep(1)
                    indeed_GoNext()
                else:
                    web.close()
                    error_catchvar = 0
            except TimeoutException:
                error_catchvar = 0
                time.sleep(5)
                Indeed_ansfind()
        if "Review" in gonext_list:
            try:
                indeed_app_review.click()
                frontend_bot_msg("Reviewing..")
            except ElementNotInteractableException as err:
                try:
                    Indeed_btn_fanhammer(rev_btn_xpath)
                except ElementNotInteractableException:
                    errlog(element="indeed_app_review",description=err)
                    nextcount = 4
            except ElementClickInterceptedException as e:
                errlog(element="indeed_app_review",description=e)
                cookiecheck()
                indeed_app_review.click()
            try:
                WebDriverWait(web, 5).until(EC.visibility_of_element_located((By.XPATH, '//*[starts-with(@id, "q_")]//descendant::div[contains(@id, "error")]')))
                error_catchvar+=1
                if error_catchvar<=4:
                    Indeed_Qfill_error()
                    time.sleep(1)
                    indeed_GoNext()
                else:
                    web.close()
                    error_catchvar = 0
            except TimeoutException:
                error_catchvar = 0
                time.sleep(5)
                Indeed_ansfind()
        if "Submit" in gonext_list:
            if WE_ARE_SUBMITTING:
                try:
                    indeed_app_submit.click()
                    frontend_bot_msg("Submitting..")
                except ElementClickInterceptedException as e:
                    errlog(element="indeed_app_submit",description=e)
                    cookiecheck()
                    indeed_app_submit.click()
                except ElementNotInteractableException as e:
                    errlog(element="indeed_app_submit",description=e)
                    try:
                        cf_manual_solver(web)
                        captcha_checkbox_and_solve(web, error="error")
                    except Exception:
                        indeed_appform_capcha()
                    try:
                        indeed_app_submit.click()
                    except ElementNotInteractableException as err:
                        try:
                            Indeed_btn_fanhammer(sub_btn_xpath)
                        except ElementNotInteractableException:
                            errlog(element="indeed_app_submit",description=err)
                            nextcount = 4
                except Exception:
                    try:
                        cf_manual_solver(web)
                        captcha_checkbox_and_solve(web, error="error")
                    except Exception:
                        indeed_appform_capcha()
                    try:
                        indeed_app_submit.click()
                    except Exception as e:
                        errlog(element="indeed_app_submit capcha fail",description=e)
                        web.close()
                time.sleep(5)
            else:
                frontend_bot_msg("Application Successful!")
                web.close()
        if nextcount == 4:
            Indeed_Job_count += 5
            errlog(element="nextcount",log="nextcount = 4")
            # print("nextcount = 4")
            if WE_ARE_SUBMITTING:
                web.close()
            else:
                x = input("Test Failed in indeed_GoNext. Nextcount = 4. ENTER to close..")

    def Indeed_signin():
        global finalprint

        def message_window(msg="Indeed has sent a one-time passcode\nto your email...\nThis passcode will expire after 10 minutes"):

            def center_window(win):
                # make sure window is updated
                win.update()
                # get the screen resolution
                scr_width, scr_height = win.winfo_screenwidth(), win.winfo_screenheight()
                # get the window resolution
                border_width = win.winfo_rootx() - win.winfo_x()
                title_height = win.winfo_rooty() - win.winfo_y()
                win_width = win.winfo_width() + border_width + border_width
                win_height = win.winfo_height() + title_height + border_width
                # calculate the position
                x = (scr_width - win_width) // 2
                y = (scr_height - win_height) // 2
                # place the window at the calculated position
                win.geometry("+%d+%d" % (x, y))

            def handle_code():
                global final_code
                global submit

                try:
                    final_code = user_code.get()
                except Exception:
                    final_code == "22222222"

                submit = True

                try:
                    root.destroy()
                except Exception:
                    root.destroy()

            def resend_code():
                global retry

                try:
                    root.destroy()
                    frontend_top_msg("Resending..")
                    frontend_bot_msg("Stand By..")
                except Exception:
                    errlog(element="resend_code", log="Couldnt retry?")
                    root.destroy()

                retry = True

            def close_signout():
                try:
                    root.destroy()
                    frontend_top_msg("Indeed Sign-in Failed")
                    frontend_bot_msg("Could not validate login code.")
                    sys.exit()
                except Exception:
                    root.destroy()
                    sys.exit()

            root = Tk()
            root.geometry("300x200")
            root.resizable(False, False)
            center_window(root)
            root.title("Enter 6-Digit Code")
            root.protocol("WM_DELETE_WINDOW", close_signout)

            user_code = StringVar()

            message = Label(root, text=msg).place(relx=0.5, rely=0.18, anchor="center")

            code_entry = Entry(root, textvariable=user_code, width=30).place(relx=0.5, rely=0.5, anchor="center")
            Submit_button = Button(root, text="Submit", command=handle_code, width=13).place(relx=0.3, rely=0.82, anchor="center")
            Resend_button = Button(root, text="Resend", command=resend_code, width=13).place(relx=0.7, rely=0.82, anchor="center")

            root.mainloop()

        def submit_code(web, final_code):

            frontend_top_msg("Signing into Indeed")
            frontend_bot_msg(f"Entering {final_code}")

            passcode_input = web.find_element(By.ID, "passcode-input")
            bot_typer(passcode_input, final_code)
            time.sleep(1.759)

            try:
                indeed_logincode_submit = web.find_element(By.XPATH, "//button/span[text()='Sign in']") # unconfirmed
                indeed_logincode_submit.uc_click()
            except (ElementClickInterceptedException, ElementNotInteractableException):
                try:
                    web.find_element(By.ID, 'label-passcode-input-error')
                    frontend_top_msg("Indeed Sign-in Failed")
                    frontend_bot_msg("Code did not match or is no longer valid.")
                except Exception as e:
                    errlog(element="label-passcode-input-error", description=e, log="Couldnt submit and there was no wrong code error?")

        def click_resend_btn(web):
            try:
                send_new_code = web.find_element(By.XPATH, "//button[@type='button']//child::span[contains(text(), 'Send new code')]")
                send_new_code.uc_click()
                time.sleep(1)
                frontend_top_msg("Code Sent..")
                frontend_bot_msg("Please Check Your Email.")
                try:
                    message_window(msg="Code resent!\nCode may take up to five minutes\nto arrive if service is slow")
                except Exception as e:
                    errlog(element='message_window resend', description=e)
            except Exception as e:
                errlog(element="send_new_code", log="Couldnt get new code?", description=e)

        def get_code_from_user(web):
            global resend_tries
            global retry
            global submit

            message_window()

            if retry == True and resend_tries == 3:
                resend_tries = resend_tries - 1
                retry = False
                click_resend_btn(web)
                message_window(msg=f"Code resent!\nCode may take up to five minutes\nto arrive if service is slow\nRetries left {str(resend_tries)}")
            elif submit == True:
                submit = False
                submit_code(web, final_code)

            if retry == True and resend_tries == 2:
                resend_tries = resend_tries - 1
                retry = False
                click_resend_btn(web)
                message_window(msg=f"Code resent!\nCode may take up to five minutes\nto arrive if service is slow\nRetries left {str(resend_tries)}")
            elif submit == True:
                submit = False
                submit_code(web, final_code)

            if retry == True and resend_tries == 1:
                resend_tries = resend_tries - 1
                retry = False
                click_resend_btn(web)
                message_window(msg=f"Code resent!\nCode may take up to five minutes\nto arrive if service is slow\nRetries left {str(resend_tries)}")
            elif submit == True:
                submit = False
                submit_code(web, final_code)

            if retry == True and resend_tries <= 0:
                print("WE GAVE UP")
            elif submit == True:
                submit = False
                submit_code(web, final_code)

        def login_code_check():

            try:
                logincode_h1 = web.find_element(By.XPATH, '//h1[contains(text(), "in with login code")]')
            except Exception:
                return

            try:
                anotherway_link = web.find_element(By.LINK_TEXT, 'Sign in another way')
            except Exception:
                try:
                    anotherway_link = web.find_element(By.XPATH, '//a[contains(text(), "Sign in another way")]')
                except Exception as e:
                    errlog(element='anotherway_link', description=e, log='find example of this scrn in test email')
                    return

            anotherway_link.uc_click()
            time.sleep(2)

        frontend_bot_msg("Signing into Indeed")
        indeed_login_success_bool = False  # People can have google accounts that dont end with gmail.com

        try:
            acct_menu_btn = WebDriverWait(web, 3).until(EC.presence_of_element_located((By.ID, 'AccountMenu'))) # Only visible if signed in
            frontend_bot_msg("Successfully signed in")
            What_Where()
            return
        except Exception:
            pass

        try: # Need a better way of figuring out if logged in - refer to acct_menu_btn if stops working
            SignB = WebDriverWait(web, 10).until(EC.presence_of_element_located((By.LINK_TEXT, "Sign in")))
            if SignB:
                SignBtn = web.find_element(By.LINK_TEXT, "Sign in")
                SignBtn.uc_click()
                time.sleep(5.77)
        except TimeoutException:
            frontend_bot_msg("Successfully signed in")
            What_Where()
            return

        try:
            frontend_top_msg("Signing into Indeed")
            frontend_bot_msg("Entering Email")
            indeed_email = web.find_element(By.XPATH, "//input[@type='email']")
            bot_typer(indeed_email, profile_dict['indeed_user'])  # ---Email input here
            time.sleep(2)
            indeed_email_submit = web.find_element(By.XPATH, "//button[@type='submit']//child::span[contains(text(), 'Continue')]")
            indeed_email_submit.uc_click()
            time.sleep(3.34)
            login_code_check()

            try:
                wrong_email = web.find_element(By.XPATH, '//span[contains(text(), "Create an account")]')
                finalprint = "Indeed invalid Email"
                frontend_top_msg('Indeed sign-in failed')
                frontend_bot_msg("Indeed invalid email")
                errlog(element="wrong_email", log="Indeed wrong Email")
                return
            except Exception:
                pass

        except NoSuchElementException as e:
            errlog(element="indeed_email or submit", description=e)
            frontend_top_msg('Indeed sign-in failed')
            frontend_bot_msg("Indeed connection failure.")
            return

        try:
            logincode = web.find_element(By.XPATH, "//h1[contains(text(), 'Sign in with login code')]")
            final_code = ''
            frontend_top_msg("Please Enter Login Code")
            frontend_bot_msg("Sent to your email")

            get_code_from_user(web)
            time.sleep(2)
        except Exception:
            pass

        try:
            WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, "//input[@type='password']")))
            indeed_password = web.find_element(By.XPATH, "//input[@type='password']")
            frontend_bot_msg("Entering Password")
            bot_typer(indeed_password, profile_dict['indeed_pass'])
            time.sleep(2)
            indeed_password_submit = web.find_element(By.XPATH, "//button[@type='submit']//child::span[text()='Sign in']")
            indeed_password_submit.uc_click()
            frontend_bot_msg("Navigating")
            time.sleep(3)
        except Exception:
            try:
                gsuite_btn = web.find_element(By.ID, "gsuite-login-google-button")
                Indeed_Google(web)
                check_if_captcha_redirect(web)
            except Exception as e:
                errlog(element="gsuite_btn or indeed_password", description=e)

        try:
            WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, "//input[@type='password']")))
            indeed_password = web.find_element(By.XPATH, "//input[@type='password']")
            check_if_captcha_redirect(web)

            time.sleep(1)
            frontend_bot_msg("Entering Password")
            bot_typer(indeed_password, profile_dict['indeed_pass'])
            time.sleep(2)
            try:
                indeed_password_submit = web.find_element(By.XPATH,
                                                          "//button[@type='submit']//child::span[text()='Sign in']")
                indeed_password_submit.uc_click()
                frontend_bot_msg("Navigating")
            except Exception as e:
                errlog(element='indeed_password_submit', description=e, log='captcha verification password button might be different.')

            time.sleep(3)

            try:
                looking_for_wrong_pw = web.find_element(By.XPATH, '/html/body').text
                if "Incorrect password" in looking_for_wrong_pw:
                    frontend_top_msg('Indeed sign-in failed')
                    frontend_bot_msg("Indeed invalid password")
                    errlog(element="wrong_password", log="Indeed wrong password")
                    return
            except Exception:
                pass
        except Exception:
            pass

        try:
            verify_phone_h3 = web.find_element(By.XPATH, "//h2[contains(text(), 'Verify your phone number')]")
            try:
                not_now_btn = web.find_element(By.XPATH, "//a[contains(@id, 'CancelLink')]")
                not_now_btn.uc_click()
                time.sleep(5)
            except Exception as e:
                errlog(element="not_now_btn", description=e)
        except Exception:
            pass

        try:
            acct_menu_btn = WebDriverWait(web, 10).until(EC.presence_of_element_located((By.ID, 'AccountMenu'))) # Only visible if signed in
        except Exception as e:
            frontend_bot_msg('Indeed Sign in failed')
            errlog(element='acct_menu_btn', description=e, log='Indeed Sign in failed')
            return

        frontend_bot_msg("Successfully signed in")
        What_Where()

    def What_Where(x=None, home=True):#---------------inputs here***

        if home:
            try:
                indeed_home = web.find_element(By.LINK_TEXT, 'Home')
                indeed_home.uc_click()
                time.sleep(3)
                frontend_bot_msg("Scanning Indeed")
            except Exception as e:
                errlog(element="indeed_home",description=e)

        try:
            where_S = WebDriverWait(web,10).until(EC.presence_of_element_located((By.ID, "text-input-where")))
            where_select = web.find_element(By.ID, "text-input-where")

            if profile_dict["job_remote"]==True:
                bot_typer(where_select,"remote")
            else:
                bot_typer(where_select,profile_dict['job_city'])

            time.sleep(5.98)
            frontend_bot_msg("Scanning Indeed.")
        except (NoSuchElementException, TimeoutException) as e:
            errlog(element="where_S",description=e)

        try:
            what_select = web.find_element(By.ID, "text-input-what")

            # Quotes are disabled until we can effectively bypass captchas
            # if not x:
            #     bot_typer_str = '"' + profile_dict['job_title'] + '"'
            #     bot_typer(what_select, bot_typer_str)
            # else:
            #     bot_typer(what_select, profile_dict['job_title'])

            bot_typer(what_select, profile_dict['job_title'])

            time.sleep(4.12)
            frontend_bot_msg("Scanning Indeed..")
            search_btn = web.find_element(By.XPATH, "//button[@type='submit' and text()='Search']")
            search_btn.uc_click()
            time.sleep(5)
            try:
                set_last_run()
            except Exception:
                pass
            try:
                cap_check_timeout = 0
                check_if_captcha_redirect(web)
                time.sleep(3)
                captcha_still_there_check(web, cap_check_timeout)
            except Exception as e:
                if not WE_ARE_SUBMITTING:
                    errlog(element="cap_check_timeout",description=e)
            frontend_bot_msg("Scanning Indeed...")
        except NoSuchElementException as e:
            errlog(element="what_select?",description=e)

        if not x:
            try:
                distfilter = WebDriverWait(web,10).until(EC.element_to_be_clickable((By.XPATH, '//button[@id="filter-radius"]')))
                if distfilter:
                    distancefilter3 = web.find_element(By.XPATH, '//button[@id="filter-radius"]')
                    distancefilter3.uc_click()
                    time.sleep(1)
                    fiftymilesb = web.find_element(By.XPATH, '//ul[@id="filter-radius-menu"]/li/a[contains(text(), "Within 50 miles")]')
                    fiftymilesb.uc_click()
                    time.sleep(2)
            except TimeoutException:
                pass

    def Indeed_ansfind():

        def indeed_resume():
            global finalprint

            def resume_save_check():

                try:
                    resume_save_h2 = web.find_element(By.XPATH, '//h2[contains(text(), "Let other employers find you")]')
                except Exception:
                    time.sleep(0.77)
                    return

                try:
                    resume_save = web.find_element(By.XPATH, '//button[@data-testid="ResumePrivacyModal-SaveBtn"]')
                except Exception:
                    try:
                        resume_save = web.find_element(By.XPATH, '//button/span[text()="Save"]')
                    except Exception:
                        try:
                            resume_save = web.find_element(By.XPATH, '//button[contains(text(), "Save")]')
                        except Exception as e:
                            errlog(element='resume_save', description=e, log='triggered when uploading a new resume')

                try:
                    time.sleep(1)
                    resume_save.click()
                except Exception:
                    try:
                        resume_save_closebtn = web.find_element(By.XPATH, '//button[@aria-label="Close"]')
                        resume_save_closebtn.click()
                    except Exception as e:
                        errlog(element='resume_save_closebtn', description=e, log='resume_save_check failed to find all elements')

                time.sleep(2.567)

            if not os.path.exists(profile_dict['resume_path']):
                errlog(element="profile_dict['resume_path']", description='FileNotFoundError', log='Could not find the resume to upload. Check current working directory/profile_dict for potential answer')
                finalprint = 'Resume not found..'
                frontend_bot_msg(finalprint)
                sys.exit()

            try:
                resume_target2 = web.find_element(By.XPATH, '//div[@data-testid="FileResumeCard"]')
            except NoSuchElementException:
                try:
                    resume_target2 = web.find_element(By.XPATH, '//*[@role="radio" and not(contains(text(), "Build an Indeed Resume"))]')
                except NoSuchElementException as e:
                    errlog(element='resume_target2', description=e, log="Indeed updated resume flow scrn")
                    frontend_bot_msg(finalprint)
                    sys.exit()
            if "Upload resume" in resume_target2.text:
                try:
                    uploadRes = web.find_element(By.XPATH, "//input[@type='file']")
                    uploadRes.send_keys(choice_resumepath)
                    time.sleep(1)
                    resume_save_check()
                    confirm_window_handle(web)
                except Exception as e:
                    errlog(element='indeed uploadRes', description=e, log='resume_target2 found but could not upload')
                    frontend_bot_msg(finalprint)
                    sys.exit()
                frontend_bot_msg("Adding resume...")
                time.sleep(1)
            else:
                if profile_dict['resume_file'] not in resume_target2.text:
                    try:
                        resume_input = web.find_element(By.XPATH, '//input[@type="file"]')
                        resume_input.send_keys(profile_dict['resume_path'])
                        time.sleep(1)
                        resume_save_check()
                        confirm_window_handle(web)
                    except Exception as e:
                        errlog(element='resume_input', description=e, log='resume_input found but could not upload')
                        frontend_bot_msg(finalprint)
                        sys.exit()
                else:
                    resume_target2.click()
                    confirm_window_handle(web)
                frontend_bot_msg("Adding resume...")
                time.sleep(2)

        global gonext_Var
        global finalprint
        gonext_Var = 0
        app_ejector = 0

        what_page_do_i_see = []

        confirm_window_handle(web)

        try:
            emp_looking = web.find_element(By.XPATH, "//h1[text()='The employer is looking for these qualifications']")
            what_page_do_i_see.append('emp_looking')
        except Exception:
            pass

        try:
            covertext = web.find_element(By.XPATH, "//h1[text()='The employer requests a cover letter for this application']")
            what_page_do_i_see.append('covertext')
        except Exception:
            pass

        try:
            commute_query = web.find_element(By.XPATH, "//h1[text()='Does this commute work for you?']")
            what_page_do_i_see.append('commute_query')
        except Exception:
            pass

        try:
            resume_target1 = web.find_element(By.XPATH, '//*[contains(text(), "Add a resume for the employer")]')
            what_page_do_i_see.append('resume_target1')
        except Exception:
            pass

        try:
            quals_query = web.find_element(By.XPATH, "//h1[contains(text(), 'Do you have any of these qualifications?')]")
            what_page_do_i_see.append('quals_query')
        except Exception:
            pass

        try:
            try:
                employer_questions = web.find_element(By.XPATH, "//h1[text()='Questions from the employer']")
            except NoSuchElementException:
                try:
                    employer_questions = web.find_element(By.XPATH, "//h1[contains(text(), 'questions from the employer')]")
                except NoSuchElementException:
                    employer_questions = web.find_element(By.XPATH, "//h1[contains(text(), 'Review these qualifications found in the job post')]")

            what_page_do_i_see.append('employer_questions')
        except Exception:
            pass

        try:
            jobexp_skip = web.find_element(By.XPATH, "//*[contains(text(), 'Enter a job that shows relevant experience')]")
            what_page_do_i_see.append('jobexp_skip')
        except Exception:
            pass

        try:
            consider = web.find_element(By.XPATH, "//h1[text()='Consider adding supporting documents']")  # try to find cover letter if so do it if not click review
            what_page_do_i_see.append('consider')
        except Exception:
            pass

        try:
            finalscrn1 = web.find_element(By.XPATH, "//h1[text()='Please review your application']")
            what_page_do_i_see.append('finalscrn1')
        except Exception:
            pass

        try:
            contactscrn = web.find_element(By.XPATH, "//h1[text()='Add your contact information']")
            what_page_do_i_see.append('contactscrn')
        except Exception:
            pass

        try:
            location_details = web.find_element(By.XPATH, "//h1[text()='Review your location details from your profile']")
            what_page_do_i_see.append('location_details')
        except Exception:
            pass

        if len(what_page_do_i_see) == 0:

            try:
                WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, "//h1[text()='The employer is looking for these qualifications']")))
                what_page_do_i_see.append('emp_looking')
            except Exception:
                app_ejector += 1

            try:
                WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, "//h1[text()='The employer requests a cover letter for this application']")))
                what_page_do_i_see.append('covertext')
            except Exception:
                app_ejector += 1

            try:
                WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, "//h1[text()='Does this commute work for you?']")))
                what_page_do_i_see.append('commute_query')
            except Exception:
                app_ejector += 1

            try:
                WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, '//*[contains(text(), "Add a resume for the employer")]')))
                what_page_do_i_see.append('resume_target1')
            except Exception:
                app_ejector += 1

            try:
                WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, "//h1[contains(text(), 'Do you have any of these qualifications?')]")))
                what_page_do_i_see.append('quals_query')
            except Exception:
                app_ejector += 1

            try:
                try:
                    WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, "//h1[text()='Questions from the employer']")))
                except TimeoutException:
                    try:
                        WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, "//h1[contains(text(), 'questions from the employer')]")))
                    except TimeoutException:
                        WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, "//h1[contains(text(), 'Review these qualifications found in the job post')]")))

                what_page_do_i_see.append('employer_questions')
            except Exception:
                app_ejector += 1

            try:
                WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, "//*[contains(text(), 'Enter a job that shows relevant experience')]")))
                what_page_do_i_see.append('jobexp_skip')
            except Exception:
                app_ejector += 1

            try:
                WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, "//h1[text()='Consider adding supporting documents']")))
                what_page_do_i_see.append('consider')
            except Exception:
                app_ejector += 1

            try:
                WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, "//h1[text()='Please review your application']")))
                what_page_do_i_see.append('finalscrn1')
            except Exception:
                app_ejector += 1

            try:
                WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, "//h1[text()='Add your contact information']")))
                what_page_do_i_see.append('contactscrn')
            except Exception:
                app_ejector += 1

            try:
                WebDriverWait(web, 3).until(EC.visibility_of_element_located((By.XPATH, "//h1[text()='Review your location details from your profile']")))
                what_page_do_i_see.append('location_details')
            except Exception:
                app_ejector += 1

        if 'emp_looking' in what_page_do_i_see: # app_ejector only increments upon NoSuchElementException or if function that includes a found element fails. Since this element only triggers a navigation app_ejector is omitted.
            gonext_Var += 1

        if 'covertext' in what_page_do_i_see:
            try:
                covertext = web.find_element(By.XPATH, "//h1[text()='The employer requests a cover letter for this application']")
                coverradio = web.find_elements(By.XPATH, "//*[@role='radio']")
                coverradio[0].click()
                time.sleep(1)
                cover_letter_target = web.find_element(By.XPATH, "//textarea")
                frontend_bot_msg("Crafting cover letter...")
                bot_typer(cover_letter_target, indeed_cover_letter)
                time.sleep(1)
                gonext_Var += 1
            except Exception as e:
                errlog(element='covertext', description=e, log='covertext scrn detected but something went wrong.')
                app_ejector += 11

        if 'commute_query' in what_page_do_i_see:
            gonext_Var += 1

        if 'resume_target1' in what_page_do_i_see:
            try:
                resume_target1 = web.find_element(By.XPATH, '//*[contains(text(), "Add a resume for the employer")]')
                indeed_resume()
                gonext_Var += 1
            except NoSuchElementException:
                errlog(element='resume_target1', description=e, log='resume_target1 scrn detected but something went wrong.')
                app_ejector += 11

        if 'quals_query' in what_page_do_i_see:
            try:
                quals_query = web.find_element(By.XPATH, "//h1[contains(text(), 'Do you have any of these qualifications?')]")
                qualifications = web.find_elements(By.TAG_NAME, "fieldset")
                for qual in qualifications:
                    try:
                        qual_bubble = qual.find_element(By.XPATH, './/input//following-sibling::span')
                        qual_bubble.click()
                        time.sleep(1)
                    except Exception as e:
                        errlog(element='qual_bubble', description=e, log='history of being a flimsy element')
                gonext_Var += 1
            except Exception:
                errlog(element='quals_query', description=e, log='quals_query scrn detected but something went wrong.')
                app_ejector += 11

        if 'employer_questions' in what_page_do_i_see:
            try:
                Indeed_formfill()
                gonext_Var += 1
            except Exception as e:
                errlog(element='Indeed_formfill', description=e, log='employer_questions scrn detected but something went wrong.')
                app_ejector += 11

        if 'jobexp_skip' in what_page_do_i_see:
            try:
                jobexp_skip = web.find_element(By.XPATH, "//*[contains(text(), 'Enter a job that shows relevant experience')]")

                try:
                    job_title = web.find_element(By.ID, 'jobTitle')
                    if profile_dict['previous_work_job_title'] == 'none' or profile_dict['previous_work_job_title'] is None:
                        pass
                    else:
                        bot_typer(job_title, profile_dict['previous_work_job_title'])
                except Exception as e:
                    errlog(element='job_title', description=e)

                time.sleep(1.24)

                try:
                    company_Name = web.find_element(By.ID, 'companyName')
                    if profile_dict['previous_work_company'] == 'none' or profile_dict['previous_work_company'] is None:
                        pass
                    else:
                        bot_typer(company_Name, profile_dict['previous_work_company'])
                except Exception as e:
                    errlog(element='company_Name', description=e)

                gonext_Var += 1
            except Exception as e:
                errlog(element='jobexp_skip', description=e, log='jobexp_skip scrn detected but something went wrong.')
                app_ejector += 11

        if 'consider' in what_page_do_i_see:
            try:
                consider = web.find_element(By.XPATH, "//h1[text()='Consider adding supporting documents']")  # try to find cover letter if so do it if not click review
                cover_radio = web.find_element(By.XPATH, "//*[contains(text(),'Write cover letter')]")
                cover_radio.click()
                time.sleep(2)
                cover_letter_target2 = web.find_element(By.XPATH, "//textarea")
                frontend_bot_msg("Crafting cover letter...")
                bot_typer(cover_letter_target2, indeed_cover_letter)
                time.sleep(1)
                gonext_Var += 1
            except Exception:
                errlog(element='consider', description=e, log='consider scrn detected but something went wrong.')
                app_ejector += 11

        if 'finalscrn1' in what_page_do_i_see:
            gonext_Var += 1

        if 'contactscrn' in what_page_do_i_see:
            try:
                contactscrn = web.find_element(By.XPATH, "//h1[text()='Add your contact information']")
                frontend_bot_msg("Adding contact information...")
                fnameinput = web.find_element(By.NAME, 'firstName')
                bot_typer(fnameinput, profile_dict['first_name'])
                time.sleep(1)
                lnameinput = web.find_element(By.NAME, 'lastName')
                bot_typer(lnameinput, profile_dict['last_name'])
                time.sleep(1)
                phonecountry_sel = web.find_element(By.XPATH, '//select[@name="phoneNumberCountry"]')
                if phonecountry_sel.get_attribute("value") != "US":
                    phonecountry_sel = Select(web.find_element(By.XPATH, '//select[@name="phoneNumberCountry"]'))
                    phonecountry_sel.select_by_visible_text("United States (+1)")
                    time.sleep(1)
                else:
                    pass
                phoneinput = web.find_element(By.XPATH, '//input[@name="phoneNumber" and @type="tel"]')
                bot_typer(phoneinput, profile_dict['personal_phone'])
                time.sleep(2)
                gonext_Var += 1
            except Exception:
                errlog(element='contactscrn', description=e, log='contactscrn detected but something went wrong.')
                app_ejector += 11

        if 'location_details' in what_page_do_i_see:
            try:  # This block is split from contactscrn bc these are optional. A profile that is filled out will never see this screen
                location_details = web.find_element(By.XPATH, "//h1[text()='Review your location details from your profile']")
                try:
                    street_adress = web.find_element(By.NAME, 'addressLine')
                    frontend_bot_msg("Adding address...")
                    bot_typer(street_adress, profile_dict['personal_address'])
                    time.sleep(1)
                except Exception:
                    pass
                try:
                    loc_postal = web.find_element(By.NAME, 'postalCode')
                    frontend_bot_msg("Adding zip code...")
                    bot_typer(loc_postal, profile_dict['personal_zip'])
                    time.sleep(1)
                except Exception:
                    pass
                try:
                    loc_city = web.find_element(By.NAME, 'city')
                    frontend_bot_msg("Adding city...")
                    bot_typer(loc_city, profile_dict['job_city'])
                    time.sleep(1)
                except Exception:
                    pass
                gonext_Var += 1
            except Exception:
                errlog(element='location_details', description=e, log='location_details detected but something went wrong.')
                app_ejector += 11

        # print("gonext_Var =",str(gonext_Var))
        # print("app_ejector =",str(app_ejector))

        if gonext_Var > 0:
            time.sleep(1)
            indeed_GoNext()
        elif app_ejector >= 11:
            errlog(element="app_ejector", log=f"app_ejector >= 11 value = {str(app_ejector)}")
            if WE_ARE_SUBMITTING:
                web.close()
            else:
                print("app_ejector = 10")
                x = input("Test failed. Press ENTER to exit..")

    def Indeed_formfill(): # finds the answer type within the question group.
        #print("Indeed_formfill called")

        default_answerbank = ["I Don't Wish To Answer","Decline to Answer","I decline to say","I choose not to provide my gender","I decline to identify","I prefer not","I Don\'t Wish","Prefer not to answer","I prefer not to specify","Decline To Self Identify","Decline to Self Identify","I don't wish to answer","I DO NOT WISH TO IDENTIFY AT THIS TIME","Wish To Answer","I do not want to answer.","I do not wish to disclose","I Do Not Wish to Disclose","I do not want to answer","I choose not to provide race information."]

        def default_skin(i):
            #print("default_skin called")
            the_id = i.get_attribute("id")

            try:
                answer = web.find_element(By.XPATH, "//*[@id='{}']//input".format(the_id))
            except Exception:
                try:
                    answer = web.find_element(By.XPATH, "//*[@id='{}']//textarea".format(the_id))
                except Exception:
                    try:
                        answer = web.find_element(By.XPATH, "//*[@id='{}']//select".format(the_id))
                    except Exception:
                        try:
                            answer = i.find_element(By.XPATH, ".//input")
                        except Exception:
                            try:
                                answer = i.find_element(By.XPATH, ".//textarea")
                            except Exception:
                                try:
                                    answer = i.find_element(By.XPATH, ".//select")
                                except Exception:
                                    pass

            answer_type = answer.get_attribute("type")

            # QUESTION LOGGING
            try:
                search_string = i.text
                send_question_post(str(answer_type), str(search_string), 'Indeed')
            except Exception as e:
                repeatQ = "Likely Repeat Question", str(e)
                errlog(severity=50, element="Indeed_LOGGING", description=repeatQ, log=str(search_string))

            if answer_type == "text":
                bot_typer(answer,"Happy to answer all questions in an interview :)")

            if answer_type == "radio":
                valueR_ejector = 0

                for x in default_answerbank:
                    try:
                        cum = web.find_element(By.XPATH, '//*[starts-with(@id, "{}")]//span[contains(text(), \"{}\")]'.format(the_id,x))
                        cumbtn = web.find_element(By.XPATH, '//*[starts-with(@id, "{}")]//span[contains(text(), \"{}\")]//preceding-sibling::input'.format(the_id,x))
                        if cumbtn.is_selected()==False:
                            cum.click()
                        break
                    except Exception:
                        try:
                            cum = i.find_element(By.XPATH, './/span[contains(text(), \"{}\")]'.format(x))
                            cumbtn = i.find_element(By.XPATH, './/span[contains(text(), \"{}\")]//preceding-sibling::input'.format(x))
                            if cumbtn.is_selected()==False:
                                cum.click()
                            break
                        except Exception:
                            valueR_ejector+=1
                            continue

                if valueR_ejector == len(default_answerbank):
                    try:
                        rad = web.find_elements(By.XPATH, "//*[starts-with(@id, '{}')]//label".format(the_id))
                        rad[0].click()
                    except Exception:
                        try:
                            rad2 = i.find_elements(By.XPATH, ".//label")
                            rad2[0].click()
                        except Exception as e:
                            errlog(element="rad2",description=e)
                    time.sleep(1)

            if answer_type == "textarea":
                bot_typer(answer,"Happy to answer all questions in an interview :)")

            if answer_type == "number":
                bot_typer(answer,"8")

            if answer_type == "checkbox":
                try:
                    rad3 = web.find_element(By.XPATH, '//div[@id="{}"]//child::input'.format(the_id))
                    if rad3.is_selected() == True:
                        pass
                    if rad3.is_selected() == False:
                        rad3 = web.find_element(By.XPATH, '//div[@id="{}"]//child::input//following-sibling::span[string-length(.)>1]'.format(the_id))
                        rad3.click()
                except Exception:
                    try:
                        rad3 = i.find_element(By.XPATH, './/input')
                        if rad3.is_selected() == True:
                            pass
                        if rad3.is_selected() == False:
                            rad3 = web.find_element(By.XPATH, './/input//following-sibling::span[string-length(.)>1]')
                            rad3.click()
                    except Exception as e:
                        errlog(element="rad3",description=e)

            if answer_type == "select-one":
                valueS_ejector = 0

                dropdown = Select(answer)

                for x in default_answerbank:
                    try:
                        dropdown.select_by_visible_text(x)
                        break
                    except Exception:
                        valueS_ejector+=1
                        continue

                if valueS_ejector == len(default_answerbank):
                    dropdown.select_by_index(1)

            if answer_type == "date":
                try:
                    datetype = web.find_element(By.XPATH, "//*[starts-with(@id, '{}')]//input".format(the_id))
                    datetype.send_keys(todaysdate)
                except Exception:
                    try:
                        datetype = i.find_element(By.XPATH, ".//input")
                        datetype.send_keys(todaysdate)
                    except Exception as e:
                        errlog(element="datetype",description=e)

            if answer_type == "tel":
                bot_typer(answer,profile_dict['personal_phone'])

        def IndeedQfill_select(i):
            #("IndeedQfill_select called")
            sel_ans_cons = {}
            defaultejecter = 0
            iterator_text = i.text
            for key,value in indeed_select_check.items():
                if key.lower() in iterator_text.lower() and "(optional)" not in iterator_text.lower():
                    sel_ans_cons.update(key=value)
                    break
                if key.lower() in iterator_text.lower() and key in indeed_skip_check.keys():
                    sel_ans_cons.update(key="skip")
                    break
            if len(sel_ans_cons)>0:
                first_val = list(sel_ans_cons.values())[0]
                if first_val != "skip":
                    try:
                        answer = Select(i.find_element(By.XPATH, "//*[@id='{}']//select".format(the_id)))
                        answer.select_by_visible_text(first_val)
                        time.sleep(1)
                    except Exception:
                        try:
                            answer = Select(i.find_element(By.XPATH, ".//select"))
                            answer.select_by_visible_text(first_val)
                            time.sleep(1)
                        except Exception:
                            defaultejecter +=1
            if len(sel_ans_cons) == 0 or defaultejecter == 1:
                #print("IndeedQfill_select FAILED")
                #print(iterator_text)
                default_skin(i)
                time.sleep(1)

        def IndeedQfill_number(i):
            #print("IndeedQfill_number called")
            num_ans_cons = {}
            defaultejecter = 0
            iterator_text = i.text
            for key,value in indeed_number_check.items():
                if key.lower() in iterator_text.lower() and "(optional)" not in iterator_text.lower():
                    num_ans_cons.update(key=value)
                    break
                if key.lower() in iterator_text.lower() and key in indeed_skip_check.keys():
                    num_ans_cons.update(key="skip")
                    break
            if len(num_ans_cons)>0:
                first_val = list(num_ans_cons.values())[0]
                if first_val != "skip":
                    try:
                        bot_typer(answer,first_val)
                        time.sleep(1)
                    except Exception:
                        defaultejecter +=1
            if len(num_ans_cons) == 0 or defaultejecter == 1:
                #print("IndeedQfill_number FAILED")
                #print(iterator_text)
                default_skin(i)
                time.sleep(1)

        def IndeedQfill_chkbox(i, question_id=None, fieldparent=None):#find question group element. split total string by \n to find question at first index. use that with relative locator + string matching to find answers.Split dict values by "," for multi answer.
            #print("IndeedQfill_chkbox called")
            chkbox_ans_cons = {}
            defaultejecter = 0
            if fieldparent is None:
                iterator_text = i.text
            elif fieldparent is not None:
                iterator_text = fieldparent.text
            for key,value in indeed_checkbox_check.items():
                if key.lower() in iterator_text.lower() and "(optional)" not in iterator_text.lower():
                    chkbox_ans_cons.update(key=value)
                    break
                if key.lower() in iterator_text.lower() and key in indeed_skip_check.keys():
                    chkbox_ans_cons.update(key="skip")
                    break
            if len(chkbox_ans_cons)>0:
                first_val = list(chkbox_ans_cons.values())[0]
                if first_val != "skip":
                    valueslist = first_val.split(",")
                    try:
                        boxchecker = 0
                        for o in valueslist:
                            try:
                                try:
                                    cum = web.find_element(By.XPATH, '//div[@id="{}"]//child::input//following-sibling::span[contains(text(), \"{}\")]'.format(the_id,o))
                                    cuminput = web.find_element(By.XPATH, '//div[@id="{}"]//child::span[contains(text(), \"{}\")]//preceding-sibling::input'.format(the_id,o))
                                    if cuminput.is_selected()==0:
                                        cum.click()
                                        if question_id is not None:
                                            if question_id not in Quest_id_list:
                                                Quest_id_list.append(question_id)
                                    else:
                                        pass
                                    time.sleep(0.5)
                                except Exception:
                                    cum = i.find_element(By.XPATH, './/input//following-sibling::span[contains(text(), \"{}\")]'.format(o))
                                    cuminput = i.find_element(By.XPATH, './/span[contains(text(), \"{}\")]//preceding-sibling::input'.format(o))
                                    if cuminput.is_selected()==0:
                                        cum.click()
                                    else:
                                        pass
                                    time.sleep(0.5)
                            except Exception:
                                boxchecker+=1
                                continue
                        if boxchecker == len(valueslist):
                            defaultejecter+=1
                        time.sleep(1)
                    except Exception:
                        defaultejecter +=1
            if len(chkbox_ans_cons) == 0 or defaultejecter == 1:
                #print("IndeedQfill_chkbox FAILED")
                #print(iterator_text)
                if fieldparent is None:
                    default_skin(i)
                elif fieldparent is not None:
                    try:
                        default_skin(fieldparent)
                    except Exception:
                        default_skin(i)
                time.sleep(1)

        def IndeedQfill_date(i):
            #print("IndeedQfill_date called")
            radio_ans_cons = {}
            defaultejecter = 0
            iterator_text = i.text
            for key,value in indeed_date_check.items():
                if key.lower() in iterator_text.lower() and "(optional)" not in iterator_text.lower():
                    radio_ans_cons.update(key=value)
                    break
                if key.lower() in iterator_text.lower() and key in indeed_skip_check.keys():
                    radio_ans_cons.update(key="skip")
                    break
            if len(radio_ans_cons)>0:
                first_val = list(radio_ans_cons.values())[0]
                if first_val != "skip":
                    try:
                        datetype = web.find_element(By.XPATH, "//*[starts-with(@id, '{}')]//input".format(the_id))
                        datetype.send_keys(first_val)
                        time.sleep(1)
                    except Exception:
                        try:
                            datetype = i.find_element(By.XPATH, ".//input")
                        except Exception:
                            defaultejecter +=1
            if len(radio_ans_cons) == 0 or defaultejecter == 1:
                #print("IndeedQfill_date FAILED")
                #print(iterator_text)
                default_skin(i)
                time.sleep(1)

        def IndeedQfill_radio(i, question_id=None, fieldparent=None):#find question group element. split total string by \n to find question at first index. use that with relative locator + string matching to find answer bubble. currently clicks on the label might have to offset with actionchains later if stops working.
            #print("IndeedQfill_radio called")
            radio_ans_cons = {}
            defaultejecter = 0
            if fieldparent is None:
                iterator_text = i.text
            elif fieldparent is not None:
                iterator_text = fieldparent.text
            for key,value in indeed_radio_check.items():
                if key.lower() in iterator_text.lower() and "(optional)" not in iterator_text.lower():
                    radio_ans_cons.update(key=value)
                    break
                if key.lower() in iterator_text.lower() and key in indeed_skip_check.keys():
                    radio_ans_cons.update(key="skip")
                    break
            if len(radio_ans_cons)>0:
                first_val = list(radio_ans_cons.values())[0]
                if first_val != "skip":
                    try:
                        cum = web.find_element(By.XPATH, '//*[starts-with(@id, "{}")]//span[contains(text(), \"{}\")]'.format(the_id,first_val))
                        cumbtn = web.find_element(By.XPATH, '//*[starts-with(@id, "{}")]//span[contains(text(), \"{}\")]//preceding-sibling::input'.format(the_id,first_val))
                        if cumbtn.is_selected()==False:
                            cum.click()
                            if question_id is not None:
                                if question_id not in Quest_id_list:
                                    Quest_id_list.append(question_id)
                        time.sleep(1)
                    except Exception:
                        try:
                            cum = i.find_element(By.XPATH, './/span[contains(text(), \"{}\")]'.format(first_val))
                            cumbtn = i.find_element(By.XPATH, './/span[contains(text(), \"{}\")]//preceding-sibling::input'.format(first_val))
                            if cumbtn.is_selected()==False:
                                cum.click()
                            time.sleep(1)
                        except Exception:
                            defaultejecter +=1
            if len(radio_ans_cons) == 0 or defaultejecter == 1:
                # print("IndeedQfill_radio FAILED")
                # print(iterator_text)
                if fieldparent is None:
                    default_skin(i)
                elif fieldparent is not None:
                    try:
                        default_skin(fieldparent)
                    except Exception:
                        default_skin(i)
                time.sleep(1)

        def IndeedQfill_text(i):
            #print("IndeedQfill_text called")
            text_ans_cons = {}
            defaultejecter = 0
            iterator_text = i.text
            for key,value in indeed_text_check.items():
                if key.lower() in iterator_text.lower():
                    text_ans_cons.update(key=value)
                    break
                if key.lower() in iterator_text.lower() and key in indeed_skip_check.keys():
                    text_ans_cons.update(key="skip")
                    break
            if len(text_ans_cons)>0:
                first_val = list(text_ans_cons.values())[0]
                if first_val != "skip":
                    try:
                        bot_typer(answer,first_val)
                        time.sleep(1)
                    except Exception:
                        defaultejecter +=1
            if len(text_ans_cons)== 0 or defaultejecter == 1:
                # print("IndeedQfill_text FAILED")
                #print(iterator_text)
                default_skin(i)
                time.sleep(1)

        Quest_id_list = []
        questions = web.find_elements(By.XPATH, "//*[starts-with(@id, 'q_') and contains(@class, 'Question')]")
        if len(questions) != 0:
            num_questions = str(len(questions))
            current_question = 1

            for i in questions:
                time.sleep(1.5)
                the_id = i.get_attribute("id")
                try:
                    answer = web.find_element(By.XPATH, "//*[@id='{}']//input".format(the_id))
                except NoSuchElementException:
                    try:
                        answer = web.find_element(By.XPATH, "//*[@id='{}']//textarea".format(the_id))
                    except NoSuchElementException:
                        try:
                            answer = web.find_element(By.XPATH, "//*[@id='{}']//select".format(the_id))
                        except NoSuchElementException:
                            continue

                frontend_bot_msg("Answering: question " + str(current_question)+ " of " + num_questions)

                answer_type = answer.get_attribute("type")

                if answer_type == "text":
                    IndeedQfill_text(i)
                if answer_type == "textarea":
                    IndeedQfill_text(i)
                if answer_type == "radio":
                    IndeedQfill_radio(i, question_id=the_id)
                if answer_type == "number":
                    IndeedQfill_number(i)
                if answer_type == "checkbox":
                    IndeedQfill_chkbox(i, question_id=the_id)
                if answer_type == "select-one":
                    IndeedQfill_select(i)
                if answer_type == "date":
                    IndeedQfill_date(i)
                if answer_type == "tel":
                    IndeedQfill_number(i)

                current_question = current_question + 1

        field_questions = web.find_elements(By.TAG_NAME, "fieldset")
        if len(field_questions) != 0:
            num_questions = str(len(field_questions))
            current_question = 1

            for f in field_questions:
                time.sleep(1.5)
                try:
                    answer = f.find_element(By.XPATH, ".//input")
                except NoSuchElementException:
                    try:
                        answer = f.find_element(By.XPATH, ".//textarea")
                    except NoSuchElementException:
                        try:
                            answer = f.find_element(By.XPATH, ".//select")
                        except NoSuchElementException:
                            continue

                frontend_bot_msg("Answering: question " + str(current_question)+ " of " + num_questions)

                answer_type = answer.get_attribute("type")

                if answer_type == "text":
                    IndeedQfill_text(f)
                if answer_type == "textarea":
                    IndeedQfill_text(f)
                if answer_type == "radio":
                    try:
                        fieldparent = f.find_element(By.XPATH, "ancestor::div[starts-with(@id, 'q_')]")
                        if fieldparent.get_attribute('id') not in Quest_id_list and "q_" in fieldparent.get_attribute('id'):
                            IndeedQfill_radio(f, fieldparent=fieldparent)
                            Quest_id_list.append(fieldparent.get_attribute('id'))
                    except Exception:
                        IndeedQfill_radio(f)
                if answer_type == "number":
                    IndeedQfill_number(f)
                if answer_type == "checkbox":
                    try:
                        fieldparent = f.find_element(By.XPATH, "ancestor::div[starts-with(@id, 'q_')]")
                        if fieldparent.get_attribute('id') not in Quest_id_list and "q_" in fieldparent.get_attribute('id'):
                            IndeedQfill_chkbox(f, fieldparent=fieldparent)
                            Quest_id_list.append(fieldparent.get_attribute('id'))
                    except Exception:
                        IndeedQfill_chkbox(f)
                if answer_type == "select-one":
                    IndeedQfill_select(f)
                if answer_type == "date":
                    IndeedQfill_date(f)
                if answer_type == "tel":
                    IndeedQfill_number(f)

                current_question = current_question + 1

    def Indeed_main():
        global Indeed_Job_count
        global Indeed_quote_bool
        global anchor_handle
        global finalprint
        #print("Indeed_main called")

        WebDriverWait(web,20).until(EC.presence_of_element_located((By.CLASS_NAME, "slider_container")))
        indeed_target2 = web.find_elements(By.CLASS_NAME, "slider_container")
        cookiecheck()

        anchor_handle = web.current_window_handle
        job_id_container = []
        indeedApplyButton_ejectVAR = 0

        for i in indeed_target2:

            if indeedApplyButton_ejectVAR == 15:
                errlog(element='indeedApplyButton_ejectVAR', log='Could not find Indeed Apply Button')
                return

            if WE_ARE_SUBMITTING:
                try:
                    response = supabase.table('subs').select('tokens').eq("id",uuid).execute()
                    response_dict = response.model_dump()
                    tokens = response_dict['data'][0]['tokens']
                    if tokens <= 0:
                        finalprint = "Not enough tokens!"
                        frontend_top_msg("Shy Apply stopped.")
                        frontend_bot_msg("Not enough tokens!")
                        try:
                            sys.exit()
                        except Exception:
                            try:
                                web.quit()
                            except Exception:
                                pass
                except Exception as e:
                    errlog(element="Indeed_main() supabase",description=e)
                    supa_retry("ping")

                check_if_running()

            try:
                frontend_top_msg("Found Opportunity!")
                frontend_bot_msg("Reading job description..")
            except Exception as e:
                errlog(element="emergency_log", log="emergency_log is broken", description=e)

            time.sleep(1)
            i.uc_click()
            time.sleep(1)

            try:
                job_id = i.find_element(By.XPATH, './/child::span[contains(@id, "jobTitle-")]')
                if job_id.get_attribute('id') in job_id_container:
                    continue
            except Exception as e:
                errlog(element="job_id", log="job_id is broken", description=e)

            try:
                stupid = WebDriverWait(web,3).until(EC.presence_of_element_located((By.XPATH, '//h3[text()="About Indeed\'s estimated salaries"]')))
                if stupid:
                    stupidclose = web.find_element(By.XPATH, '//h3[text()="About Indeed\'s estimated salaries"]//following-sibling::button[@aria-label="Close"]')
                    stupidclose.uc_click()
                    time.sleep(1)
                    try:
                        WebDriverWait(web, 5).until(EC.visibility_of_element_located((By.XPATH, '//button[@id="indeedApplyButton" and contains(@aria-label, "Apply now opens in a new tab")]')))
                        indeed_container_applyB = web.find_element(By.XPATH, '//button[@id="indeedApplyButton" and contains(@aria-label, "Apply now opens in a new tab")]')
                    except Exception:
                        try:
                            WebDriverWait(web, 5).until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'ia-IndeedApplyButton') and .//*[contains(@aria-label, 'Apply now opens in a new tab')]]")))
                            indeed_container_applyB = web.find_element(By.XPATH, "//div[contains(@class, 'ia-IndeedApplyButton') and .//*[contains(@aria-label, 'Apply now opens in a new tab')]]")
                        except Exception:
                            indeedApplyButton_ejectVAR += 1
                            continue
            except TimeoutException:
                try:
                    WebDriverWait(web, 5).until(EC.visibility_of_element_located((By.XPATH, '//button[@id="indeedApplyButton" and contains(@aria-label, "Apply now opens in a new tab")]')))
                    indeed_container_applyB = web.find_element(By.XPATH, '//button[@id="indeedApplyButton" and contains(@aria-label, "Apply now opens in a new tab")]')
                except Exception:
                    try:
                        WebDriverWait(web, 5).until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'ia-IndeedApplyButton') and .//*[contains(@aria-label, 'Apply now opens in a new tab')]]")))
                        indeed_container_applyB = web.find_element(By.XPATH, "//div[contains(@class, 'ia-IndeedApplyButton') and .//*[contains(@aria-label, 'Apply now opens in a new tab')]]")
                    except Exception:
                        indeedApplyButton_ejectVAR += 1
                        continue
            time.sleep(2)
            try:
                try:
                    companyname = i.find_element(By.XPATH, ".//*[@data-testid='company-name']")
                except NoSuchElementException:
                    companyname = i.find_element(By.XPATH, ".//*[@class='companyName']")
                text = companyname.text
                if len(text) > 30:
                    truncated_text ="Applying to: "+ text[:30] + "..."
                    frontend_top_msg(truncated_text)
                else:
                    emergency_logtext = "Applying: "+text
                    frontend_top_msg(emergency_logtext)
                job_id_container.append(job_id.get_attribute('id'))
            except Exception as e:
                errlog(element="companyname",description=e)
                frontend_top_msg(str(profile_dict['job_title']))
            tabs = web.window_handles
            if len(tabs)>1: # THIS exists in the event of multiple tabs existing before creating the new application tab
                for tab in tabs:
                    web.switch_to.window(tab)
                    if tab != anchor_handle:
                        web.close()
                        time.sleep(0.5)
                    else:
                        continue
                web.switch_to.window(anchor_handle)
            time.sleep(2)
            indeed_container_applyB.uc_click()
            time.sleep(2)
            tabs = web.window_handles
            for o in tabs:
                web.switch_to.window(o)
                if web.current_window_handle!=anchor_handle:
                    break
            try:
                WebDriverWait(web,20).until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'h1')))
            except TimeoutException:
                pass
            time.sleep(7)
            try:
                Indeed_ansfind()
            except Exception:
                pass
            if WE_ARE_SUBMITTING:
                try:
                    confirmVar = 0
                    afterscrn = WebDriverWait(web,20).until(EC.visibility_of_element_located((By.XPATH, '//h1[text()="Your application has been submitted!"]')))
                    web.close()#look for end message if yes then +=1 close tab and switch
                    frontend_bot_msg("Application submitted")
                    indeedApplyButton_ejectVAR = 0
                    try:
                        application_success_log(text)
                    except Exception as e:
                        errlog(element="jobtext", description=e, log="could not find jobtext")
                    confirmVar+=1
                except (TimeoutException, NoSuchWindowException) as e:
                    errlog(element="afterscrn",description=e)
                    try:
                        one_more_step = WebDriverWait(web, 5).until(EC.visibility_of_element_located((By.XPATH, "//h1[text()='One more step']")))
                        if one_more_step:
                            web.close()
                            confirmVar = 0
                    except (TimeoutException, NoSuchWindowException) as e:
                        errlog(element="one_more_step",description=e)
                        try:
                            complete_test = WebDriverWait(web, 5).until(EC.visibility_of_element_located((By.XPATH, "//h1[text()='Complete a test to help your application stand out']")))
                            if complete_test:
                                confirmVar = 0
                                web.close()#look for end message if yes then +=1 close tab and switch
                                frontend_bot_msg("Application submitted")
                                indeedApplyButton_ejectVAR = 0
                                try:
                                    application_success_log(text)
                                except Exception as e:
                                    errlog(element="jobtext", description=e, log="could not find jobtext")
                                confirmVar+=1
                        except (TimeoutException, NoSuchWindowException) as e:
                            errlog(element="complete_test",description=e)
                            confirmVar = 0
                            web.close()
            else:
                confirmVar = 1
            time.sleep(2)
            web.switch_to.window(anchor_handle)
            time.sleep(2)

            if confirmVar == 1:
                Indeed_Job_count+=1
                if WE_ARE_SUBMITTING:
                    tokens_minus_one = tokens - 1
                    try:
                        supabase.table('subs').update({'tokens': tokens_minus_one}).eq("id",uuid).execute()
                    except Exception:
                        supa_retry("update")
                    time.sleep(2)
                    frontend_top_msg("Searching for best Listing")
                    barrens_chat("Scanning Indeed", 960)
                confirmVar = 0#-------------MIGHT CAUSE PROBLEMS
            if Indeed_Job_count >= num_apps:
                break
        if Indeed_Job_count < num_apps:
            try:
                try:
                    current_page = web.find_element(By.XPATH, "//a[@data-testid='pagination-page-current']")
                except NoSuchElementException:
                    current_page = web.find_element(By.XPATH, "//button[@data-testid='pagination-page-current']")
                nextpage_count = int(current_page.text) + 1
                try:
                    next_numpage = web.find_element(By.XPATH, "//a[@aria-label='{}']".format(nextpage_count))
                    next_numpage.uc_click()
                    time.sleep(3)
                    Indeed_main()
                except NoSuchElementException:
                    try:
                        next_page = web.find_element(By.XPATH, "//a[@aria-label='Next Page']")
                        next_page.uc_click()
                        time.sleep(3)
                        Indeed_main()
                    except NoSuchElementException:
                        if Indeed_quote_bool == True:
                            What_Where(x="no quotes")
                            time.sleep(5)
                            Indeed_quote_bool=False
                            Indeed_main()
                        else:
                            Indeed_Job_count = num_apps
            except NoSuchElementException as e:
                errlog(element="current_page",description=e)
        return Indeed_Job_count


    global Indeed_Job_count
    global Indeed_quote_bool
    global resend_tries
    global retry
    global submit
    resend_tries = 3
    retry = False
    submit = False
    Indeed_Job_count = 0
    error_catchvar = 0
    Indeed_quote_bool = False

    try:
        web.get("https://www.indeed.com/")
        time.sleep(8)
        check_if_running()
        Indeed_signin()
    except Exception as e:
        errlog(element="outer Indeed_signin()",description=e)

    try:
        jobcontainerfind1 = WebDriverWait(web,20).until(EC.presence_of_element_located((By.CLASS_NAME, "slider_container")))
        if jobcontainerfind1:
            Indeed_main()
    except TimeoutException as e:
        errlog(element="jobcontainerfind1",description=e)

    # print("Final Indeed job_count = "+str(Indeed_Job_count))
    return Indeed_Job_count

if profile_dict['no_sponsorship'] == 0:
    indeed_radio_check.update({"Select which best describes your right to work in the US?": "I require sponsorship to work for a new employer"})

education_levels = {
    1: "High School",
    2: "GED",
    3: "High School",
    4: "Associates",
    5: "Associates",
    6: "Bachelors",
    7: "Masters",
    8: "Doctoral"
}

edu_level = profile_dict['edu_level']
indeed_radio_check.update({"What is the highest level of education": education_levels[edu_level]})

if WE_ARE_SUBMITTING:
    if profile_dict['previous_work_company'] == 'none' or profile_dict['previous_work_company'] is None:
        pass
    else:
        indeed_text_check.update({'Current (Most Recent) Employer':profile_dict['previous_work_company']})

    if profile_dict['previous_work_job_title'] == 'none' or profile_dict['previous_work_job_title'] is None:
        pass
    else:
        indeed_text_check.update({'Current (Most Recent) Job Title': profile_dict['previous_work_job_title']})

try:
    if os_name() == 'win':
        userdata = profile_dict["shy_dir"] + "\\browser"
    elif os_name() == 'mac':
        userdata = profile_dict["shy_dir"] + "/browser"
        indeed_radio_check.update({'What Computers do you own?':'Apple (newer or top of the line)'})

    try:
        proc_list = []
        for proc in psutil.process_iter():
            if platform_proc_name in proc.name().lower():
                proc_list.append("shyapply")
                break
        if len(proc_list) > 0:
            if WE_ARE_SUBMITTING:
                if is_process_stopped() == False:
                    web = Driver(browser='chrome', uc=True, user_data_dir=userdata, headless=True, headed=False)#headless=True, headed = True -> for Linux
                else:
                    finalprint = 'Red button pressed. Shy Apply Stopped!'
                    frontend_bot_msg(finalprint)
                    sys.exit()
            else:
                web = Driver(browser='chrome', uc=True, user_data_dir=userdata, headless=False, headed=True)#headless=True, headed = True -> for Linux

            web.set_window_size(1920, 1080)
        elif len(proc_list) == 0:
            sys.exit()
    except Exception as e:
        errlog(element="web",description=e, log='probably client closed prior to driver start')

    website_init = []
    if profile_dict["linkedin"] == True:
        website_init.append("LinkedIn")
    if profile_dict["ziprecruiter"] == True:
        website_init.append("ZipRecruiter")
    if profile_dict["glassdoor"] == True:
        website_init.append("Glassdoor")
    if profile_dict["indeed"] == True:
        website_init.append("Indeed")

    for site in website_init:

        if WE_ARE_SUBMITTING:
            try:
                response = supabase.table('subs').select('tokens').eq("id",uuid).execute()
                response_dict = response.model_dump()
                tokens = response_dict['data'][0]['tokens']
                if tokens <= 0:
                    finalprint = "Not enough tokens!"
                    frontend_top_msg("Shy Apply stopped.")
                    frontend_bot_msg("Not enough tokens!")
                    sys.exit()
            except Exception as e:
                errlog(element="response",description=e)
                supa_retry("ping")

        if site == "Indeed":
            try:
                proc_list = []
                for proc in psutil.process_iter():
                    if platform_proc_name in proc.name().lower():
                        proc_list.append("shyapply")
                        break
                if len(proc_list) > 0:
                    if is_process_stopped() == False:
                        if not WE_ARE_SUBMITTING:
                            profile_dict.update({'resume_file':'Dylan Taylor 2024.pdf'})
                            if os_name() == 'win':
                                profile_dict.update({'resume_path':r'C:\Users\crtkd\AppData\Local\shy-apply\Dylan Taylor 2024.pdf'})
                                choice_resumepath = profile_dict['resume_path']
                            elif os_name() == 'mac':
                                profile_dict.update({'resume_path': os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'shy-apply', '1', 'Dylan Taylor 2024.pdf')})
                                choice_resumepath = profile_dict['resume_path']
                        frontend_top_msg("Initializing Indeed...")
                        Indeed_Driver(web)
            except Exception as e:
                errlog(element="Indeed website_init",description=e)

finally:

    if len(logslist) != 0:
        try:
            if WE_ARE_SUBMITTING:
                db = sqlite3.connect(r'{}'.format(args.path))
            else:
                db = sqlite3.connect(os.path.join(profile_dict['shy_dir'], 'shyapply.db'))
            db.row_factory = sqlite3.Row
            db_cursor = db.cursor()
            for log in logslist:
                db_cursor.execute(log)
                db.commit()
            db.close()
        except Exception:
            pass

    if WE_ARE_SUBMITTING:
        try:
            web.quit()
        except Exception:
            pass

        term_proc_list = ['chromedriver', 'uc_driver', 'shy_drivers', 'odetodionysus']
        for proc in psutil.process_iter():
            try:
                if "chrome" in proc.name().lower():
                    try:
                        nut = psutil.Process(proc.pid).cmdline()
                        if os_name() == 'win':
                            if '--user-data-dir=' + profile_dict["shy_dir"] + "\\browser" in nut:
                                proc.kill()
                        elif os_name() == 'mac':
                            if '--user-data-dir=' + profile_dict["shy_dir"] + "/browser" in nut:
                                proc.kill()
                    except (NoSuchProcess, ProcessLookupError, AccessDenied):
                        pass
            except (NoSuchProcess, ProcessLookupError, AccessDenied):
                pass
            try:
                if any(word in proc.name().lower() for word in term_proc_list):
                    try:
                        proc.kill()
                    except (NoSuchProcess,ProcessLookupError, AccessDenied):
                        pass
            except (NoSuchProcess, ProcessLookupError, AccessDenied):
                pass

    elif not WE_ARE_SUBMITTING:
        print("enter input")
        x = input()
        try:
            web.quit()
        except Exception:
            pass

    try:
        frontend_top_msg("Shy Apply finished.")
        frontend_bot_msg(finalprint)
    except Exception:
        pass
