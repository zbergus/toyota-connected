# Toyota Connected Services (North America) - Home Assistant Integration

A modern, secure, and native Home Assistant integration for Toyota and Lexus Connected Services in North America, with dedicated support for **Canada** and the **2024 Toyota bZ4X (24MM generation BEV)**.

---

## Key Highlights & Modern Upgrades

- **Strict Security**:
  - Implements **RFC 7636 PKCE S256** OAuth authentication (plain-text challenges eliminated).
  - Serialized token refresh guarded by `asyncio.Lock()` to prevent race conditions and invalid grant lockouts.
  - Zero plaintext password persistence after authentication.
  - Strict diagnostics redaction (stripping tokens, GUIDs, device IDs, and location coordinates).
- **First-Class Canada Support**:
  - Dynamic regional routing (`x-region: "CA"`).
  - Native metric units: Kilometers (`km`), Celsius (`°C`), Kilopascals (`kPa`), and Kilowatts (`kW`).
- **2024 Toyota bZ4X (24MM Generation BEV) Features**:
  - **Sensors**: Battery Level (State of Charge %), Usable Battery Capacity %, Driving Range (AC Off), Driving Range (AC On), Charging Power (kW), Remaining Charge Time (to 100% and to 80%), Odometer (km), and Individual Tire Pressures (kPa / PSI).
  - **Binary Sensors**: Active Charging, Plug Connection, Doors, Windows, Hatch, and Hood.
  - **Controls**:
    - `switch.*_immediate_charge`: Start or stop charging immediately.
    - `switch.*_climate_preconditioning`: Quick toggle for cabin climate pre-conditioning.
    - `select.*_target_charge_limit`: Set target battery charging limit (50%, 60%, 70%, 80%, 90%, 100%).
    - `select.*_ac_current_limit`: Set max AC charging current (8 A, 16 A, 32 A, Max).
    - `lock.*_door_lock`: Remote lock and unlock.
    - `climate.*_climate`: Cabin pre-conditioning thermostat in Celsius.
- **Smart 12V Battery Protection**:
  - Passive WebSocket event listening while vehicle is parked and asleep (avoids draining the vehicle's 12V auxiliary battery).
  - Automatic single status sync after vehicle trip completion (odometer advancement detected).
- **Decoupled Architecture**:
  - Entire client core is natively built within the integration; completely retires runtime monkey-patching of the unmaintained `toyota-na` PyPI library.

---

## Installation

### Method 1: HACS (Recommended)
1. In Home Assistant, open **HACS** > **Integrations**.
2. Click the three dots in the top right > **Custom repositories**.
3. Add your repository URL: `https://github.com/zbergus/toyota` with Category: **Integration**.
4. Search for `Toyota Connected Services (North America)` and click **Download**.
5. Restart Home Assistant.

### Method 2: Manual Installation
1. Copy or symlink `custom_components/toyota_na` into your Home Assistant directory:
   ```bash
   ln -s /path/to/toyota/custom_components/toyota_na ~/.homeassistant/custom_components/toyota_na
   ```
2. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **Toyota Connected Services (North America)**.
3. Enter your Toyota account email and password.
4. When prompted, enter the One-Time Password (OTP) verification code sent to your email or SMS.
5. Your 2024 bZ4X (and any other vehicles on the account) will be discovered automatically with full sensors and controls.

---

## Testing

Run the automated unit test suite:
```bash
python3 -m unittest discover -s tests -v
```
