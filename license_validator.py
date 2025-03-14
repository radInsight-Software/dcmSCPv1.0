# license_validator.py

import os
import datetime
import hashlib
import base64
import traceback
from cryptography.fernet import Fernet

class LicenseValidator:
    def __init__(self, software_name):
        """Initialize the validator with the software name."""
        self.software_name = software_name
        self.license_file = f"{software_name}_license.key"
        self.system_info_file = "computer_info.txt"

    def get_software_secret(self):
        """Generate a consistent secret key based on the software name."""
        key_material = f"YourSecretPrefix-{self.software_name}".encode()
        hashed_key = hashlib.sha256(key_material).digest()[:32]
        encoded_key = base64.urlsafe_b64encode(hashed_key)
        return Fernet(encoded_key)

    def validate_license(self):
        """Validate the license on the client system."""
        try:
            print(f"🔍 Validating license for {self.license_file}...")

            # Check if license and system info files exist
            if not os.path.exists(self.license_file):
                print("❌ License file missing! Exiting...")
                return False

            if not os.path.exists(self.system_info_file):
                print("❌ System info file missing! Exiting...")
                return False

            # Load encrypted license
            with open(self.license_file, "r", encoding="utf-8") as file:
                encrypted_license = file.read().strip()

            print(f"🔐 Encrypted License: {encrypted_license[:50]}...")  # Display first 50 chars for debug

            # Get the secret key
            secret_key = self.get_software_secret()
            cipher = secret_key  # Use Fernet instance

            try:
                # Decrypt license key
                decrypted_license = cipher.decrypt(encrypted_license.encode()).decode()
            except Exception:
                print("❌ Error: License decryption failed! License may be corrupted or invalid.")
                return False

            print(f"✅ Decrypted License Data: {decrypted_license}")

            # Parse license data
            try:
                system_info, trial_start, trial_days = decrypted_license.split("|")
            except ValueError:
                print("❌ Error: Invalid license format!")
                return False

            # Load actual system info
            with open(self.system_info_file, "r", encoding="utf-8") as file:
                actual_system_info = file.read().strip()

            print(f"🔎 Expected System Info: {system_info}")
            print(f"🔎 Actual System Info: {actual_system_info}")

            # Compare decrypted system info with actual system info
            if system_info != actual_system_info:
                print("❌ System info mismatch! License invalid.")
                return False

            # Check trial period
            try:
                trial_start_date = datetime.datetime.strptime(trial_start, "%Y-%m-%d")
                trial_days = int(trial_days)
            except ValueError:
                print("❌ Error: Invalid date or trial period in license!")
                return False

            current_date = datetime.datetime.now()
            days_elapsed = (current_date - trial_start_date).days

            if days_elapsed > trial_days:
                print(f"⏳ Trial Expired! Please activate {self.software_name}.")
                return False
            else:
                days_remaining = trial_days - days_elapsed
                print(f"✅ License Valid! Trial active for {days_remaining} more days.")
                return True

        except Exception as e:
            error_msg = f"❌ License validation error: {e}\n{traceback.format_exc()}"
            print(error_msg)
            with open("gerkeyerror.log", "w", encoding="utf-8") as error_file:
                error_file.write(error_msg)
            return False
