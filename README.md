# Water Pump GUI

Tkinter GUI for controlling a Leica automatic water immersion dispenser via RS-232.

## Requirements

- Python 3.10+
- `pyserial`

```bash
conda create -n waterpump python=3.10
conda activate waterpump
pip install pyserial
```

## Usage

```bash
conda activate waterpump
python waterpump_gui.py
```

Or create a batch file on Windows (`run_waterpump.bat`):

```bat
call conda activate waterpump
python waterpump_gui.py
```

## Step-by-step workflow

### Startup
1. Click **Refresh** to detect COM ports
2. Select your port (e.g. `COM17`) from the dropdown
3. Click **Connect** — status turns green
4. Click **Check connection (37045)** — log should show `37045 1`
5. Click **STOP (37021)** — clears any running state
6. Click **INIT (37020)** — powers motor, resets position
7. Click **Check status (37004)** — log should show `37004 0`
8. Click **Read once** — confirms a sensible impedance value (~14000–15500)

### Filling
9. Click **Gradual Fill** — steps through targets 15000 → 15200 → 15450 automatically

### Monitoring
10. Set **Duration** (hours) and **Interval** (seconds)
11. Click **Start Monitoring** — polls impedance, logs timestamp + value
12. Click **Stop Monitoring** to end early
13. Click **Save log to CSV** to export data

### Draining
14. Click **Safe Drain** and confirm — runs the full drain procedure automatically:
    - Reduces target, stops auto mode
    - Waits for contact to break (prompts if still present)
    - Drains slowly until dry threshold

### Shutdown
15. Click **STOP (37021)**
16. Click **Auto mode OFF (37042 0)**
17. Click **Disconnect**

## Impedance reference

| Value       | Meaning                  |
|-------------|--------------------------|
| < 14000     | Dry / air risk           |
| ~14100      | Contact break threshold  |
| 15000–15500 | Working range            |
| > 15500     | Overfill risk            |

## Commands reference

| Command    | Description                        |
|------------|------------------------------------|
| 37020      | Initialize system                  |
| 37021      | Stop                               |
| 37040 N    | Set target impedance to N          |
| 37041      | Read current target                |
| 37042 1/0  | Auto immersion ON / OFF            |
| 37043      | Read auto mode state               |
| 37044      | Read measured impedance            |
| 37045      | Check connection                   |
| 37004      | Device status                      |
