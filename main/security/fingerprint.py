import hashlib
import platform
import uuid
import subprocess
import os

def get_mac():
    mac = uuid.getnode()
    return ':'.join(f'{(mac >> ele) & 0xff:02x}' for ele in range(40, -1, -8))

def get_cpu_id():
    try:
        output = subprocess.check_output(
            ['powershell', '-Command', '(Get-CimInstance Win32_Processor).ProcessorId'],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return output or "unknown_cpu"
    except Exception:
        return "unknown_cpu"

    
#For Linux
def get_cpu_id_linux():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "Serial" in line or "model name" in line:
                    return line.split(":")[1].strip()
    except:
        pass
    return "unknown_cpu"


def get_motherboard_serial():
    try:
        output = subprocess.check_output(
            ['powershell', '-Command', '(Get-CimInstance Win32_BaseBoard).SerialNumber'],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return output or "unknown_board"
    except Exception:
        return "unknown_board"

#For Linux
def get_motherboard_serial_linux():
    try:
        return subprocess.check_output(
            "cat /sys/class/dmi/id/board_serial", shell=True
        ).decode().strip()
    except:
        return "unknown_board"


def get_disk_serial():
    try:
        output = subprocess.check_output(
            [
                'powershell',
                '-Command',
                "(Get-CimInstance Win32_PhysicalMedia | Select-Object -First 1).SerialNumber"
            ],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return output or "unknown_disk"
    except Exception:
        return "unknown_disk"

    
#For Linux
def get_disk_serial_linux():
    try:
        return subprocess.check_output(
            "lsblk -o SERIAL | sed -n '2p'", shell=True
        ).decode().strip()
    except:
        return "unknown_disk"

def generate_machine_fingerprint():
    system = platform.system()
    print(system)
    print(get_cpu_id())
    print(get_motherboard_serial())
    print(get_disk_serial())
    print(get_mac())

    if system == "Windows":
        parts = [
            get_mac(),
            get_cpu_id(),
            get_motherboard_serial(),
            get_disk_serial(),
        ]
    else:
        parts = [
            get_mac(),
            get_cpu_id_linux(),
            get_motherboard_serial_linux(),
            get_disk_serial_linux(),
        ]

    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()

LICENSE_FILE = "license.lock"

def load_fingerprint():
    if not os.path.exists(LICENSE_FILE):
        return None
    with open(LICENSE_FILE, "r") as f:
        return f.read().strip()

def save_fingerprint(fp):
    with open(LICENSE_FILE, "w") as f:
        f.write(fp)
